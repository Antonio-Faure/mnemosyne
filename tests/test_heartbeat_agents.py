"""The heartbeat drives the bi-agent background turn (agency job)."""

import pytest

from mnemosyne.agents import supervisor
from mnemosyne.agents.outcome import AgentOutcome
from mnemosyne.engine import Engine
from mnemosyne.heartbeat.jobs import JobContext, handle_agency
from mnemosyne.journal import Control, Journal
from mnemosyne.models import Job
from mnemosyne.notify import Notifier


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
async def test_agency_idle_is_free(config):
    ctx = _ctx(config)
    try:
        assert await handle_agency(ctx, Job(kind="agency", payload={})) is None
    finally:
        await ctx.engine.aclose()


@pytest.mark.asyncio
async def test_agency_runs_one_pending_message(config, monkeypatch):
    calls: list[str] = []

    async def fake_browser(cfg, task, mailbox, journal, vault_get):
        calls.append(task)
        return AgentOutcome(finish="rapport ok")

    monkeypatch.setitem(supervisor._RUNNERS, "browser", fake_browser)

    ctx = _ctx(config)
    try:
        ctx.engine.db.post_message("operator", "browser", "fais le warmup")
        await handle_agency(ctx, Job(kind="agency", payload={}))
        assert calls == ["fais le warmup"]
        assert ctx.engine.db.list_messages()[-1]["status"] == "handled"
    finally:
        await ctx.engine.aclose()
