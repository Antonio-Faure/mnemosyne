"""The watchdog reports stalls with a cause, not durations.

`scripts/soak.py` used to shout "message #67 running for 51 min", which is the
wrong signal: a long mission is not an incident. The agents now write a stall
marker when they stop progressing, and the watchdog distinguishes the two.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from mnemosyne.config import get_config
from mnemosyne.db import Database
from mnemosyne.models import Job
from mnemosyne.monitor import (
    check_invariants,
    clear_stall,
    mark_stall,
    report,
)
from mnemosyne.util import utcnow_iso


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    config = get_config()
    monkeypatch.setattr(type(config), "data_path", property(lambda self: tmp_path))
    monkeypatch.setattr(type(config), "db_file", lambda self: tmp_path / "m.db")
    return config


def _backdate(db: Database, sql: str, params: tuple) -> None:
    """Test-only setup: age a row. (Production reads go through the API;
    backdating a timestamp is exactly the one thing no public method does.)"""
    db._conn.execute(sql, params)
    db._conn.commit()


def _running_message(db: Database, recipient: str = "browser") -> int:
    mid = db.post_message("operator", recipient, "mission")
    db.claim_messages(recipient, owner="test", limit=1)
    return mid


def test_a_long_running_mission_is_not_an_incident(cfg):
    db = Database(cfg.db_file())
    mid = _running_message(db)
    _backdate(
        db, "UPDATE messages SET claimed_at = ? WHERE id = ?",
        ((datetime.now(UTC) - timedelta(minutes=51)).isoformat(), mid),
    )
    line, alerts = check_invariants(cfg)
    assert alerts == [], "une mission longue qui ne patine pas ne déclenche rien"
    assert "running=1" in line
    db.close()


def test_a_stuck_agent_is_reported_with_its_cause(cfg):
    db = Database(cfg.db_file())
    _running_message(db)
    # the marker must be at least STALL_MARK_MIN old to count
    db.set_kv("stall:browser", {"at": (datetime.now(UTC) - timedelta(minutes=3)).isoformat(),
                                "reason": "3 fois la meme action"})
    line, alerts = check_invariants(cfg)
    assert len(alerts) == 1, alerts
    assert "patine" in alerts[0] and "3 fois la meme action" in alerts[0]
    assert "patine=browser" in line
    db.close()


def test_progress_clears_the_marker(cfg):
    db = Database(cfg.db_file())
    mark_stall(db, "coder", "boucle")
    assert db.get_kv("stall:coder")
    clear_stall(db, "coder")
    line, alerts = check_invariants(cfg)
    assert db.get_kv("stall:coder") is None
    assert "patine=-" in line
    assert not any("patine" in a for a in alerts)
    db.close()


def test_a_pending_message_nobody_picks_up_is_an_alert(cfg):
    db = Database(cfg.db_file())
    db.post_message("operator", "browser", "mission")
    _backdate(
        db, "UPDATE messages SET created_at = ? WHERE status = 'pending'",
        ((datetime.now(UTC) - timedelta(minutes=120)).isoformat(),),
    )
    _line, alerts = check_invariants(cfg)
    assert any("en attente depuis" in a for a in alerts)
    db.close()


def test_a_lease_held_by_a_dead_process_is_an_alert(cfg):
    import socket

    db = Database(cfg.db_file())
    db.set_kv(
        "lease:agency",
        {"owner": "x", "pid": 16777216, "host": socket.gethostname(),
         "started": 1, "expires": 9999999999},
    )
    _line, alerts = check_invariants(cfg)
    assert any("bail agency" in a and "processus disparu" in a for a in alerts)
    db.close()


def test_a_mechanical_job_hung_is_an_alert_but_never_an_agent_run(cfg):
    """jobs >45 min: mechanical ones alert, agent sessions never (stall judge)."""
    db = Database(cfg.db_file())
    mech = db.enqueue(Job(kind="verify", payload={}))
    agent = db.enqueue(Job(kind="agency", payload={}))
    db.claim_due_jobs(utcnow_iso(), 2)
    old = (datetime.now(UTC) - timedelta(minutes=60)).isoformat()
    _backdate(db, "UPDATE jobs SET locked_at = ? WHERE id IN (?, ?)", (old, mech, agent))
    _line, alerts = check_invariants(cfg)
    assert any(f"job #{mech} (verify) running" in a for a in alerts), alerts
    assert not any(f"#{agent}" in a for a in alerts), alerts
    db.close()


def test_report_appends_one_line_per_check(cfg, tmp_path):
    out = tmp_path / "soak.log"
    report(cfg, out)
    report(cfg, out)
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert all("pending=" in line for line in lines)
