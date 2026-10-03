"""SQLite persistence (WAL) for the catalog, asset store and durable job queue."""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from mnemosyne.models import Asset, Job, JobState, SourceState
from mnemosyne.util import ensure_dir, utcnow_iso

#: the note stored on a message/task row (a WeTransfer link must fit)
NOTE_MAX_CHARS = 1000

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
    task_id     INTEGER,
    sender      TEXT NOT NULL,
    recipient   TEXT NOT NULL,
    body        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TEXT NOT NULL,
    handled_at  TEXT,
    note        TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status, recipient);

CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    start_agent  TEXT NOT NULL,
    objective    TEXT NOT NULL,
    turn_cap     INTEGER,
    payload      TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TEXT NOT NULL,
    started_at   TEXT,
    finished_at  TEXT,
    note         TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, id);

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
            ("messages", ("task_id", "handled_at", "note")),
            ("jobs", ("locked_by",)),
            ("tasks", ("last_activation_at",)),
        ):
            cols = {row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})")}
            for name in names:
                if name not in cols:
                    kind = "INTEGER" if name == "task_id" else "TEXT"
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
        # the per-task mailbox index needs the migrated column, so it lives here
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_task ON messages(task_id, recipient)"
        )
        # messages rebuilt by the task model: the old claim columns are dropped
        # from the schema; leave them in place (SQLite cannot easily drop), they
        # are simply never written again.

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

    # ── task queue (bi-agent) ────────────────────────────────────────────
    def enqueue_task(
        self, start_agent: str, objective: str, turn_cap: int | None = None,
        payload: dict | None = None,
    ) -> int:
        """Create a queue entry. One task = one objective, one starting agent."""
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO tasks (start_agent, objective, turn_cap, payload, status, created_at)
                   VALUES (?, ?, ?, ?, 'pending', ?)""",
                (start_agent, objective, turn_cap,
                 json.dumps(payload) if payload else None, utcnow_iso()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def next_task(self) -> dict | None:
        """The task to work on: a running one continues first, else FIFO pending."""
        with self._lock:
            row = self._conn.execute(
                """SELECT * FROM tasks WHERE status = 'running' ORDER BY id ASC LIMIT 1"""
            ).fetchone()
            if row is None:
                row = self._conn.execute(
                    """SELECT * FROM tasks WHERE status = 'pending' ORDER BY id ASC LIMIT 1"""
                ).fetchone()
        return dict(row) if row else None

    def get_task(self, task_id: int) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def set_task_status(
        self, task_id: int, status: str, note: str | None = None
    ) -> None:
        """Set task state. started_at on running, finished_at on terminal states."""
        now = utcnow_iso()
        with self._lock:
            row = self._conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
            updates = ["status = ?"]
            params: list[Any] = [status]
            if status == "running" and (row is None or row["status"] != "running"):
                updates.append("started_at = ?")
                params.append(now)
            if status in ("done", "failed", "review", "cancelled"):
                updates.append("finished_at = ?")
                params.append(now)
            if note is not None:
                updates.append("note = ?")
                params.append(note[:NOTE_MAX_CHARS])
            params.append(task_id)
            self._conn.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params
            )
            self._conn.commit()

    def touch_task_activation(self, task_id: int) -> None:
        """Stamp when the task was last worked on (the watchdog reads it)."""
        with self._lock:
            self._conn.execute(
                "UPDATE tasks SET last_activation_at = ? WHERE id = ?",
                (utcnow_iso(), task_id),
            )
            self._conn.commit()

    def has_open_task(
        self, kind: str | None = None, source_id: str | None = None
    ) -> bool:
        """True if a pending/running task exists (optionally of a given kind/source)."""
        with self._lock:
            if kind or source_id:
                conditions, params = [], []
                if kind:
                    conditions.append("payload LIKE ?")
                    params.append(f'%"kind": "{kind}"%')
                if source_id:
                    conditions.append("payload LIKE ?")
                    params.append(f'%"source_id": "{source_id}"%')
                row = self._conn.execute(
                    f"""SELECT 1 FROM tasks
                        WHERE status IN ('pending', 'running') AND {' AND '.join(conditions)}
                        LIMIT 1""",
                    params,
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT 1 FROM tasks WHERE status IN ('pending', 'running') LIMIT 1"
                ).fetchone()
        return row is not None

    def count_tasks(self, status: str | None = None) -> int:
        with self._lock:
            if status:
                row = self._conn.execute(
                    "SELECT COUNT(*) AS n FROM tasks WHERE status = ?", (status,)
                ).fetchone()
            else:
                row = self._conn.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()
        return int(row["n"]) if row else 0

    def list_tasks(self, status: str | None = None, limit: int = 50) -> list[dict]:
        with self._lock:
            if status:
                rows = self._conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY id DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
        return [dict(r) for r in rows]

    # ── per-task temporary mailbox ───────────────────────────────────────
    def post_message(
        self, sender: str, recipient: str, body: str, task_id: int
    ) -> int:
        """A message lives INSIDE one task's mailbox (never taskless)."""
        if task_id is None:
            raise ValueError("a message must belong to a task")
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO messages (task_id, sender, recipient, body, status, created_at)
                   VALUES (?, ?, ?, ?, 'pending', ?)""",
                (task_id, sender, recipient, body.strip(), utcnow_iso()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def pending_task_recipients(self, task_id: int) -> list[str]:
        """Recipients with unconsumed messages in this task's mailbox."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT DISTINCT recipient FROM messages
                   WHERE task_id = ? AND status = 'pending' ORDER BY recipient""",
                (task_id,),
            ).fetchall()
        return [r["recipient"] for r in rows]

    def pending_task_messages(self, task_id: int, recipient: str) -> list[dict]:
        """Unconsumed messages of the task addressed to one agent (id order)."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM messages
                   WHERE task_id = ? AND recipient = ? AND status = 'pending'
                   ORDER BY id ASC""",
                (task_id, recipient),
            ).fetchall()
        return [dict(r) for r in rows]

    def task_message_count(self, task_id: int) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM messages WHERE task_id = ? AND status = 'pending'",
                (task_id,),
            ).fetchone()
        return int(row["n"]) if row else 0

    def delete_task_messages(self, task_id: int) -> int:
        """The temporary mailbox dies with the task (the journal keeps the trace)."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM messages WHERE task_id = ?", (task_id,))
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
                "UPDATE messages SET status = ?, handled_at = ?, note = ? WHERE id = ?",
                (status, utcnow_iso() if terminal else None, note, message_id),
            )
            self._conn.commit()

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
