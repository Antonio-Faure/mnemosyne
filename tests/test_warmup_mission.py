"""Warmup is a browser mission, not a separate session.

The heartbeat job decides *when* and posts a read-only mission to the browser
agent, capped in turns (`[[tour: N]]`), instead of running its own Stirrup
session. That leaves exactly two agent session types: coder and browser.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from mnemosyne.agents import supervisor
from mnemosyne.agents.supervisor import _split_turn_cap
from mnemosyne.db import Database
from mnemosyne.engine import Engine
from mnemosyne.heartbeat.jobs import JobContext, handle_warmup
from mnemosyne.journal import Control, Journal
from mnemosyne.models import Job
from mnemosyne.notify import Notifier


def test_turn_cap_is_extracted_and_stripped():
    messages = [
        {"body": "[[tour: 40]]\nMission warmup", "sender": "warmup", "created_at": "t"},
    ]
    cleaned, cap = _split_turn_cap(messages)
    assert cap == 40
    assert cleaned[0]["body"] == "Mission warmup"


def test_no_cap_leaves_the_body_untouched():
    messages = [{"body": "Mission normale", "sender": "operator", "created_at": "t"}]
    cleaned, cap = _split_turn_cap(messages)
    assert cap is None
    assert cleaned[0]["body"] == "Mission normale"


@pytest.mark.asyncio
async def test_turn_cap_reaches_the_runner(config, monkeypatch):
    """A `[[tour: N]]` message bounds its turn, and the marker never reaches the agent."""
    from mnemosyne.agents.mailbox import Mailbox
    from mnemosyne.agents.supervisor import _execute_turn

    seen: list[tuple[str, int | None]] = []

    async def fake_coder(cfg, task, mailbox, journal, vault_get, max_turns=None):
        seen.append((task, max_turns))
        return type("O", (), {"finish": "ok", "turns": 1})()

    monkeypatch.setitem(supervisor._RUNNERS, "coder", fake_coder)

    db = Database(config.db_file())
    try:
        Mailbox(db).post("warmup", "coder", "[[tour: 12]]\nMission courte")
        claimed = db.claim_messages("coder", owner="test")
        await _execute_turn(config, "coder", claimed, Mailbox(db), None, None)
    finally:
        db.close()

    assert seen and seen[0][1] == 12
    assert "[[tour:" not in seen[0][0]


def _ctx(config) -> JobContext:
    engine = Engine(config)
    engine.catalog.sync()
    return JobContext(
        config=config,
        engine=engine,
        journal=Journal(config.journal_path),
        control=Control(config.control_path),
        notifier=Notifier(config.notify.telegram),
    )


@pytest.mark.asyncio
async def test_warmup_job_posts_one_mission(config, monkeypatch):
    from mnemosyne.heartbeat import jobs

    async def ready(_ctx):
        return True

    monkeypatch.setattr(jobs, "_browser_ready", ready)
    monkeypatch.setattr(jobs.random, "random", lambda: 0.99)  # no skip
    config.agents.warmup_window_start = 8
    config.agents.warmup_window_end = 23

    class _Noon(datetime):  # inside the human window whatever the real hour is
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 1, 12, 0, 0)

    monkeypatch.setattr(jobs, "datetime", _Noon)

    ctx = _ctx(config)
    try:
        await handle_warmup(ctx, Job(kind="warmup", payload={}))
        await handle_warmup(ctx, Job(kind="warmup", payload={}))  # idempotent

        messages = ctx.engine.db.list_messages(status="pending")
        assert len(messages) == 1, "a second mission must not pile up"
        mission = messages[0]
        assert mission["sender"] == "warmup"
        assert mission["recipient"] == "browser"
        assert mission["body"].startswith("[[tour:")
        assert "MISSION WARMUP" in mission["body"]
        assert "lecture seule" in mission["body"]
    finally:
        await ctx.engine.aclose()


def test_batch_cap_follows_the_longest_mission():
    """A short warmup batched with a full mission must not truncate the mission."""
    cleaned, cap = _split_turn_cap(
        [
            {"body": "[[tour: 40]]\nMission warmup", "sender": "warmup", "created_at": "t"},
            {"body": "Mission longue (pas de plafond)", "sender": "operator", "created_at": "t"},
        ]
    )
    assert cap is None
    assert cleaned[0]["body"] == "Mission warmup"
    assert cleaned[1]["body"] == "Mission longue (pas de plafond)"


def test_batch_of_capped_missions_uses_the_longest():
    _, cap = _split_turn_cap(
        [
            {"body": "[[tour: 25]]\na", "sender": "warmup", "created_at": "t"},
            {"body": "[[tour: 90]]\nb", "sender": "operator", "created_at": "t"},
        ]
    )
    assert cap == 90
