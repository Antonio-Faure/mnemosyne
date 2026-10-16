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


def _finish_open_tasks(ctx) -> None:
    """The previous session ended before the next hourly tick (the job runs hourly)."""
    for task in ctx.engine.db.list_tasks():
        if task["status"] in ("pending", "running"):
            ctx.engine.db.set_task_status(task["id"], "done")


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
    config.agents.auto_connect = True  # cette jambe est opt-in

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
        _finish_open_tasks(ctx)                                    # la session se termine
        await handle_warmup(ctx, Job(kind="warmup", payload={}))   # cycle 1: connexion
        _finish_open_tasks(ctx)
        await handle_warmup(ctx, Job(kind="warmup", payload={}))   # cycle 2: warmup
        _finish_open_tasks(ctx)
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
    config.agents.auto_connect = True  # la jambe connexion est opt-in
    monkeypatch.setattr(jobs, "datetime", _Noon)
    monkeypatch.setattr(jobs, "_connexion_candidate", lambda _ctx: None)

    ctx = _ctx(config)
    try:
        await handle_warmup(ctx, Job(kind="warmup", payload={}))   # cycle 0: warmup
        _finish_open_tasks(ctx)                                    # la session se termine
        await handle_warmup(ctx, Job(kind="warmup", payload={}))   # cycle 1: pas de candidat
        tasks = ctx.engine.db.list_tasks()
        assert len(tasks) == 2
        assert all(t["objective"].startswith("MISSION WARMUP") for t in tasks)
    finally:
        await ctx.engine.aclose()


@pytest.mark.asyncio
async def test_connexion_is_gated_by_the_outbound_quota(config, monkeypatch):
    """A fresh account (0 outbound/day) never posts a registration: warmup instead."""
    from mnemosyne.heartbeat import jobs
    from mnemosyne.models import AuthKind

    async def ready(_ctx):
        return True

    monkeypatch.setattr(jobs, "_browser_ready", ready)
    monkeypatch.setattr(jobs.random, "random", lambda: 0.99)
    config.agents.warmup_window_start = 8
    config.agents.warmup_window_end = 23
    config.agents.warmup_per_day_min = 4
    config.agents.warmup_per_day_max = 4
    config.agents.auto_connect = True  # on teste le quota, pas l'opt-in
    config.reputation.account_created_at = datetime.now().date().isoformat()  # day 0

    class _Noon(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 1, 12, 0, 0)

    monkeypatch.setattr(jobs, "datetime", _Noon)

    class _Candidate:
        id = "europeana"
        name = "Europeana"
        base_url = "https://example.org"
        auth = AuthKind.API_KEY

    monkeypatch.setattr(jobs, "_connexion_candidate", lambda _ctx: _Candidate())

    ctx = _ctx(config)
    try:
        ctx.engine.db.set_kv("mission_cycle", 1)  # odd cycle → candidate considered
        await handle_warmup(ctx, Job(kind="warmup", payload={}))

        tasks = ctx.engine.db.list_tasks()
        assert len(tasks) == 1
        assert tasks[0]["objective"].startswith("MISSION WARMUP")
    finally:
        await ctx.engine.aclose()


@pytest.mark.asyncio
async def test_auto_connect_off_never_posts_a_connexion(config, monkeypatch):
    """`agents.auto_connect: false` (défaut) : le cycle ne poste que des warmups.

    L'onboarding automatique est opt-in : même sur un cycle impair, le
    sélecteur de candidat n'est pas consulté — donc aucune inscription.
    """
    from mnemosyne.heartbeat import jobs

    async def ready(_ctx):
        return True

    monkeypatch.setattr(jobs, "_browser_ready", ready)
    monkeypatch.setattr(jobs.random, "random", lambda: 0.99)
    config.agents.warmup_window_start = 8
    config.agents.warmup_window_end = 23
    config.agents.warmup_per_day_min = 4
    config.agents.warmup_per_day_max = 4

    class _Noon(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 1, 12, 0, 0)

    monkeypatch.setattr(jobs, "datetime", _Noon)
    assert config.agents.auto_connect is False  # défaut : pas d'onboarding auto

    def _must_not_be_consulted(_ctx):
        raise AssertionError("_connexion_candidate ne doit pas être consulté")

    monkeypatch.setattr(jobs, "_connexion_candidate", _must_not_be_consulted)

    ctx = _ctx(config)
    try:
        await handle_warmup(ctx, Job(kind="warmup", payload={}))   # cycle 0 : warmup
        _finish_open_tasks(ctx)
        await handle_warmup(ctx, Job(kind="warmup", payload={}))   # cycle 1 : warmup aussi
        bodies = [t["objective"] for t in reversed(ctx.engine.db.list_tasks())]
        assert len(bodies) == 2
        assert all(b.startswith("MISSION WARMUP") for b in bodies)
        assert all("MISSION CONNEXION" not in b for b in bodies)
    finally:
        await ctx.engine.aclose()


@pytest.mark.asyncio
async def test_connexion_candidate_is_none_when_frozen(config):
    """`dev.sources_freeze` est le maître : aucun candidat, même auto_connect actif."""
    import yaml

    from mnemosyne.heartbeat.jobs import _connexion_candidate

    (config.sources_path / "cle.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "cle",
                "name": "Source à clé",
                "protocol": "iiif",
                "base_url": "https://cle.example/",
                "auth": "api_key",
                "license": "varies",
            }
        ),
        encoding="utf-8",
    )

    ctx = _ctx(config)
    try:
        config.agents.auto_connect = True
        config.dev.sources_freeze = False
        assert _connexion_candidate(ctx) is not None, "la source à clé est un candidat"

        config.dev.sources_freeze = True
        assert _connexion_candidate(ctx) is None, "le gel coupe la sélection"
    finally:
        await ctx.engine.aclose()
