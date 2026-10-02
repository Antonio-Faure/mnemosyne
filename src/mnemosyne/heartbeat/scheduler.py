"""Durable heartbeat: the perpetual discover→verify→harvest→repair loop."""

from __future__ import annotations

import asyncio
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

HARVEST_INTERVAL_S = 1800
VERIFY_INTERVAL_S = 21600
WARMUP_INTERVAL_S = 3600
JOURNAL_INTERVAL_S = 900
WATCHDOG_INTERVAL_S = 300  # invariants check, inside the service (no side process)
AGENCY_INTERVAL_S = 120  # check the bi-agent mailbox every 2 minutes (idle = free)


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
            if not self.engine.db.has_open_job("harvest", d.id):
                self.engine.db.enqueue(
                    Job(kind="harvest",
                        payload={"source_id": d.id, "interval_s": HARVEST_INTERVAL_S, "limit": 20},
                        priority=50)
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
        if not self.engine.db.has_open_job("journal"):
            self.engine.db.enqueue(
                Job(kind="journal", payload={"interval_s": JOURNAL_INTERVAL_S}, priority=90)
            )
        if not self.engine.db.has_open_job("agency"):
            self.engine.db.enqueue(
                Job(kind="agency", payload={"interval_s": AGENCY_INTERVAL_S}, priority=30)
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
        self.bootstrap()
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

    def stop(self) -> None:
        self._stop.set()

    async def _poll_telegram(self) -> None:
        """Forward the operator's Telegram replies into the control inbox."""
        if not self.notifier.enabled:
            return
        offset = self.engine.db.get_kv("telegram_offset")
        messages, next_offset = await self.notifier.poll(offset)
        if next_offset is not None and next_offset != offset:
            self.engine.db.set_kv("telegram_offset", next_offset)
        for message in messages:
            log.info("telegram operator: %s", message)
            self.control.post(message)

    def _process_inbox(self) -> None:
        for message in self.control.consume():
            log.info("operator message: %s", message)
            self.journal.append(f"message opérateur : {message}", source="operator")

    async def _tick(self) -> None:
        await self._poll_telegram()
        self._process_inbox()
        now = datetime.now(UTC)
        stale_cutoff = (now - timedelta(seconds=self.config.heartbeat.stale_lock_s)).isoformat()
        recovered = self.engine.db.recover_stale_jobs(stale_cutoff)
        if recovered:
            log.warning("recovered %d stale jobs", recovered)
            self.journal.append(
                f"{recovered} jobs bloqués récupérés", level="warn", source="recovery"
            )

        jobs = self.engine.db.claim_due_jobs(utcnow_iso(), self.config.heartbeat.max_workers)
        if not jobs:
            return
        sem = asyncio.Semaphore(self.config.heartbeat.max_workers)

        async def run(job: Job) -> None:
            async with sem:
                await self._run_job(job)

        await asyncio.gather(*(run(j) for j in jobs))

    async def _run_job(self, job: Job) -> None:
        assert job.id is not None
        handler = HANDLERS.get(job.kind)
        if handler is None:
            self.engine.db.fail_job(job.id, f"no handler for kind={job.kind}")
            return
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
            self._reschedule(job, in_seconds=60, error=str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            if job.attempts + 1 >= job.max_attempts:
                self.engine.db.fail_job(job.id, str(exc))
                self.journal.append(f"job {job.kind} échoué définitivement : {exc}", level="error")
                await self.notifier.send(f"job {job.kind} failed permanently: {exc}", "error")
            else:
                self.journal.append(f"job {job.kind} erreur (retry) : {exc}", level="warn")
                self._reschedule(job, in_seconds=2 ** (job.attempts + 1) * 30, error=str(exc))
            return
        self.engine.db.complete_job(job.id)

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
