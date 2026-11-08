"""Durable heartbeat: the perpetual discover→verify→repair loop."""

from __future__ import annotations

import asyncio
import contextlib
import time
from datetime import UTC, datetime, timedelta

from mnemosyne.config import Config
from mnemosyne.engine import Engine
from mnemosyne.heartbeat.jobs import HANDLERS, JobContext
from mnemosyne.journal import Control, Journal
from mnemosyne.logger import get_logger
from mnemosyne.models import AuthKind, Job, JobState
from mnemosyne.notify import Notifier
from mnemosyne.reputation import GovernorBlocked
from mnemosyne.sources import build_connector
from mnemosyne.util import cleanup_orphan_tmp, utcnow_iso

log = get_logger("heartbeat")

VERIFY_INTERVAL_S = 21600
WARMUP_INTERVAL_S = 3600
JOURNAL_INTERVAL_S = 900
WATCHDOG_INTERVAL_S = 300  # invariants check, inside the service (no side process)
AGENCY_INTERVAL_S = 120  # check the bi-agent mailbox every 2 minutes (idle = free)
OPERATOR_INTERVAL_S = 30  # poll the operator bots (answers wake parked tasks)

#: Job runs whose real trace is the task session: keep them out of the sidebar
#: by default (visible with "inclure les runs silencieux").
SILENT_JOB_KINDS = frozenset({"agency", "warmup", "resolver"})


class Heartbeat:
    def __init__(self, config: Config, engine: Engine | None = None):
        self.config = config
        self.engine = engine or Engine(config)
        self.notifier = Notifier(config.notify.telegram)
        self.journal = Journal(config.journal_path)
        self.control = Control(config.control_path)
        self.ctx = JobContext(
            config=config,
            engine=self.engine,
            journal=self.journal,
            control=self.control,
            notifier=self.notifier,
        )
        self._stop = asyncio.Event()
        # Jobs run OUTSIDE the tick: a long agent session (agency, resolver) must
        # never freeze the heartbeat and starve the other permanent loop.
        self._inflight: dict[int, asyncio.Task] = {}

    # ── bootstrap ────────────────────────────────────────────────────────
    def bootstrap(self) -> None:
        cleanup_orphan_tmp(self.config.data_path)
        pruned = self.engine.db.prune_duplicate_jobs()
        if pruned:
            log.warning("pruned %d duplicate pending jobs", pruned)
        done_cutoff = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        old = self.engine.db.prune_done_jobs(done_cutoff)
        if old:
            log.info("pruned %d finished jobs older than 7 days", old)
        descriptors = self.engine.catalog.sync()
        supported = 0
        for d in descriptors:
            if not d.enabled:
                continue
            if build_connector(d, self.engine.http) is None:
                log.debug("skipping %s (no connector yet)", d.id)
                continue
            supported += 1
            if not self.engine.db.has_open_job("verify", d.id):
                self.engine.db.enqueue(
                    Job(kind="verify", payload={"source_id": d.id, "interval_s": VERIFY_INTERVAL_S},
                        priority=10)
                )
            # Providers that need access are onboarded by the browser agent, and
            # get their own dated journal (`journal/services/<id>.md`).
            if d.auth != AuthKind.NONE:
                if not self.journal.service_path(d.id).exists():
                    self.journal.append_service(
                        d.id,
                        f"objectif : obtenir l'accès (auth={d.auth.value}, "
                        f"portail {d.base_url})",
                        title=d.name,
                        source="bootstrap",
                    )
        warmup = self.config.reputation.account_created_at
        if warmup and not self.engine.db.has_open_job("warmup"):
            self.engine.db.enqueue(
                Job(kind="warmup", payload={"interval_s": WARMUP_INTERVAL_S}, priority=20)
            )
        if not self.engine.db.has_open_job("watchdog"):
            self.engine.db.enqueue(
                Job(kind="watchdog", payload={"interval_s": WATCHDOG_INTERVAL_S}, priority=99)
            )
        if self.config.operator.enabled and not self.engine.db.has_open_job("telegram"):
            self.engine.db.enqueue(
                Job(kind="telegram", payload={"interval_s": OPERATOR_INTERVAL_S}, priority=15)
            )
        if self.config.email.enabled and not self.engine.db.has_open_job("email_watch"):
            self.engine.db.enqueue(
                Job(
                    kind="email_watch",
                    payload={
                        "interval_s": max(10, self.config.email.poll_interval_s),
                    },
                    priority=25,
                )
            )
        if not self.engine.db.has_open_job("journal"):
            self.engine.db.enqueue(
                Job(kind="journal", payload={"interval_s": JOURNAL_INTERVAL_S}, priority=90)
            )
        if not self.engine.db.has_open_job("agency"):
            self.engine.db.enqueue(
                Job(kind="agency", payload={"interval_s": AGENCY_INTERVAL_S}, priority=30)
            )
        if self.config.resolver.enabled and not self.engine.db.has_open_job("resolver"):
            self.engine.db.enqueue(
                Job(
                    kind="resolver",
                    payload={"interval_s": max(30, self.config.resolver.interval_s)},
                    priority=35,
                )
            )
        if self.config.discovery.enabled and not self.engine.db.has_open_job("discover"):
            self.engine.db.enqueue(
                Job(
                    kind="discover",
                    payload={"interval_s": self.config.discovery.interval_s},
                    priority=95,
                )
            )
        log.info("heartbeat bootstrapped: %d supported providers", supported)

        dropped = self.engine.db.release_legacy_leases()
        if dropped:
            log.warning("released %d legacy lease(s) at boot", dropped)

        directives = self.control.directives()
        self.journal.append(
            f"démarrage heartbeat — {supported} providers supportés"
            + (f" — directives: {directives}" if directives else ""),
            source="boot",
        )

    # ── main loop ────────────────────────────────────────────────────────
    async def run_forever(self) -> None:
        try:
            self.bootstrap()
        except Exception as exc:  # noqa: BLE001 - a broken config must not kill the loop
            log.error("bootstrap failed: %s", exc, exc_info=True)
            await self.notifier.send(f"heartbeat bootstrap failed: {exc}", "error")
        renew = asyncio.create_task(self._renew_loop())
        try:
            pending = self.engine.db.count_jobs(JobState.PENDING)
            await self.notifier.send(f"mnemosyne heartbeat online — {pending} jobs pending")
            while not self._stop.is_set():
                try:
                    await self._tick()
                except Exception as exc:  # noqa: BLE001 - the heartbeat must never die
                    log.error("tick error: %s", exc, exc_info=True)
                    await self.notifier.send(f"heartbeat tick error: {exc}", "error")
                try:
                    await asyncio.wait_for(
                        self._stop.wait(), timeout=self.config.heartbeat.tick_seconds
                    )
                except TimeoutError:
                    pass
        finally:
            renew.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await renew

    async def _renew_loop(self, interval_s: float = 60.0) -> None:
        """Keep our leases and job locks fresh while we work.

        A live process renews; a dead one stops renewing, and the lease expiry
        (~5 min) or the stale-job recovery takes over.
        """
        while True:
            await asyncio.sleep(interval_s)
            try:
                self.engine.db.renew_own()
            except Exception as exc:  # noqa: BLE001 - renewal must not kill the loop
                log.warning("renewal failed: %s", exc)

    def request_stop(self) -> None:
        """SIGTERM/SIGINT: free OUR leases at once, then stop the loop.

        Compose sends SIGTERM and SIGKILLs ~10 s later: releasing here lets the
        next container generation start immediately instead of waiting for the
        renewed TTL to lapse. Running jobs are requeued for the same reason —
        leaving them RUNNING would park both loops until the stale recovery.
        """
        try:
            requeued = self.engine.db.requeue_own_jobs()
            if requeued:
                log.info("requeued %d running job(s) before shutdown", requeued)
        except Exception as exc:  # noqa: BLE001 - shutdown must never raise
            log.debug("cannot requeue running jobs: %s", exc)
        self.release_own_leases()
        self.stop()

    def release_own_leases(self) -> None:
        for name in ("agency", "browser", "resolver"):
            try:
                self.engine.db.release_own_lease(name)
            except Exception as exc:  # noqa: BLE001 - shutdown must never raise
                log.debug("cannot release the %s lease: %s", name, exc)

    def stop(self) -> None:
        self._stop.set()

    def _process_inbox(self) -> None:
        for message in self.control.consume():
            log.info("operator message: %s", message)
            self.journal.append(f"message opérateur : {message}", source="operator")

    async def _tick(self) -> None:
        self._process_inbox()
        now = datetime.now(UTC)
        stale_cutoff = (now - timedelta(seconds=self.config.heartbeat.stale_lock_s)).isoformat()
        recovered = self.engine.db.recover_stale_jobs(stale_cutoff)
        if recovered:
            log.warning("recovered %d stale jobs", recovered)
            self.journal.append(
                f"{recovered} jobs bloqués récupérés", level="warn", source="recovery"
            )

        jobs = self.engine.db.claim_due_jobs(utcnow_iso(), self._free_slots())
        for job in jobs:
            self._dispatch(job)

    def _free_slots(self) -> int:
        """Concurrency budget left: `max_workers` minus the jobs already running."""
        return max(0, self.config.heartbeat.max_workers - len(self._inflight))

    def _dispatch(self, job: Job) -> None:
        """Start one job in its own task; `_tick` never waits for it."""
        assert job.id is not None
        task = asyncio.create_task(self._run_job(job), name=f"job:{job.kind}:{job.id}")
        self._inflight[job.id] = task
        task.add_done_callback(lambda t: self._job_finished(job.id, t))

    def _job_finished(self, job_id: int, task: asyncio.Task) -> None:
        self._inflight.pop(job_id, None)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            # `_run_job` handles handler errors itself; reaching this point means
            # the bookkeeping around it broke. The stale-job recovery is the net.
            log.error("job #%s crashed outside its handler: %s", job_id, exc, exc_info=exc)

    async def _drain(self) -> None:
        """Wait for every dispatched job (tests, graceful shutdown)."""
        while self._inflight:
            await asyncio.gather(*list(self._inflight.values()), return_exceptions=True)

    async def _run_job(self, job: Job) -> None:
        assert job.id is not None
        handler = HANDLERS.get(job.kind)
        if handler is None:
            self.engine.db.fail_job(job.id, f"no handler for kind={job.kind}")
            return
        db = self.engine.db
        # one job RUN = one observatory session (the row is unique per execution)
        db.open_job_session(job.id, job.kind, payload=job.payload)
        started = time.monotonic()
        try:
            if job.kind == "agency":
                # An agent session is judged on progress (the stall marker),
                # never on a clock: no wall cap, whatever the mission length.
                updates = await handler(self.ctx, job)
            else:
                # Mechanical jobs are internally bounded (httpx 30s/request,
                # plafonné loops); the timeout only protects the heartbeat loop
                # from a hung handler freezing _tick forever.
                updates = await asyncio.wait_for(
                    handler(self.ctx, job), timeout=self.config.heartbeat.job_timeout_s
                )
        except GovernorBlocked as exc:
            log.warning("job %s blocked: %s", job.kind, exc)
            db.close_job_session(
                job.id,
                status="blocked",
                error=str(exc),
                extra={"duration_s": round(time.monotonic() - started, 1)},
            )
            self._reschedule(job, in_seconds=60, error=str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            db.close_job_session(
                job.id,
                status="failed",
                error=str(exc),
                extra={"duration_s": round(time.monotonic() - started, 1)},
            )
            if job.attempts + 1 >= job.max_attempts:
                self.engine.db.fail_job(job.id, str(exc))
                self.journal.append(f"job {job.kind} échoué définitivement : {exc}", level="error")
                await self.notifier.send(f"job {job.kind} failed permanently: {exc}", "error")
            else:
                self.journal.append(f"job {job.kind} erreur (retry) : {exc}", level="warn")
                self._reschedule(job, in_seconds=2 ** (job.attempts + 1) * 30, error=str(exc))
            return
        # `_activity` is a session title/relevance hint, never a payload field
        activity = updates.pop("_activity", None) if updates else None
        self.engine.db.complete_job(job.id)
        db.close_job_session(
            job.id,
            status="done",
            activity=activity,
            # wrappers always silent; other jobs keep the activity rule
            # (no activity = silent run, never a sidebar entry)
            notable=False if job.kind in SILENT_JOB_KINDS else None,
            extra={
                "duration_s": round(time.monotonic() - started, 1),
                "updates": updates or {},
            },
        )

        payload = dict(job.payload)
        if updates:
            payload.update(updates)
        # the handler may override interval_s to schedule the next run dynamically
        interval = payload.get("interval_s")
        if interval:
            run_at = (datetime.now(UTC) + timedelta(seconds=int(interval))).isoformat()
            self.engine.db.enqueue(
                Job(kind=job.kind, payload=payload, priority=job.priority, run_at=run_at)
            )

    def _reschedule(self, job: Job, in_seconds: int, error: str | None = None) -> None:
        assert job.id is not None
        run_at = (datetime.now(UTC) + timedelta(seconds=in_seconds)).isoformat()
        self.engine.db.reschedule_job(job.id, run_at, error)

    async def aclose(self) -> None:
        await self.engine.aclose()
