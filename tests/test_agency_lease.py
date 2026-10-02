"""One pilot at a time: a second supervisor must not run activations concurrently.

Two concurrent supervisors would run two coder sessions in the same git
worktree (and two browser sessions against the same Chrome). The `agency`
lease serialises them; a queued task is never lost — the running pilot (or
the next tick) drains the queue.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from mnemosyne.agents.supervisor import run_agency
from mnemosyne.config import get_config
from mnemosyne.db import NOTE_MAX_CHARS, Database


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
def stub_activation(monkeypatch):
    """Never run a real agent in a unit test (battery.py does that in Docker).

    The stub replays the closing logic of the real activation (a task whose
    mailbox is drained is closed, sessions dropped) — otherwise the drain
    queue would loop forever on a task that never ends.
    """

    async def fake_activation(config, db, mailbox, journal, vault_get, agent, task, messages):
        from mnemosyne.agents.session_cache import drop_session_cache

        for m in messages:
            mailbox.mark(m["id"], "handled", note="stub")
        if mailbox.pending_count(task["id"]) == 0:
            db.set_task_status(task["id"], "done", note="stub")
            drop_session_cache(config, task)
            db.delete_task_messages(task["id"])
        return {"agent": agent, "task_id": task["id"], "finish": "stub", "turns": 1,
                "branch": None, "error": None}

    monkeypatch.setattr("mnemosyne.agents.supervisor._activate_session", fake_activation)


def test_a_second_pilot_still_enqueues_but_does_not_drain(cfg):
    """A foreign (alive) agency lease blocks the local activations: the task
    stays in the queue, the running pilot will serve it."""
    db = Database(cfg.db_file())
    assert db.try_lease("agency", ttl_s=60, owner="pilote-externe")

    result = asyncio.run(run_agency(cfg, "mission du codeur", start="coder"))

    assert result.turns == []
    task = db.get_task(1)
    assert task is not None and task["status"] == "pending", "la mission reste en file"
    db.close()


def test_the_lease_is_released_after_a_run(cfg):
    db = Database(cfg.db_file())
    result = asyncio.run(run_agency(cfg, "mission", start="coder"))
    assert result.stop_reason == "no_pending"
    assert len(result.turns) == 1
    assert db.lease_holder_dead_pid("agency") is None
    assert not db.lease_exists("agency"), "le bail est rendu après l'activation"
    assert db.get_task(1)["status"] == "done"
    db.close()


def test_a_dead_pilot_lease_does_not_block(cfg):
    db = Database(cfg.db_file())
    db._conn.execute(
        "INSERT INTO kv (key, value) VALUES ('lease:agency', ?)",
        (
            '{"owner": "cli:1", "pid": 4194304, "host": "autre", "started": 1,'
            ' "expires": 9999999999}',
        ),
    )
    db._conn.commit()
    result = asyncio.run(run_agency(cfg, "mission", start="coder"))
    assert result.turns, "un pilote mort ne bloque pas la file"
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


def test_the_note_keeps_the_delivery_report():
    """Regression: 200 chars cut exactly the useful part (link, duration)."""
    from mnemosyne.agents.supervisor import outcome_status_note

    report = "BILAN — livré https://we.tl/t-abcdef " + "détail " * 400
    status, note = outcome_status_note(report, None)
    assert status == "handled"
    assert len(note) == NOTE_MAX_CHARS == 1000
    assert "https://we.tl/t-abcdef" in note, "le lien de livraison doit survivre"

    status, note = outcome_status_note("", "boom")
    assert (status, note) == ("failed", "boom")
    status, note = outcome_status_note("", None)
    assert status == "review"
