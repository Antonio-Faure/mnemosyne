"""Invariants of the running system, checked on a timer and logged.

The watchdog answers one question: *is something stuck?* It never stops
anything. A long task is not a problem (sessions keep their context, the
ping-pong is unlimited): a task is a problem when nobody works on it — the
agents report their own stalls (`stall:<agent>` markers) and the queue
operator-facing can be cancelled at any moment.

Alerts therefore mean "look at this", never "cut this off".
"""

from __future__ import annotations

from datetime import UTC, datetime

from mnemosyne.config import Config
from mnemosyne.db import Database

#: a task nobody works on for this long is suspicious (the agency tick is 2 min)
STALE_MIN = 45
PENDING_MIN = 90
#: a stall marker counts after this age (the agent gets 2 min of silence)
STALL_MARK_MIN = 2


def _age_minutes(stamp: str | None) -> float | None:
    if not stamp:
        return None
    try:
        return (datetime.now(UTC) - datetime.fromisoformat(stamp)).total_seconds() / 60
    except ValueError:
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

        pending_tasks = db.list_tasks(status="pending")
        for task in pending_tasks:
            age = _age_minutes(task["created_at"])
            if age is not None and age > pending_min:
                alerts.append(
                    f"tâche #{task['id']} en attente dans la file depuis {age:.0f} min"
                )

        running = db.list_tasks(status="running")
        agency_alive = any(job["kind"] == "agency" for job in db.running_jobs())
        for task in running:
            age = _age_minutes(task.get("last_activation_at"))
            if age is None:
                continue
            if age > stale_min and not agency_alive:
                alerts.append(
                    f"tâche #{task['id']} ouverte mais plus personne ne la travaille "
                    f"({age:.0f} min)"
                )

        for lease_name in ("browser", "agency"):
            dead_pid = db.lease_holder_dead_pid(lease_name)
            if dead_pid:
                alerts.append(f"bail {lease_name} tenu par un processus disparu ({dead_pid})")

        stats = {
            "pending": len(pending_tasks),
            "running": len(running),
            "review": db.count_tasks("review"),
            "lease": db.lease_exists("browser"),
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
    """Remove the marker (a true DELETE: no "null" rows left in kv)."""
    db.delete_kv(f"stall:{agent}")
