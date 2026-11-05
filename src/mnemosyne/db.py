"""SQLite persistence (WAL) for the catalog, asset store and durable job queue."""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from mnemosyne.models import Asset, Job, JobState, SourceState
from mnemosyne.util import ensure_dir, utcnow_iso

#: Identifies THIS process incarnation in leases and job claims. Docker gives
#: every container generation a new hostname AND the host/container share the
#: kernel, so neither hostname nor pid can tell a live holder from a dead one
#: across pid namespaces — only the holder's own renewals can.
_INSTANCE = uuid.uuid4().hex

#: Lease TTL: renewed by the holder every minute while it works (see
#: `renew_own`), so a crashed generation frees the driver after a few minutes.
LEASE_TTL_S = 300.0

#: the note stored on a message/task row (a WeTransfer link must fit)
NOTE_MAX_CHARS = 1000

#: task statuses that close a session
TASK_TERMINAL = ("done", "failed", "review", "cancelled")

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

CREATE TABLE IF NOT EXISTS operator_asks (
    id            TEXT PRIMARY KEY,
    task_id       INTEGER NOT NULL,
    agent         TEXT NOT NULL,
    question      TEXT NOT NULL,
    options       TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    answer        TEXT,
    message_id    INTEGER,
    tg_chat_id    TEXT,
    tg_message_id INTEGER,
    tg_prompt_id  INTEGER,
    created_at    TEXT NOT NULL,
    answered_at   TEXT
);

-- Observatory: the sidebar lists sessions (one queue task OR one job run);
-- agent activations/handoffs are EVENTS inside a session, never sessions.
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,          -- 'task:<id>' | 'job:<id>'
    family     TEXT NOT NULL,             -- task | job
    type       TEXT NOT NULL,             -- warmup, connexion, connect, harvest, agency…
    title      TEXT NOT NULL,
    agent      TEXT,                      -- starting agent (tasks) / null (jobs)
    status     TEXT NOT NULL,
    notable    INTEGER NOT NULL DEFAULT 1, -- 0 = silent run (hidden unless asked)
    started_at TEXT NOT NULL,
    ended_at   TEXT,
    updated_at TEXT NOT NULL,
    meta       TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_notable ON sessions(notable, started_at DESC);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    ts         TEXT NOT NULL,
    kind       TEXT NOT NULL,
    actor      TEXT,
    payload    TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, id);

"""


def _like_escape(value: str) -> str:
    """Escape a value for a LIKE pattern (source ids carry ``_``/``%``)."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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

    Only a holder we can actually probe (same hostname = same pid namespace) is
    ever declared gone: a foreign hostname is the host while we run in the
    container (or an older container generation) and its liveness cannot be
    probed from here. Those holders are reclaimed by EXPIRY instead — and the
    holder keeps its expiry fresh by renewing (`renew_own`), so a dead
    generation frees the lease in minutes while a live one never loses it.
    """
    host = payload.get("host")
    if host is None:  # legacy payload: cannot attribute, respect it until expiry
        return False
    if host != socket.gethostname():
        return False
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
    """Identify the claimer (kind, pid, host, instance) so a dead one is detectable."""
    return json.dumps(
        {
            "who": who,
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "started": _proc_start_time(),
            "instance": _INSTANCE,
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
                    try:
                        self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
                    except sqlite3.OperationalError as exc:
                        # two processes may initialise the same file at once: the
                        # loser of the race finds the column already added
                        if "duplicate column name" not in str(exc):
                            raise
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
        """Insert the assets, returning the number of *new* rows.

        ``ON CONFLICT(id) DO NOTHING`` skips known assets, so the return value
        must count the real insertions (callers use it to flag a source as
        CONNECTED): ``len(assets)`` would report fresh assets on every re-run.
        """
        if not assets:
            return 0
        inserted = 0
        with self._lock:
            for asset in assets:
                cursor = self._conn.execute(
                    """INSERT INTO assets (id, source_id, source_asset_id, data, created_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO NOTHING""",
                    (
                        asset.id,
                        asset.source_id,
                        asset.source_asset_id,
                        asset.model_dump_json(),
                        utcnow_iso(),
                    ),
                )
                inserted += cursor.rowcount
            self._conn.commit()
        return inserted

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
                pattern = f'%"source_id": "{_like_escape(source_id)}"%'
                row = self._conn.execute(
                    """SELECT 1 FROM jobs
                       WHERE kind = ? AND state IN (?, ?) AND payload LIKE ? ESCAPE '\\'
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
        """Create a queue entry (and its observatory session)."""
        now = utcnow_iso()
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO tasks (start_agent, objective, turn_cap, payload, status, created_at)
                   VALUES (?, ?, ?, ?, 'pending', ?)""",
                (start_agent, objective, turn_cap,
                 json.dumps(payload) if payload else None, now),
            )
            task_id = int(cur.lastrowid)
            self._open_task_session(task_id, start_agent, objective, turn_cap, payload, now)
            self._conn.commit()
            return task_id

    def _open_task_session(
        self, task_id: int, start_agent: str, objective: str,
        turn_cap: int | None, payload: dict | None, created_at: str,
    ) -> str:
        """Materialize a task as a session + its first event (lock held)."""
        session_id = f"task:{task_id}"
        kind = (payload or {}).get("kind")
        session_type = str(kind) if kind else start_agent
        title = (objective.strip().splitlines() or ["(sans objectif)"])[0][:300]
        self._conn.execute(
            """INSERT OR IGNORE INTO sessions
                   (id, family, type, title, agent, status, notable, started_at,
                    updated_at, meta)
               VALUES (?, 'task', ?, ?, ?, 'pending', 1, ?, ?, ?)""",
            (
                session_id, session_type, title, start_agent, created_at, created_at,
                json.dumps(
                    {"task_id": task_id, "turn_cap": turn_cap, "payload": payload or {}}
                ),
            ),
        )
        self._conn.execute(
            "INSERT INTO events (session_id, ts, kind, actor, payload) "
            "VALUES (?, ?, 'session.created', 'orchestrator', ?)",
            (
                session_id, created_at,
                json.dumps(
                    {"family": "task", "type": session_type, "agent": start_agent,
                     "title": title}
                ),
            ),
        )
        return session_id

    def next_task(self) -> dict | None:
        """The task to work on.

        Priority: the task worked on most recently continues (its session is
        warm); then running tasks with a pending answer/agent-message (oldest
        activation first); then new pending tasks (FIFO). Tasks waiting on the
        operator are SKIPPED — a parked task costs nothing and never blocks the
        queue; its answer wakes it back into the running set.
        """
        parked = (
            "EXISTS (SELECT 1 FROM messages m WHERE m.task_id = t.id "
            "AND m.status = 'pending' AND m.recipient = 'operator') "
            "AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.task_id = t.id "
            "AND m.status = 'pending' AND m.recipient IN ('coder', 'browser'))"
        )
        with self._lock:
            row = self._conn.execute(
                f"""SELECT * FROM tasks t WHERE t.status = 'running'
                    AND NOT ({parked})
                    ORDER BY COALESCE(t.last_activation_at, t.created_at) DESC,
                             t.id ASC
                    LIMIT 1"""
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
        """Set task state (and mirror it on the observatory session)."""
        now = utcnow_iso()
        with self._lock:
            row = self._conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
            previous = row["status"] if row else None
            updates = ["status = ?"]
            params: list[Any] = [status]
            if status == "running" and (row is None or row["status"] != "running"):
                updates.append("started_at = ?")
                params.append(now)
            if status in TASK_TERMINAL:
                updates.append("finished_at = ?")
                params.append(now)
            if note is not None:
                updates.append("note = ?")
                params.append(note[:NOTE_MAX_CHARS])
            params.append(task_id)
            self._conn.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params
            )
            if previous is not None and previous != status:
                session_id = f"task:{task_id}"
                fields = ["status = ?", "updated_at = ?"]
                session_params: list[Any] = [status, now]
                if status in TASK_TERMINAL:
                    fields.append("ended_at = ?")
                    session_params.append(now)
                session_params.append(session_id)
                self._conn.execute(
                    f"UPDATE sessions SET {', '.join(fields)} WHERE id = ?",
                    session_params,
                )
                self._conn.execute(
                    "INSERT INTO events (session_id, ts, kind, actor, payload) "
                    "VALUES (?, ?, 'task.status', 'orchestrator', ?)",
                    (
                        session_id, now,
                        json.dumps(
                            {"from": previous, "to": status, "note": (note or "")[:280]}
                        ),
                    ),
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

    # ── observatory: sessions / events ───────────────────────────────────
    def upsert_session(
        self,
        session_id: str,
        *,
        family: str,
        type: str,
        title: str,
        agent: str | None = None,
        status: str = "pending",
        notable: bool = True,
        started_at: str | None = None,
        ended_at: str | None = None,
        meta: dict | None = None,
    ) -> None:
        """Create or refresh a session (title/status may change over time)."""
        now = utcnow_iso()
        with self._lock:
            self._conn.execute(
                """INSERT INTO sessions
                       (id, family, type, title, agent, status, notable,
                        started_at, ended_at, updated_at, meta)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       type = excluded.type,
                       title = excluded.title,
                       agent = excluded.agent,
                       status = excluded.status,
                       notable = excluded.notable,
                       ended_at = excluded.ended_at,
                       updated_at = excluded.updated_at,
                       meta = excluded.meta""",
                (
                    session_id, family, type, title[:300], agent, status,
                    1 if notable else 0, started_at or now, ended_at, now,
                    json.dumps(meta, default=str) if meta else None,
                ),
            )
            self._conn.commit()

    def update_session(
        self,
        session_id: str,
        *,
        status: str | None = None,
        ended_at: str | None = None,
        notable: bool | None = None,
        title: str | None = None,
        meta: dict | None = None,
    ) -> None:
        fields = ["updated_at = ?"]
        params: list[Any] = [utcnow_iso()]
        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if ended_at is not None:
            fields.append("ended_at = ?")
            params.append(ended_at)
        if notable is not None:
            fields.append("notable = ?")
            params.append(1 if notable else 0)
        if title is not None:
            fields.append("title = ?")
            params.append(title[:300])
        if meta is not None:
            fields.append("meta = ?")
            params.append(json.dumps(meta, default=str))
        params.append(session_id)
        with self._lock:
            self._conn.execute(
                f"UPDATE sessions SET {', '.join(fields)} WHERE id = ?", params
            )
            self._conn.commit()

    def add_event(
        self,
        session_id: str,
        kind: str,
        actor: str | None = None,
        payload: dict | None = None,
        ts: str | None = None,
    ) -> int:
        """Append one observatory event (an explicit `ts` is used by backfills)."""
        now = ts or utcnow_iso()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO events (session_id, ts, kind, actor, payload) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    session_id, now, kind, actor,
                    json.dumps(payload, default=str) if payload else None,
                ),
            )
            self._conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def list_sessions(
        self,
        limit: int = 60,
        *,
        before: str | None = None,
        include_silent: bool = False,
        family: str | None = None,
    ) -> list[dict]:
        sql = (
            "SELECT s.*, (SELECT COUNT(*) FROM events e WHERE e.session_id = s.id) "
            "AS event_count FROM sessions s WHERE 1 = 1"
        )
        params: list[Any] = []
        if not include_silent:
            sql += " AND s.notable = 1"
        if family:
            sql += " AND s.family = ?"
            params.append(family)
        if before:
            sql += " AND s.started_at < ?"
            params.append(before)
        sql += " ORDER BY s.started_at DESC, s.id DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_session(self, session_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT s.*, (SELECT COUNT(*) FROM events e WHERE e.session_id = s.id) "
                "AS event_count FROM sessions s WHERE s.id = ?",
                (session_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_events(
        self,
        session_id: str,
        *,
        after: int | None = None,
        upto: int | None = None,
        limit: int = 5000,
    ) -> list[dict]:
        sql = "SELECT * FROM events WHERE session_id = ?"
        params: list[Any] = [session_id]
        if after is not None:
            sql += " AND id > ?"
            params.append(after)
        if upto is not None:
            sql += " AND id <= ?"
            params.append(upto)
        sql += " ORDER BY id LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def events_after(
        self, after_id: int, *, session_id: str | None = None, limit: int = 300
    ) -> list[dict]:
        sql = "SELECT * FROM events WHERE id > ?"
        params: list[Any] = [after_id]
        if session_id:
            sql += " AND session_id = ?"
            params.append(session_id)
        sql += " ORDER BY id LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def max_event_id(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(id), 0) AS n FROM events"
            ).fetchone()
        return int(row["n"])

    def open_job_session(
        self, job_id: int, kind: str, *, title: str | None = None
    ) -> str:
        """One job RUN = one session (the job row is unique per execution)."""
        session_id = f"job:{job_id}"
        now = utcnow_iso()
        self.upsert_session(
            session_id,
            family="job",
            type=kind,
            title=title or kind,
            status="running",
            notable=False,
            started_at=now,
            meta={"job_id": job_id, "kind": kind},
        )
        self.add_event(session_id, "job.start", "orchestrator", {"kind": kind})
        return session_id

    def close_job_session(
        self,
        job_id: int,
        *,
        status: str = "done",
        activity: str | None = None,
        error: str | None = None,
    ) -> None:
        session_id = f"job:{job_id}"
        self.update_session(
            session_id,
            status=status,
            ended_at=utcnow_iso(),
            notable=bool(activity),
            title=activity or None,
        )
        self.add_event(
            session_id,
            "job.end",
            "orchestrator",
            {
                "status": status,
                "activity": activity,
                "error": (error or "")[:400] or None,
            },
        )

    def has_open_task(
        self, kind: str | None = None, source_id: str | None = None
    ) -> bool:
        """True if a pending/running task exists (optionally of a given kind/source)."""
        with self._lock:
            if kind or source_id:
                conditions, params = [], []
                if kind:
                    conditions.append("payload LIKE ? ESCAPE '\\'")
                    params.append(f'%"kind": "{_like_escape(kind)}"%')
                if source_id:
                    conditions.append("payload LIKE ? ESCAPE '\\'")
                    params.append(f'%"source_id": "{_like_escape(source_id)}"%')
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

    # ── operator asks (question -> answer, over Telegram or CLI) ─────────
    def create_ask(
        self, ask_id: str, task_id: int, agent: str, question: str,
        options: list[dict], message_id: int | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO operator_asks
                   (id, task_id, agent, question, options, status, message_id, created_at)
                   VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (ask_id, task_id, agent, question, json.dumps(options), message_id, utcnow_iso()),
            )
            self._conn.commit()

    def get_ask(self, ask_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM operator_asks WHERE id = ?", (ask_id,)
            ).fetchone()
        return dict(row) if row else None

    def set_ask_telegram(self, ask_id: str, chat_id: str, message_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE operator_asks SET tg_chat_id = ?, tg_message_id = ? WHERE id = ?",
                (chat_id, message_id, ask_id),
            )
            self._conn.commit()

    def set_ask_prompt(self, ask_id: str, prompt_id: int) -> None:
        """Remember the ForceReply prompt so the free-text answer can be matched."""
        with self._lock:
            self._conn.execute(
                "UPDATE operator_asks SET tg_prompt_id = ? WHERE id = ?", (prompt_id, ask_id)
            )
            self._conn.commit()

    def answer_ask(self, ask_id: str, answer: str) -> None:
        with self._lock:
            self._conn.execute(
                """UPDATE operator_asks SET status = 'answered', answer = ?, answered_at = ?
                   WHERE id = ?""",
                (answer, utcnow_iso(), ask_id),
            )
            self._conn.commit()

    def list_asks(self, status: str | None = None) -> list[dict]:
        with self._lock:
            if status:
                rows = self._conn.execute(
                    "SELECT * FROM operator_asks WHERE status = ? ORDER BY created_at ASC",
                    (status,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM operator_asks ORDER BY created_at ASC"
                ).fetchall()
        return [dict(r) for r in rows]

    def task_waiting_on_operator(self, task_id: int) -> bool:
        with self._lock:
            row = self._conn.execute(
                """SELECT 1 FROM messages
                   WHERE task_id = ? AND status = 'pending' AND recipient = 'operator'
                   LIMIT 1""",
                (task_id,),
            ).fetchone()
        return row is not None

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
                "instance": _INSTANCE,
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

    def release_own_lease(self, name: str) -> bool:
        """Delete the lease only when WE hold it (never a foreign pilot's)."""
        key = f"lease:{name}"
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
            if row is None:
                return False
            held = _read_lease(row["value"])
            if not held or held.get("instance") != _INSTANCE:
                return False
            self._conn.execute("DELETE FROM kv WHERE key = ?", (key,))
            self._conn.commit()
        return True

    def renew_own_lease(self, name: str, ttl_s: float = LEASE_TTL_S) -> bool:
        """Push OUR lease's expiry forward; never touches a foreign holder."""
        key = f"lease:{name}"
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
            if row is None:
                return False
            held = _read_lease(row["value"])
            if not held or held.get("instance") != _INSTANCE:
                return False
            held["expires"] = time.time() + ttl_s
            self._conn.execute(
                "UPDATE kv SET value = ? WHERE key = ?", (json.dumps(held), key)
            )
            self._conn.commit()
        return True

    def renew_own_jobs(self) -> int:
        """Refresh `locked_at` of the RUNNING jobs claimed by this incarnation."""
        pattern = f'%"instance": "{_INSTANCE}"%'
        with self._lock:
            cur = self._conn.execute(
                "UPDATE jobs SET locked_at = ? WHERE state = ? AND locked_by LIKE ?",
                (utcnow_iso(), JobState.RUNNING.value, pattern),
            )
            self._conn.commit()
            return cur.rowcount

    def renew_own(self) -> None:
        """One renewal pass for this incarnation (leases + job claims)."""
        self.renew_own_jobs()
        for name in ("agency", "browser"):
            self.renew_own_lease(name)

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
