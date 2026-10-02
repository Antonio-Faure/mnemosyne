"""Invariants of the running system, checked on a timer and logged.

The watchdog answers one question: *is something stuck?* It never stops
anything. A long mission is not a problem: a mission is a problem when it has
stopped making progress, and that is what the agents report themselves
(`agents/progress.py` writes a `stall:<agent>` marker).

Alerts therefore mean "look at this", never "cut this off".
"""

from __future__ import annotations

import json
import os
import socket
from datetime import UTC, datetime, timedelta

from mnemosyne.config import Config
from mnemosyne.db import Database

#: a running message/job is only suspicious once it has stalled
STALE_MIN = 45
PENDING_MIN = 90
#: a stall marker older than this is reported (the agent gets 3 min of silence)
STALL_MARK_MIN = 2


def _iso_minus(minutes: float) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _age_minutes(stamp: str | None) -> float | None:
    if not stamp:
        return None
    try:
        return (datetime.now(UTC) - datetime.fromisoformat(stamp)).total_seconds() / 60
    except ValueError:
        return None


def _lease_dead(db: Database, name: str) -> int | None:
    """Pid of a lease whose holder cannot be alive (same host, dead process)."""
    row = db._conn.execute("SELECT value FROM kv WHERE key = ?", (f"lease:{name}",)).fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row["value"])
    except ValueError:
        return None
    pid = payload.get("pid")
    if (
        payload.get("host") == socket.gethostname()
        and isinstance(pid, int)
        and pid > 0
        and not _alive(pid)
    ):
        return pid
    return None


def _stall_marker(db: Database) -> dict | None:
    """Last stall reported by an agent, if recent enough to matter."""
    for agent in ("browser", "coder"):
        payload = db.get_kv(f"stall:{agent}")
        if not isinstance(payload, dict):
            continue
        age = _age_minutes(payload.get("at"))
        if age is None or age < STALL_MARK_MIN:
            continue
        return {"agent": agent, "minutes": round(age), "reason": payload.get("reason")}
    return None


def check_invariants(
    config: Config,
    stale_min: float = STALE_MIN,
    pending_min: float = PENDING_MIN,
) -> tuple[str, list[str]]:
    """One line of counters + a list of human-readable alerts."""
    db = Database(config.db_file())
    alerts: list[str] = []
    try:
        stall = _stall_marker(db)

        running = db._conn.execute(
            "SELECT id, sender, recipient, claimed_at FROM messages WHERE status = 'running'"
        ).fetchall()
        # A running message is NOT an alert, whatever its age: a long mission is
        # the normal case. Only the stall marker (written by the agent itself
        # when it stops progressing) turns into an alert.

        pending = db._conn.execute(
            "SELECT id, sender, recipient, created_at FROM messages WHERE status = 'pending'"
        ).fetchall()
        for row in pending:
            age = _age_minutes(row["created_at"])
            if age is not None and age > pending_min:
                alerts.append(
                    f"message #{row['id']} ({row['sender']}->{row['recipient']}) "
                    f"en attente depuis {age:.0f} min"
                )

        for lease_name in ("browser", "agency"):
            dead_pid = _lease_dead(db, lease_name)
            if dead_pid:
                alerts.append(f"bail {lease_name} détenu par un pid mort ({dead_pid})")

        jobs = db._conn.execute(
            "SELECT id, kind, locked_at FROM jobs WHERE state = 'running'"
        ).fetchall()
        for job in jobs:
            age = _age_minutes(job["locked_at"])
            if age is not None and age > stale_min:
                alerts.append(f"job #{job['id']} ({job['kind']}) running depuis {age:.0f} min")

        review = db._conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE status = 'review'"
        ).fetchone()["n"]
        stats = {
            "pending": len(pending),
            "running": len(running),
            "review": review,
            "lease": bool(db._conn.execute(
                "SELECT 1 FROM kv WHERE key = 'lease:browser'"
            ).fetchone()),
            "stall": stall["agent"] if stall else "-",
        }
    finally:
        db.close()

    if stall:
        alerts.insert(
            0,
            f"agent {stall['agent']} patine depuis {stall['minutes']} min "
            f"({stall['reason']}) — rapport attendu",
        )
    line = (
        f"{datetime.now(UTC):%H:%M:%S} pending={stats['pending']} running={stats['running']} "
        f"review={stats['review']} lease={'oui' if stats['lease'] else 'non'} "
        f"patine={stats['stall']} alerts={len(alerts)}"
    )
    return line, alerts


def report(config: Config, path, **kwargs) -> tuple[str, list[str]]:
    """Check and append to the soak log. Returns the line and the alerts."""
    line, alerts = check_invariants(config, **kwargs)
    stamp = datetime.now(UTC).isoformat()
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {line}\n")
        for alert in alerts:
            handle.write(f"{stamp} !! {alert}\n")
    return line, alerts


def mark_stall(db: Database, agent: str, reason: str) -> None:
    """Record that an agent reported itself stuck (cleared when it progresses)."""
    db.set_kv(f"stall:{agent}", {"at": datetime.now(UTC).isoformat(), "reason": reason})


def clear_stall(db: Database, agent: str) -> None:
    db.set_kv(f"stall:{agent}", None)
