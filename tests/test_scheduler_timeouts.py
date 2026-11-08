"""No wall-clock cap on agent sessions; mechanical jobs keep a safety net.

`Heartbeat._run_job` used to wrap EVERY handler in `wait_for(job_timeout_s)`:
a 4 h clock that cut a long-but-advancing agent session, exactly the mistake
the vision forbids ("aucun plafond de temps"). Now `agency` runs uncapped —
judged on the stall marker — while mechanical jobs keep a bounded timeout that
protects the heartbeat loop from a hung handler.
"""

from __future__ import annotations

import asyncio

import pytest

from mnemosyne.config import get_config
from mnemosyne.heartbeat import jobs as jobs_mod
from mnemosyne.heartbeat.scheduler import Heartbeat
from mnemosyne.models import Job, JobState


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    config = get_config()
    monkeypatch.setattr(type(config), "data_path", property(lambda self: tmp_path))
    monkeypatch.setattr(type(config), "db_file", lambda self: tmp_path / "m.db")
    monkeypatch.setattr(type(config), "journal_path", property(lambda self: tmp_path / "j"))
    monkeypatch.setattr(type(config), "control_path", property(lambda self: tmp_path / "c.md"))
    return config


async def test_agent_session_outlives_the_mechanical_timeout(cfg, monkeypatch):
    """A long agency run is never cancelled; a hung mechanical job is."""

    async def agent_mission(ctx, job):
        await asyncio.sleep(1.5)  # longer than job_timeout_s (1s below)
        return None

    async def hung_mechanical(ctx, job):
        await asyncio.sleep(30)  # must be cancelled, not waited on
        return None

    monkeypatch.setitem(jobs_mod.HANDLERS, "agency", agent_mission)
    monkeypatch.setitem(jobs_mod.HANDLERS, "verify", hung_mechanical)
    cfg.heartbeat.job_timeout_s = 1

    hb = Heartbeat(cfg)
    agency_id = hb.engine.db.enqueue(Job(kind="agency", payload={}, priority=1))
    mech_id = hb.engine.db.enqueue(Job(kind="verify", payload={"source_id": "x"}, priority=2))

    await hb._tick()  # must return: a hung handler cannot freeze the loop
    await hb._drain()

    agent = hb.engine.db.get_job(agency_id)
    mech = hb.engine.db.get_job(mech_id)
    assert agent is not None and agent.state is JobState.DONE, agent
    assert mech is not None and mech.state is JobState.PENDING, mech
    assert mech.attempts == 1, mech  # timed out once, scheduled for retry
    await hb.aclose()


async def test_running_agent_session_does_not_block_the_other_loop(cfg, monkeypatch):
    """A long activation (resolver) must not starve a job enqueued meanwhile.

    Before: `_tick` awaited every claimed job, so one resolver turn blocked the
    whole heartbeat — the biagent job stayed pending for the session duration.
    """

    started = asyncio.Event()
    release = asyncio.Event()
    ran: list[str] = []

    async def slow_resolver(ctx, job):
        started.set()
        await release.wait()
        ran.append("resolver")

    async def quick_mechanical(ctx, job):
        ran.append("agency")

    monkeypatch.setitem(jobs_mod.HANDLERS, "resolver", slow_resolver)
    monkeypatch.setitem(jobs_mod.HANDLERS, "agency", quick_mechanical)

    hb = Heartbeat(cfg)
    hb.engine.db.enqueue(Job(kind="resolver", payload={}, priority=1))

    await hb._tick()  # dispatches the resolver session, returns at once
    await started.wait()
    assert hb._inflight, "the resolver job must still be running"

    agency_id = hb.engine.db.enqueue(Job(kind="agency", payload={}, priority=2))
    await hb._tick()  # second tick while the resolver is mid-turn
    for _ in range(100):
        job = hb.engine.db.get_job(agency_id)
        if job is not None and job.state is JobState.DONE:
            break
        await asyncio.sleep(0.01)

    job = hb.engine.db.get_job(agency_id)
    assert job is not None and job.state is JobState.DONE, job
    assert ran == ["agency"]  # the resolver is still parked on its event
    release.set()
    await hb._drain()
    assert ran == ["agency", "resolver"]
    await hb.aclose()

