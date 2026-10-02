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


def _age(db: Database, message_id: int, minutes: float) -> None:
    stamp = (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()
    db._conn.execute("UPDATE messages SET claimed_at = ? WHERE id = ?", (stamp, message_id))
    db._conn.commit()


def _running_message(db: Database, recipient: str = "browser") -> int:
    return db._conn.execute(
        "INSERT INTO messages (sender, recipient, body, status, created_at, claimed_at)"
        " VALUES ('operator', ?, 'mission', 'running', ?, ?)",
        (recipient, datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat()),
    ).lastrowid


def test_a_long_running_mission_is_not_an_incident(cfg):
    db = Database(cfg.db_file())
    mid = _running_message(db)
    _age(db, mid, 51)
    line, alerts = check_invariants(cfg)
    assert alerts == [], "une mission longue qui ne patine pas ne déclenche rien"
    assert "running=1" in line
    db.close()


def test_a_stuck_agent_is_reported_with_its_cause(cfg):
    db = Database(cfg.db_file())
    mid = _running_message(db)
    _age(db, mid, 51)
    mark_stall(db, "browser", "3 fois la meme action")
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
    db._conn.execute(
        "INSERT INTO messages (sender, recipient, body, status, created_at)"
        " VALUES ('operator', 'browser', 'mission', 'pending', ?)",
        ((datetime.now(UTC) - timedelta(minutes=120)).isoformat(),),
    )
    db._conn.commit()
    _line, alerts = check_invariants(cfg)
    assert any("en attente depuis" in a for a in alerts)
    db.close()


def test_a_lease_held_by_a_dead_process_is_an_alert(cfg):
    import json

    db = Database(cfg.db_file())
    db._conn.execute(
        "INSERT INTO kv (key, value) VALUES ('lease:agency', ?)",
        (json.dumps({"owner": "x", "pid": 4194304, "host": _hostname(),
                     "started": 1, "expires": 9999999999}),),
    )
    db._conn.commit()
    _line, alerts = check_invariants(cfg)
    assert any("bail agency" in a and "pid mort" in a for a in alerts)
    db.close()


def test_report_appends_one_line_per_check(cfg, tmp_path):
    out = tmp_path / "soak.log"
    report(cfg, out)
    report(cfg, out)
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert all("pending=" in line for line in lines)


def _hostname() -> str:
    import socket

    return socket.gethostname()
