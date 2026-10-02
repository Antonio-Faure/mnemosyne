"""The watchdog reports stalls with a cause, not durations — TASK EDITION.

A long task (one session, or a ping-pong between two) is the normal case:
only a self-reported stall or an abandoned task is an alert.
"""

from __future__ import annotations

import socket
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


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    config = get_config()
    monkeypatch.setattr(type(config), "data_path", property(lambda self: tmp_path))
    monkeypatch.setattr(type(config), "db_file", lambda self: tmp_path / "m.db")
    return config


def test_a_long_running_task_is_not_an_incident(cfg):
    """A task whose activation is recent (or a session still working) alerts nobody."""
    db = Database(cfg.db_file())
    db.enqueue_task("browser", "mission longue")
    db.set_task_status(1, "running")
    line, alerts = check_invariants(cfg)
    assert alerts == [], "une tâche longue qui travaille ne déclenche rien"
    assert "running=1" in line
    db.close()


def test_a_stuck_agent_is_reported_with_its_cause(cfg):
    db = Database(cfg.db_file())
    db.enqueue_task("browser", "mission")
    db.set_task_status(1, "running")
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


def test_a_task_nobody_drains_is_an_alert(cfg):
    """A task left PENDING in the queue for hours = the loop is not running."""
    db = Database(cfg.db_file())
    db.enqueue_task("browser", "mission oubliée")
    db._conn.execute(
        "UPDATE tasks SET created_at = ? WHERE id = 1",
        ((datetime.now(UTC) - timedelta(minutes=120)).isoformat(),),
    )
    db._conn.commit()
    _line, alerts = check_invariants(cfg)
    assert any("en attente dans la file" in a for a in alerts), alerts
    db.close()


def test_an_open_task_with_no_activation_for_hours_is_an_alert(cfg):
    """A task 'running' but not worked on for 45 min while its mailbox waits."""
    db = Database(cfg.db_file())
    db.enqueue_task("browser", "mission abandonnée")
    db.set_task_status(1, "running")
    db.post_message("browser", "coder", "la réponse", task_id=1)
    old = (datetime.now(UTC) - timedelta(minutes=60)).isoformat()
    db._conn.execute(
        "UPDATE tasks SET last_activation_at = ? WHERE id = 1", (old,)
    )
    db._conn.commit()
    _line, alerts = check_invariants(cfg)
    assert any("plus personne ne la travaille" in a for a in alerts), alerts
    db.close()


def test_an_activation_in_flight_is_not_an_alert(cfg):
    """Same task, but an agency job is RUNNING: the session is working."""
    db = Database(cfg.db_file())
    db.enqueue_task("browser", "mission en cours")
    db.set_task_status(1, "running")
    db.post_message("browser", "coder", "la réponse", task_id=1)
    old = (datetime.now(UTC) - timedelta(minutes=60)).isoformat()
    db._conn.execute("UPDATE tasks SET last_activation_at = ? WHERE id = 1", (old,))
    db.enqueue(Job(kind="agency", payload={}))
    db.claim_due_jobs(datetime.now(UTC).isoformat(), 1)  # agency job in flight
    _line, alerts = check_invariants(cfg)
    assert not any("plus personne" in a for a in alerts), alerts
    db.close()


def test_a_lease_held_by_a_dead_process_is_an_alert(cfg):
    db = Database(cfg.db_file())
    db.set_kv(
        "lease:agency",
        {"owner": "x", "pid": 16777216, "host": socket.gethostname(),
         "started": 1, "expires": 9999999999},
    )
    _line, alerts = check_invariants(cfg)
    assert any("bail agency" in a and "processus disparu" in a for a in alerts)
    db.close()


def test_report_appends_one_line_per_check(cfg, tmp_path):
    out = tmp_path / "soak.log"
    report(cfg, out)
    report(cfg, out)
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert all("pending=" in line for line in lines)
