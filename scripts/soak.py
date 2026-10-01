"""Soak watchdog: log one line per check and shout when an invariant breaks.

Run inside the container:  python scripts/soak.py --interval 300
Invariants checked (warning => operator should look):
  * a message stuck RUNNING for more than --stale minutes
  * a message PENDING for more than --pending minutes (nobody is picking it up)
  * a browser lease held by a process that no longer exists
  * a job stuck RUNNING for more than --stale minutes
  * a session that ended without a finish summary (status "review")
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mnemosyne.config import get_config
from mnemosyne.db import Database


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


def check(config, stale_min: float, pending_min: float) -> tuple[str, list[str]]:
    db = Database(config.db_file())
    alerts: list[str] = []
    try:
        running = db._conn.execute(
            "SELECT id, sender, recipient, claimed_at FROM messages WHERE status = 'running'"
        ).fetchall()
        for row in running:
            age = _age_minutes(row["claimed_at"])
            if age is not None and age > stale_min:
                alerts.append(f"message #{row['id']} running depuis {age:.0f} min")
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
        row = db._conn.execute("SELECT value FROM kv WHERE key = 'lease:browser'").fetchone()
        if row:
            try:
                lease = json.loads(row["value"])
            except ValueError:
                lease = {}
            pid = lease.get("pid")
            if (
                lease.get("host") == socket.gethostname()
                and isinstance(pid, int)
                and pid > 0
                and not _alive(pid)
            ):
                alerts.append(f"bail navigateur détenu par un pid mort ({pid})")
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
            "lease": bool(row),
        }
    finally:
        db.close()
    line = (
        f"{datetime.now(UTC):%H:%M:%S} pending={stats['pending']} running={stats['running']} "
        f"review={stats['review']} lease={'oui' if stats['lease'] else 'non'} "
        f"alerts={len(alerts)}"
    )
    return line, alerts


def _age_minutes(stamp: str | None) -> float | None:
    if not stamp:
        return None
    try:
        return (datetime.now(UTC) - datetime.fromisoformat(stamp)).total_seconds() / 60
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float, default=300)
    parser.add_argument("--stale", type=float, default=45, help="minutes")
    parser.add_argument("--pending", type=float, default=90, help="minutes")
    parser.add_argument("--out", default="data/outbox/soak.log")
    args = parser.parse_args()
    config = get_config()
    out = Path(config.root) / args.out if not args.out.startswith("/") else Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    while True:
        line, alerts = check(config, args.stale, args.pending)
        with out.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            for alert in alerts:
                handle.write(f"  !! {alert}\n")
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
