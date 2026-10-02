"""SQLite persistence (WAL) for the catalog, asset store and durable job queue."""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from mnemosyne.models import Asset, Job, JobState, SourceState
from mnemosyne.util import ensure_dir, utcnow_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id            TEXT PRIMARY KEY,
    descriptor    TEXT NOT NULL,
    state         TEXT NOT NULL,
    last_error    TEXT,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    id              TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL,
    source_asset_id TEXT NOT NULL,
    data            TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assets_source ON assets(source_id);

CREATE TABLE IF NOT EXISTS jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT NOT NULL,
    payload      TEXT NOT NULL,
    state        TEXT NOT NULL,
    priority     INTEGER NOT NULL DEFAULT 100,
    attempts     INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    run_at       TEXT NOT NULL,
    locked_at    TEXT,
    locked_by    TEXT,
    last_error   TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_due ON jobs(state, run_at, priority);

CREATE TABLE IF NOT EXISTS counters (
    key   TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS discoveries (
    id          TEXT PRIMARY KEY,
    host        TEXT NOT NULL,
    data        TEXT NOT NULL,
    source      TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sender      TEXT NOT NULL,
    recipient   TEXT NOT NULL,
    body        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TEXT NOT NULL,
    handled_at  TEXT,
    note        TEXT,
    claimed_at  TEXT,
    claimed_by  TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status, recipient);

"""


def _proc_start_time(pid: int | None = None) -> int | None:
    """Start time of a process (/proc field 22): identifies an incarnation.

    In a container every `mnemosyne run` is pid 1, so the pid alone cannot tell
    "the current holder" from "a previous generation that died".
    """
    target = pid if pid is not None else os.getpid()
    try:
        with open(f"/proc/{target}/stat", "rb") as handle:
            raw = handle.read()
    except OSError:
        return None
    try:
        fields = raw[raw.rindex(b")") + 2 :].split()
        return int(fields[19])
    except (ValueError, IndexError):
        return None


def _holder_is_gone(payload: dict) -> bool:
    """True when a lease/claim holder cannot be alive for us.

    Single container per database: a payload from another hostname belongs to a
    previous container generation (docker gives a fresh hostname on recreate),
    and that process is gone. Same hostname -> check pid + incarnation.
    """
    host = payload.get("host")
    if host is None:  # legacy payload: cannot attribute, respect it until expiry
        return False
    if host != socket.gethostname():
        return True
    return _process_gone(payload.get("pid"), payload.get("started"))


def _process_gone(pid: object, started: object) -> bool:
    """True when `pid` is dead, or alive but a different process incarnation."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    if isinstance(started, int) and started > 0:
        current = _proc_start_time(pid)
        if current is not None and current != started:
            return True  # pid reused by a newer process
    return False


def _claim_owner(who: str) -> str:
    """Identify the claimer (kind, pid, host) so a dead one is detectable."""
    return json.dumps(
        {
            "who": who,
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "started": _proc_start_time(),
        }
    )


def _owner_is_dead(raw: str | None) -> bool:
    """True when the claimer of a message cannot be alive for us (see
    `_holder_is_gone`: foreign container, dead pid, or a reused pid)."""
    if not raw:
        return False
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        data = None
    if not isinstance(data, dict):
        # legacy owner format: "heartbeat:1234" / "cli:1234"
        try:
            data = {"pid": int(str(raw).rsplit(":", 1)[-1])}
        except (TypeError, ValueError):
            return False
    return _holder_is_gone(data)


def _read_lease(raw: str) -> dict | None:
    """Parse a lease value: JSON object, JSON number, or a plain float expiry."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        try:
            return {"expires": float(raw)}
        except (TypeError, ValueError):
            return None
    if isinstance(data, dict):
        return data
    if isinstance(data, (int, float)):  # legacy: the bare expiry was valid JSON
        return {"expires": float(data)}
    return None


def _lease_is_stale(held: dict, now: float) -> bool:
    """True when a lease may be taken: expired, or its holder process is gone."""
    if float(held.get("expires", 0)) <= now:
        return True
    return _holder_is_gone(held)


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        ensure_dir(self.path.parent)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self) -> None:
        """Add columns introduced after the first schema version (idempotent)."""
        for table, names in (
            ("messages", ("claimed_at", "claimed_by")),
            ("jobs", ("locked_by",)),
        ):
            cols = {row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})")}
            for name in names:
                if name not in cols:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} TEXT")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ── sources ──────────────────────────────────────────────────────────
    def upsert_source(self, source_id: str, descriptor: dict, state: SourceState) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO sources (id, descriptor, state, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       descriptor = excluded.descriptor,
                       updated_at = excluded.updated_at""",
                (source_id, json.dumps(descriptor), state.value, utcnow_iso()),
            )
            self._conn.commit()

    def set_source_state(
        self, source_id: str, state: SourceState, last_error: str | None = None
    ) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sources SET state = ?, last_error = ?, updated_at = ? WHERE id = ?",
                (state.value, last_error, utcnow_iso(), source_id),
            )
            self._conn.commit()

    def get_source(self, source_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sources WHERE id = ?", (source_id,)
            ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "descriptor": json.loads(row["descriptor"]),
            "state": row["state"],
            "last_error": row["last_error"],
            "updated_at": row["updated_at"],
        }

    def list_sources(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT id FROM sources ORDER BY id").fetchall()
        return [s for sid in (r["id"] for r in rows) if (s := self.get_source(sid))]

    # ── assets ───────────────────────────────────────────────────────────
    def save_assets(self, assets: list[Asset]) -> int:
        if not assets:
            return 0
        with self._lock:
            self._conn.executemany(
                """INSERT INTO assets (id, source_id, source_asset_id, data, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO NOTHING""",
                [
                    (a.id, a.source_id, a.source_asset_id, a.model_dump_json(), utcnow_iso())
                    for a in assets
                ],
            )
            self._conn.commit()
        return len(assets)

    def get_asset(self, asset_id: str) -> Asset | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM assets WHERE id = ?", (asset_id,)
            ).fetchone()
        return Asset.model_validate_json(row["data"]) if row else None

    def count_assets(self, source_id: str | None = None) -> int:
        with self._lock:
            if source_id:
                row = self._conn.execute(
                    "SELECT COUNT(*) AS n FROM assets WHERE source_id = ?", (source_id,)
                ).fetchone()
            else:
                row = self._conn.execute("SELECT COUNT(*) AS n FROM assets").fetchone()
        return int(row["n"]) if row else 0

    # ── jobs ─────────────────────────────────────────────────────────────
    def enqueue(self, job: Job) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO jobs (kind, payload, state, priority, attempts, max_attempts, run_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    job.kind,
                    json.dumps(job.payload),
                    JobState.PENDING.value,
                    job.priority,
                    job.attempts,
                    job.max_attempts,
                    job.run_at,
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def get_job(self, job_id: int) -> Job | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row) if row else None

    def claim_due_jobs(self, now: str, limit: int) -> list[Job]:
        """Atomically claim up to `limit` due jobs, marking them RUNNING."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM jobs
                   WHERE state = ? AND run_at <= ?
                   ORDER BY priority ASC, id ASC
                   LIMIT ?""",
                (JobState.PENDING.value, now, limit),
            ).fetchall()
            claimed: list[Job] = []
            for row in rows:
                cur = self._conn.execute(
                    """UPDATE jobs SET state = ?, locked_at = ?, locked_by = ?
                       WHERE id = ? AND state = ?""",
                    (
                        JobState.RUNNING.value,
                        now,
                        _claim_owner(f"job:{row['kind']}"),
                        row["id"],
                        JobState.PENDING.value,
                    ),
                )
                if cur.rowcount:
                    claimed.append(_row_to_job(row))
            self._conn.commit()
        return claimed

    def complete_job(self, job_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE jobs SET state = ?, locked_at = NULL WHERE id = ?",
                (JobState.DONE.value, job_id),
            )
            self._conn.commit()

    def reschedule_job(self, job_id: int, run_at: str, error: str | None = None) -> None:
        with self._lock:
            self._conn.execute(
                """UPDATE jobs SET state = ?, run_at = ?, attempts = attempts + 1,
                       last_error = ?, locked_at = NULL WHERE id = ?""",
                (JobState.PENDING.value, run_at, error, job_id),
            )
            self._conn.commit()

    def fail_job(self, job_id: int, error: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE jobs SET state = ?, last_error = ?, locked_at = NULL WHERE id = ?",
                (JobState.FAILED.value, error, job_id),
            )
            self._conn.commit()

    def recover_stale_jobs(self, cutoff: str) -> int:
        """Return stuck RUNNING jobs to PENDING (crash recovery).

        A job is stuck when it has been RUNNING longer than `cutoff`, or when the
        process that claimed it no longer exists (killed session / dead container
        process) — the second case is what makes recovery immediate instead of
        waiting for the whole stale window.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, locked_at, locked_by FROM jobs WHERE state = ?",
                (JobState.RUNNING.value,),
            ).fetchall()
            recovered = 0
            for row in rows:
                if (
                    row["locked_at"] is None
                    or row["locked_at"] < cutoff
                    or _owner_is_dead(row["locked_by"])
                ):
                    cur = self._conn.execute(
                        """UPDATE jobs SET state = ?, locked_at = NULL, locked_by = NULL
                           WHERE id = ? AND state = ?""",
                        (JobState.PENDING.value, row["id"], JobState.RUNNING.value),
                    )
                    recovered += cur.rowcount
            self._conn.commit()
            return recovered

    def has_open_job(self, kind: str, source_id: str | None = None) -> bool:
        """True if a pending/running job of `kind` exists.

        With `source_id`, match that source; without it (singleton recurring jobs
        like `journal`/`warmup`), match any open job of the kind.
        """
        with self._lock:
            if source_id is not None:
                pattern = f'%"source_id": "{source_id}"%'
                row = self._conn.execute(
                    """SELECT 1 FROM jobs
                       WHERE kind = ? AND state IN (?, ?) AND payload LIKE ?
                       LIMIT 1""",
                    (kind, JobState.PENDING.value, JobState.RUNNING.value, pattern),
                ).fetchone()
            else:
                row = self._conn.execute(
                    """SELECT 1 FROM jobs
                       WHERE kind = ? AND state IN (?, ?) LIMIT 1""",
                    (kind, JobState.PENDING.value, JobState.RUNNING.value),
                ).fetchone()
        return row is not None

    def prune_duplicate_jobs(self) -> int:
        """Delete duplicate PENDING jobs sharing (kind, payload), keeping the oldest."""
        pending = JobState.PENDING.value
        with self._lock:
            cur = self._conn.execute(
                """DELETE FROM jobs
                   WHERE state = ? AND id NOT IN (
                       SELECT MIN(id) FROM jobs WHERE state = ? GROUP BY kind, payload
                   )""",
                (pending, pending),
            )
            self._conn.commit()
            return cur.rowcount

    def prune_done_jobs(self, before_iso: str) -> int:
        """Delete finished jobs scheduled before `before_iso` (keep the table small)."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM jobs WHERE state = ? AND run_at < ?",
                (JobState.DONE.value, before_iso),
            )
            self._conn.commit()
            return cur.rowcount

    def count_jobs(self, state: JobState | None = None) -> int:
        with self._lock:
            if state:
                row = self._conn.execute(
                    "SELECT COUNT(*) AS n FROM jobs WHERE state = ?", (state.value,)
                ).fetchone()
            else:
                row = self._conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()
        return int(row["n"]) if row else 0

    # ── counters / kv ────────────────────────────────────────────────────
    def incr_counter(self, key: str, amount: int = 1) -> int:
        with self._lock:
            self._conn.execute(
                """INSERT INTO counters (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = value + ?""",
                (key, amount, amount),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT value FROM counters WHERE key = ?", (key,)
            ).fetchone()
        return int(row["value"]) if row else 0

    def get_counter(self, key: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM counters WHERE key = ?", (key,)
            ).fetchone()
        return int(row["value"]) if row else 0

    # ── discoveries (candidate providers, P3) ────────────────────────────
    def save_discoveries(self, records: list) -> int:
        """Insert candidate providers, ignoring already-known ones. Returns new count."""
        new = 0
        with self._lock:
            for record in records:
                cur = self._conn.execute(
                    """INSERT INTO discoveries (id, host, data, source, created_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO NOTHING""",
                    (
                        record.id,
                        record.host,
                        record.model_dump_json(),
                        record.source,
                        utcnow_iso(),
                    ),
                )
                new += cur.rowcount
            self._conn.commit()
        return new

    def list_discoveries(self, status: str | None = None) -> list:
        from mnemosyne.discovery.models import DiscoveryRecord

        with self._lock:
            rows = self._conn.execute(
                "SELECT data FROM discoveries ORDER BY created_at DESC"
            ).fetchall()
        records = [DiscoveryRecord.model_validate_json(r["data"]) for r in rows]
        if status is not None:
            records = [r for r in records if r.status == status]
        return records

    def set_discovery_status(self, discovery_id: str, status: str) -> None:
        from mnemosyne.discovery.models import DiscoveryRecord

        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM discoveries WHERE id = ?", (discovery_id,)
            ).fetchone()
            if not row:
                return
            record = DiscoveryRecord.model_validate_json(row["data"])
            record.status = status
            self._conn.execute(
                "UPDATE discoveries SET data = ? WHERE id = ?",
                (record.model_dump_json(), discovery_id),
            )
            self._conn.commit()

    def count_discoveries(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM discoveries").fetchone()
        return int(row["n"]) if row else 0

    # ── inter-agent mailbox (bi-agent) ───────────────────────────────────
    def post_message(self, sender: str, recipient: str, body: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO messages (sender, recipient, body, status, created_at)
                   VALUES (?, ?, ?, 'pending', ?)""",
                (sender, recipient, body, utcnow_iso()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def next_pending_message(self, recipient: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                """SELECT * FROM messages WHERE status = 'pending' AND recipient = ?
                   ORDER BY id ASC LIMIT 1""",
                (recipient,),
            ).fetchone()
        return dict(row) if row else None

    def claim_next_message(
        self, recipient: str, owner: str, stale_after_s: float = 18000
    ) -> dict | None:
        """Claim the oldest pending message for `recipient` (single)."""
        claimed = self.claim_messages(
            recipient, owner, limit=1, stale_after_s=stale_after_s
        )
        return claimed[0] if claimed else None

    def _release_stuck_messages(self, stale_iso: str) -> int:
        """Release RUNNING messages that are old or whose claimer is dead."""
        released = 0
        running = self._conn.execute(
            "SELECT id, claimed_at, claimed_by FROM messages WHERE status = 'running'"
        ).fetchall()
        for row in running:
            if (
                row["claimed_at"] is None
                or row["claimed_at"] < stale_iso
                or _owner_is_dead(row["claimed_by"])
            ):
                released += self._conn.execute(
                    """UPDATE messages
                       SET status = 'pending', claimed_at = NULL, claimed_by = NULL
                       WHERE id = ? AND status = 'running'""",
                    (row["id"],),
                ).rowcount
        return released

    def recover_stale_messages(self, stale_after_s: float = 18000) -> int:
        """Give back messages stuck RUNNING (crashed/killed session).

        Called on every heartbeat tick, so a killed turn is retried even when
        the mailbox is otherwise empty.
        """
        stale_iso = (
            datetime.now(UTC) - timedelta(seconds=stale_after_s)
        ).replace(microsecond=0).isoformat()
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                released = self._release_stuck_messages(stale_iso)
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return released

    def claim_messages(
        self,
        recipient: str,
        owner: str,
        *,
        limit: int = 5,
        stale_after_s: float = 18000,
    ) -> list[dict]:
        """Atomically claim up to `limit` PENDING messages for `recipient`.

        Batching matters: several messages posted back-to-back by the same agent
        (a report then an update) must cost ONE turn, not one turn each.

        Global turn-taking is enforced: if a message is still RUNNING (claimed
        less than `stale_after_s` ago), nothing is claimed. RUNNING messages
        older than that (crashed process) are released first, in the same
        transaction.
        """
        now = datetime.now(UTC).replace(microsecond=0)
        now_iso = now.isoformat()
        stale_iso = (now - timedelta(seconds=stale_after_s)).isoformat()
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                self._release_stuck_messages(stale_iso)
                busy = self._conn.execute(
                    "SELECT 1 FROM messages WHERE status = 'running' LIMIT 1"
                ).fetchone()
                if busy is not None:
                    self._conn.commit()
                    return []
                rows = self._conn.execute(
                    """SELECT * FROM messages
                       WHERE status = 'pending' AND recipient = ?
                       ORDER BY id ASC LIMIT ?""",
                    (recipient, max(1, limit)),
                ).fetchall()
                claimed: list[dict] = []
                for row in rows:
                    cur = self._conn.execute(
                        """UPDATE messages
                           SET status = 'running', claimed_at = ?, claimed_by = ?
                           WHERE id = ? AND status = 'pending'""",
                        (now_iso, _claim_owner(owner), row["id"]),
                    )
                    if cur.rowcount:
                        message = dict(row)
                        message.update(
                            status="running",
                            claimed_at=now_iso,
                            claimed_by=owner,
                            handled_at=None,
                        )
                        claimed.append(message)
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return claimed

    def archive_pending_messages(self, recipient: str, note: str | None = None) -> int:
        """Archive (stop processing) every pending message addressed to `recipient`."""
        with self._lock:
            cur = self._conn.execute(
                """UPDATE messages SET status = 'archived', handled_at = ?, note = ?
                   WHERE recipient = ? AND status = 'pending'""",
                (utcnow_iso(), note, recipient),
            )
            self._conn.commit()
            return cur.rowcount

    # ── cross-process leases (single browser driver) ─────────────────────
    def try_lease(self, name: str, ttl_s: float, owner: str = "") -> bool:
        """Acquire `name` for `ttl_s` seconds. False if someone alive holds it.

        Leases are intentional and coarse: only one process may drive Chrome at
        a time (bi-agent browser turn, warmup mission, picture/video work).
        A lease whose holder died (kill, crash) is reclaimed immediately instead
        of blocking the driver for the whole TTL.
        """
        key = f"lease:{name}"
        now = time.time()
        payload = json.dumps(
            {
                "owner": owner,
                "pid": os.getpid(),
                "host": socket.gethostname(),
                "started": _proc_start_time(),
                "expires": now + ttl_s,
            }
        )
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                row = self._conn.execute(
                    "SELECT value FROM kv WHERE key = ?", (key,)
                ).fetchone()
                if row is not None:
                    held = _read_lease(row["value"])
                    if held and not _lease_is_stale(held, now):
                        self._conn.commit()
                        return False
                self._conn.execute(
                    """INSERT INTO kv (key, value) VALUES (?, ?)
                       ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                    (key, payload),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return True

    def release_legacy_leases(self) -> int:
        """Drop lease rows written before process-incarnation tracking.

        Called once at heartbeat start: a row without a process incarnation
        cannot be attributed, and no live holder can be one of ours right after
        boot, so keeping it would only block the driver.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, value FROM kv WHERE key LIKE 'lease:%'"
            ).fetchall()
            dropped = 0
            for row in rows:
                if "started" not in (row["value"] or ""):
                    self._conn.execute("DELETE FROM kv WHERE key = ?", (row["key"],))
                    dropped += 1
            self._conn.commit()
            return dropped

    def release_lease(self, name: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM kv WHERE key = ?", (f"lease:{name}",))
            self._conn.commit()

    def list_messages(self, status: str | None = None, limit: int = 50) -> list[dict]:
        with self._lock:
            if status:
                rows = self._conn.execute(
                    "SELECT * FROM messages WHERE status = ? ORDER BY id ASC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM messages ORDER BY id ASC LIMIT ?", (limit,)
                ).fetchall()
        return [dict(r) for r in rows]

    def mark_message(
        self, message_id: int, status: str = "handled", note: str | None = None
    ) -> None:
        """Set a message state. `handled_at` is only stamped on terminal states."""
        terminal = status in ("handled", "failed", "review", "archived")
        with self._lock:
            self._conn.execute(
                """UPDATE messages
                   SET status = ?, handled_at = ?, note = ?,
                       claimed_at = NULL, claimed_by = NULL
                   WHERE id = ?""",
                (status, utcnow_iso() if terminal else None, note, message_id),
            )
            self._conn.commit()

    def count_messages(self, status: str | None = None) -> int:
        with self._lock:
            if status:
                row = self._conn.execute(
                    "SELECT COUNT(*) AS n FROM messages WHERE status = ?", (status,)
                ).fetchone()
            else:
                row = self._conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()
        return int(row["n"]) if row else 0

    def count_pending_from(self, sender: str) -> int:
        """Pending messages posted by one sender (e.g. a single warmup mission)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM messages WHERE status = 'pending' AND sender = ?",
                (sender,),
            ).fetchone()
        return int(row["n"]) if row else 0

    def set_kv(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO kv (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (key, json.dumps(value)),
            )
            self._conn.commit()

    def delete_kv(self, key: str) -> None:
        """Remove a key (no row left behind, unlike set_kv(None))."""
        with self._lock:
            self._conn.execute("DELETE FROM kv WHERE key = ?", (key,))
            self._conn.commit()

    # ── watchdog reads (mnemosyne.monitor) ───────────────────────────────
    def running_messages(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, sender, recipient, claimed_at FROM messages"
                " WHERE status = 'running'"
            ).fetchall()
        return [dict(r) for r in rows]

    def pending_messages(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, sender, recipient, created_at FROM messages"
                " WHERE status = 'pending'"
            ).fetchall()
        return [dict(r) for r in rows]

    def review_message_count(self) -> int:
        return self.count_messages(status="review")

    def running_jobs(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, kind, locked_at FROM jobs WHERE state = 'running'"
            ).fetchall()
        return [dict(r) for r in rows]

    def lease_exists(self, name: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM kv WHERE key = ?", (f"lease:{name}",)
            ).fetchone()
        return row is not None

    def lease_holder_dead_pid(self, name: str) -> int | None:
        """Pid of a lease holder that cannot be alive for us (same definition
        as reclaim: foreign container, dead pid, or a reused pid — never a bare
        `os.kill` probe). An expired lease is reclaimable, not an alert."""
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM kv WHERE key = ?", (f"lease:{name}",)
            ).fetchone()
        if row is None:
            return None
        held = _read_lease(row["value"])
        if not held or float(held.get("expires", 0)) <= time.time():
            return None
        if not _holder_is_gone(held):
            return None
        pid = held.get("pid")
        return pid if isinstance(pid, int) and pid > 0 else None

    def get_kv(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        kind=row["kind"],
        payload=json.loads(row["payload"]),
        state=JobState(row["state"]),
        priority=row["priority"],
        attempts=row["attempts"],
        max_attempts=row["max_attempts"],
        run_at=row["run_at"],
        locked_at=row["locked_at"],
        last_error=row["last_error"],
    )
