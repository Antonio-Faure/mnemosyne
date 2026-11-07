"""Harvest cadence: productive sources stay at 6 h, empty ones back off to 24 h."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from mnemosyne.config import Config
from mnemosyne.heartbeat.jobs import handle_harvest
from mnemosyne.models import Job


class _Catalog:
    def __init__(self, source):
        self._source = source

    def get(self, source_id):
        return self._source


class _Engine:
    def __init__(self, source, saved: int):
        self.catalog = _Catalog(source)
        self.saved = saved
        self.calls: list[tuple[str, str, int]] = []

    async def harvest(self, source_id: str, seed: str, limit: int = 20) -> int:
        self.calls.append((source_id, seed, limit))
        return self.saved


def _ctx(config: Config, engine: _Engine):
    return SimpleNamespace(
        config=config,
        engine=engine,
        journal=SimpleNamespace(append=lambda *args, **kwargs: None),
    )


def _job(**payload) -> Job:
    return Job(kind="harvest", payload={"source_id": "gallica", **payload})


def test_productive_harvest_keeps_the_short_cadence():
    config = Config()
    source = SimpleNamespace(seeds=["seed-a", "seed-b"])
    engine = _Engine(source, saved=3)

    out = asyncio.run(handle_harvest(_ctx(config, engine), _job(seed_index=0)))

    assert out is not None
    assert out["interval_s"] == config.harvest.interval_s == 6 * 3600
    assert out["seed_index"] == 1
    assert "3 nouveaux" in out["_activity"]
    assert engine.calls == [("gallica", "seed-a", 20)]


def test_empty_harvest_backs_off_to_once_a_day():
    config = Config()
    source = SimpleNamespace(seeds=["seed-a"])
    engine = _Engine(source, saved=0)

    out = asyncio.run(handle_harvest(_ctx(config, engine), _job(seed_index=0)))

    assert out is not None
    assert out["interval_s"] == config.harvest.empty_interval_s == 24 * 3600
    assert out["seed_index"] == 1
    assert "_activity" not in out


def test_seedless_source_is_parked_without_calling_the_provider():
    config = Config()
    source = SimpleNamespace(seeds=[])
    engine = _Engine(source, saved=0)

    out = asyncio.run(handle_harvest(_ctx(config, engine), _job()))

    assert out is not None
    assert out["interval_s"] == config.harvest.no_seed_interval_s == 7 * 86400
    assert engine.calls == []


def test_harvest_can_be_paused_by_config():
    config = Config()
    config.harvest.enabled = False
    source = SimpleNamespace(seeds=["seed-a"])
    engine = _Engine(source, saved=3)

    out = asyncio.run(handle_harvest(_ctx(config, engine), _job()))

    assert out is not None
    assert out["interval_s"] == config.harvest.no_seed_interval_s
    assert engine.calls == []
