"""One pilot at a time: a second supervisor must not run turns concurrently.

Two concurrent supervisors would run two coder turns in the same git worktree
(and two browser turns against the same Chrome session). The `agency` lease
serialises them; the task is still posted, so nothing is lost.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from mnemosyne.agents.supervisor import run_agency
from mnemosyne.config import get_config
from mnemosyne.db import Database


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    config = get_config()
    monkeypatch.setattr(type(config), "data_path", property(lambda self: tmp_path))
    monkeypatch.setattr(type(config), "db_file", lambda self: tmp_path / "m.db")
    monkeypatch.setattr(
        type(config), "control_path", property(lambda self: tmp_path / "control.md")
    )
    return config


@pytest.fixture(autouse=True)
def stub_turn(monkeypatch):
    """Never run a real agent in a unit test (battery.py does that in Docker)."""

    async def fake_turn(config, agent, messages, mailbox, journal, vault_get):
        for m in messages:
            mailbox.mark(m["id"], "handled", note="stub")
        return {
            "agent": agent,
            "message_id": messages[0]["id"],
            "error": "",
            "finish": "stub",
            "branch": None,
        }

    monkeypatch.setattr("mnemosyne.agents.supervisor._execute_turn", fake_turn)


def _dead_lease(db: Database) -> None:
    db._conn.execute(
        "INSERT INTO kv (key, value) VALUES ('lease:agency', ?)",
        (
            '{"owner": "cli:1", "pid": 4194304, "host": "autre", "started": 1,'
            ' "expires": 9999999999}',
        ),
    )
    db._conn.commit()


def test_second_pilot_reports_busy_and_still_posts(cfg):
    db = Database(cfg.db_file())
    assert db.try_lease("agency", ttl_s=60, owner="pilote-externe")

    result = asyncio.run(run_agency(cfg, "mission du codeur", start="coder", max_handoffs=1))

    assert result.stop_reason == "agency_busy"
    assert result.turns == []
    rows = db.list_messages()
    assert len(rows) == 1, "la mission reste en file, elle n'est pas perdue"
    assert rows[0]["recipient"] == "coder"
    assert rows[0]["status"] == "pending"
    db.close()


def test_lease_is_released_after_a_run(cfg):
    db = Database(cfg.db_file())
    _dead_lease(db)  # un pilote mort ne doit pas bloquer

    result = asyncio.run(run_agency(cfg, "mission", start="coder", max_handoffs=1))

    assert result.stop_reason in ("no_pending", "max_handoffs")
    assert len(result.turns) == 1
    holder = db._conn.execute("SELECT value FROM kv WHERE key = 'lease:agency'").fetchone()
    assert holder is None, "le bail est rendu apres le run"
    assert db.list_messages()[0]["status"] == "handled"
    db.close()


def test_dead_pilot_lease_does_not_block(cfg):
    db = Database(cfg.db_file())
    _dead_lease(db)
    result = asyncio.run(run_agency(cfg, "mission", start="coder", max_handoffs=1))
    assert result.stop_reason != "agency_busy", "un pilote mort ne bloque pas"
    db.close()


def test_two_pilots_never_run_at_the_same_time(cfg):
    """Vraie course : deux fils, le second doit trouver le bail pris."""
    seen: list[str] = []

    def pilot(tag: str) -> None:
        db = Database(cfg.db_file())
        if db.try_lease("agency", ttl_s=60, owner=tag):
            seen.append(f"{tag}:held")
            time.sleep(0.4)
            db.release_lease("agency")
        else:
            seen.append(f"{tag}:refused")
        db.close()

    threads = [threading.Thread(target=pilot, args=(t,)) for t in ("A", "B")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(seen) in (["A:held", "B:refused"], ["A:refused", "B:held"])


def test_note_keeps_the_delivery_report():
    """Regression: 200 chars cut exactly the useful part (link, duration)."""
    from mnemosyne.agents.supervisor import NOTE_MAX_CHARS, outcome_status_note

    report = "BILAN — livré https://we.tl/t-abcdef " + "détail " * 400
    status, note = outcome_status_note(report, None)
    assert status == "handled"
    assert len(note) == NOTE_MAX_CHARS == 1000
    assert "https://we.tl/t-abcdef" in note, "le lien de livraison doit survivre"

    status, note = outcome_status_note("", "boom")
    assert (status, note) == ("failed", "boom")
    status, note = outcome_status_note("", None)
    assert status == "review"
