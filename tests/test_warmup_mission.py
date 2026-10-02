"""The mission cycle: warmup and source connection are TASKS, never mixed.

The heartbeat job alternates legs (1 warmup → 1 connexion when a candidate
exists), each leg is its own queue entry with its own turn cap — the old
in-band `[[tour: N]]` protocol is gone.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from mnemosyne.engine import Engine
from mnemosyne.heartbeat.jobs import JobContext, handle_warmup
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
async def test_warmup_leg_posts_a_task_with_its_turn_cap(config, monkeypatch):
    from mnemosyne.heartbeat import jobs

    async def ready(_ctx):
        return True

    monkeypatch.setattr(jobs, "_browser_ready", ready)
    monkeypatch.setattr(jobs.random, "random", lambda: 0.99)  # no skip
    config.agents.warmup_window_start = 8
    config.agents.warmup_window_end = 23

    class _Noon(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 1, 12, 0, 0)

    monkeypatch.setattr(jobs, "datetime", _Noon)

    ctx = _ctx(config)
    try:
        await handle_warmup(ctx, Job(kind="warmup", payload={}))
        await handle_warmup(ctx, Job(kind="warmup", payload={}))  # idempotent

        tasks = ctx.engine.db.list_tasks()
        assert len(tasks) == 1, "a second warmup must not pile up"
        task = tasks[0]
        assert task["start_agent"] == "browser"
        assert task["turn_cap"] == ctx.config.agents.warmup_max_turns
        assert "MISSION WARMUP" in task["objective"]
        assert "lecture seule" in task["objective"]
        # no in-band protocol left in the objective
        assert "[[tour:" not in task["objective"]
    finally:
        await ctx.engine.aclose()


@pytest.mark.asyncio
async def test_cycle_alternates_warmup_and_connexion(config, monkeypatch):
    """Cycle parity: 0 → warmup, 1 → connexion (candidate), then warmup again."""
    from mnemosyne.heartbeat import jobs

    async def ready(_ctx):
        return True

    monkeypatch.setattr(jobs, "_browser_ready", ready)
    monkeypatch.setattr(jobs.random, "random", lambda: 0.99)
    config.agents.warmup_window_start = 8
    config.agents.warmup_window_end = 23

    class _Noon(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 1, 12, 0, 0)

    monkeypatch.setattr(jobs, "datetime", _Noon)

    from mnemosyne.models import AuthKind

    # enough warmup quota so the cycle is not cut short by the daily cap
    config.agents.warmup_per_day_min = 4
    config.agents.warmup_per_day_max = 4

    class _Candidate:
        id = "europeana"
        name = "Europeana"
        base_url = "https://www.europeana.eu/"
        auth = AuthKind.API_KEY

    # no key at the vault, no task open → europeana is a candidate
    monkeypatch.setattr(jobs, "_connexion_candidate", lambda _ctx: _Candidate())

    ctx = _ctx(config)
    try:
        await handle_warmup(ctx, Job(kind="warmup", payload={}))   # cycle 0: warmup
        await handle_warmup(ctx, Job(kind="warmup", payload={}))   # cycle 1: connexion
        await handle_warmup(ctx, Job(kind="warmup", payload={}))   # cycle 2: warmup
        await handle_warmup(ctx, Job(kind="warmup", payload={}))   # cycle 3: connexion

        tasks = ctx.engine.db.list_tasks()
        kinds = [t["objective"].split()[0] for t in reversed(tasks)]  # oldest first
        assert kinds == ["MISSION", "MISSION", "MISSION", "MISSION"]
        # classify by the mission text: warmup vs connexion
        bodies = [t["objective"] for t in reversed(tasks)]
        assert bodies[0].startswith("MISSION WARMUP")
        assert bodies[1].startswith("MISSION CONNEXION")
        assert bodies[2].startswith("MISSION WARMUP")
        assert bodies[3].startswith("MISSION CONNEXION")
        payload_sources = [t["payload"] for t in reversed(tasks)]
        assert "europeana" in payload_sources[1] and "europeana" in payload_sources[3]
        assert payload_sources[0] == '{"kind": "warmup"}'
    finally:
        await ctx.engine.aclose()


@pytest.mark.asyncio
async def test_connexion_without_candidate_falls_back_to_warmup(config, monkeypatch):
    """No candidate → the odd cycle posts a warmup; the cycle never stalls."""
    from mnemosyne.heartbeat import jobs

    async def ready(_ctx):
        return True

    monkeypatch.setattr(jobs, "_browser_ready", ready)
    monkeypatch.setattr(jobs.random, "random", lambda: 0.99)
    config.agents.warmup_window_start = 8
    config.agents.warmup_window_end = 23

    class _Noon(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 1, 12, 0, 0)

    config.agents.warmup_per_day_min = 4
    config.agents.warmup_per_day_max = 4
    monkeypatch.setattr(jobs, "datetime", _Noon)
    monkeypatch.setattr(jobs, "_connexion_candidate", lambda _ctx: None)

    ctx = _ctx(config)
    try:
        await handle_warmup(ctx, Job(kind="warmup", payload={}))   # cycle 0: warmup
        await handle_warmup(ctx, Job(kind="warmup", payload={}))   # cycle 1: pas de candidat
        tasks = ctx.engine.db.list_tasks()
        assert len(tasks) == 2
        assert all(t["objective"].startswith("MISSION WARMUP") for t in tasks)
    finally:
        await ctx.engine.aclose()
