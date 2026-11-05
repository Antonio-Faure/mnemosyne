"""Backfill the observatory from the task/job tables.

The observatory started recording *structured* events on 2026-10-31; this
backfill turns the existing tasks and notable job runs into sessions with a
minimal timeline (creation, status changes, job start/end), so the sidebar and
the replay show the past too. Idempotent: a session that already exists is
skipped, never duplicated.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from mnemosyne.db import TASK_TERMINAL, Database

#: job kinds worth an entry in the sidebar (agency/journal/watchdog runs every
#: minute: they are noise, the tasks they execute are the real sessions)
NOTABLE_JOB_KINDS = ("warmup", "harvest", "verify", "discover")

#: terminal task statuses that close a session (task.status events)
_TERMINAL = set(TASK_TERMINAL)


def _task_type(start_agent: str, payload: dict) -> str:
    kind = payload.get("kind")
    return str(kind) if kind else start_agent


def _job_title(job: dict) -> str:
    """`harvest gallica` reads better than `harvest` in the sidebar."""
    try:
        payload = json.loads(job["payload"] or "{}")
    except ValueError:
        payload = {}
    source = payload.get("source_id")
    return f"{job['kind']} {source}" if source else job["kind"]


def _task_events(db: Database, task: dict) -> None:
    session_id = f"task:{task['id']}"
    created = task["created_at"]
    db.add_event(
        session_id,
        "session.created",
        "orchestrator",
        {
            "family": "task",
            "type": _task_type(task["start_agent"], json.loads(task["payload"] or "{}")),
            "agent": task["start_agent"],
            "title": (task["objective"].strip().splitlines() or ["(sans objectif)"])[0][:300],
            "backfilled": True,
        },
        ts=created,
    )
    if task["started_at"]:
        db.add_event(
            session_id,
            "task.status",
            "orchestrator",
            {"from": "pending", "to": "running", "note": None, "backfilled": True},
            ts=task["started_at"],
        )
    if task["status"] in _TERMINAL and task["finished_at"]:
        previous = "running" if task["started_at"] else "pending"
        db.add_event(
            session_id,
            "task.status",
            "orchestrator",
            {
                "from": previous,
                "to": task["status"],
                "note": (task["note"] or "")[:280] or None,
                "backfilled": True,
            },
            ts=task["finished_at"],
        )


def _job_events(db: Database, job: dict) -> None:
    session_id = f"job:{job['id']}"
    run_at = job["run_at"]
    db.add_event(
        session_id,
        "job.start",
        "orchestrator",
        {"kind": job["kind"], "backfilled": True},
        ts=run_at,
    )
    db.add_event(
        session_id,
        "job.end",
        "orchestrator",
        {
            "status": job["state"],
            "activity": None,
            "error": (job["last_error"] or "")[:400] or None,
            "backfilled": True,
        },
        ts=run_at,
    )


def backfill(db: Database, *, days: int = 14) -> dict[str, int]:
    """Create sessions/events for existing tasks and one job run per kind/day."""
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    created = {"tasks": 0, "jobs": 0, "skipped": 0}

    with db._lock:
        tasks = [
            dict(row)
            for row in db._conn.execute(
                "SELECT * FROM tasks WHERE created_at >= ? ORDER BY id", (since,)
            ).fetchall()
        ]
    for task in tasks:
        session_id = f"task:{task['id']}"
        if db.get_session(session_id):
            created["skipped"] += 1
            continue
        payload = json.loads(task["payload"] or "{}")
        title = (task["objective"].strip().splitlines() or ["(sans objectif)"])[0][:300]
        db.upsert_session(
            session_id,
            family="task",
            type=_task_type(task["start_agent"], payload),
            title=title,
            agent=task["start_agent"],
            status=task["status"],
            notable=True,
            started_at=task["created_at"],
            ended_at=task["finished_at"],
            meta={"task_id": task["id"], "payload": payload, "backfilled": True},
        )
        _task_events(db, task)
        created["tasks"] += 1

    jobs: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for kind in NOTABLE_JOB_KINDS:
        with db._lock:
            rows = db._conn.execute(
                """SELECT * FROM jobs
                   WHERE kind = ? AND state IN ('done', 'failed') AND run_at >= ?
                   ORDER BY run_at DESC""",
                (kind, since),
            ).fetchall()
        kept = 0
        for row in rows:
            row = dict(row)
            key = (kind, row["run_at"][:10])
            if key in seen:
                continue
            seen.add(key)
            jobs.append(row)
            kept += 1
            if kept >= days:
                break
    for job in sorted(jobs, key=lambda row: row["run_at"]):
        session_id = f"job:{job['id']}"
        if db.get_session(session_id):
            created["skipped"] += 1
            continue
        db.upsert_session(
            session_id,
            family="job",
            type=job["kind"],
            title=_job_title(job),
            status=job["state"],
            notable=True,
            started_at=job["run_at"],
            ended_at=job["run_at"],
            meta={"job_id": job["id"], "kind": job["kind"], "backfilled": True},
        )
        _job_events(db, job)
        created["jobs"] += 1

    return created
