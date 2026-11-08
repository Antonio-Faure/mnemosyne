import asyncio
import time

import pytest
import yaml

from mnemosyne.connectors.base import Connector
from mnemosyne.engine import Engine
from mnemosyne.models import Asset


class FakeConnector(Connector):
    async def search(self, query, limit=20, **filters):
        return [
            Asset.build(self.id, "1", title="Puits de Lacq 1950", image_url="http://x/1.jpg"),
            Asset.build(self.id, "2", title="Raffinerie", image_url="http://x/2.jpg"),
        ]


@pytest.mark.asyncio
async def test_engine_search_uses_connectors(config, monkeypatch):
    engine = Engine(config)
    engine.catalog.sync()

    monkeypatch.setattr(
        "mnemosyne.engine.build_connector",
        lambda descriptor, http: FakeConnector(descriptor, http),
    )
    try:
        assets = await engine.search("puits de Lacq")
    finally:
        await engine.aclose()

    assert len(assets) == 2
    assert all(a.source_id == "gallica" for a in assets)


@pytest.mark.asyncio
async def test_harvest_refuses_disabled_source(config, sources_dir, monkeypatch):
    """A disabled source must never be harvested, even when named explicitly."""
    (sources_dir / "off.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "off",
                "name": "Disabled source",
                "protocol": "iiif",
                "base_url": "https://example.invalid",
                "auth": "none",
                "enabled": False,
                "extra": {"manifest": "https://example.invalid/m.json"},
            }
        ),
        encoding="utf-8",
    )
    engine = Engine(config)
    engine.catalog.sync()

    calls: list[str] = []

    def _build(descriptor, http):
        calls.append(descriptor.id)
        return FakeConnector(descriptor, http)

    monkeypatch.setattr("mnemosyne.engine.build_connector", _build)
    try:
        saved = await engine.harvest("off", "usine")
    finally:
        await engine.aclose()

    assert saved == 0
    assert calls == []


def _add_second_source(sources_dir) -> None:
    (sources_dir / "second.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "second",
                "name": "Second provider",
                "protocol": "rest",
                "base_url": "https://second.invalid",
                "auth": "none",
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_search_collapses_the_same_work_across_sources(
    config, sources_dir, monkeypatch
):
    """Europeana/DPLA/Commons serving the same work: one record, first wins."""
    _add_second_source(sources_dir)

    class OneWork(Connector):
        async def search(self, query, limit=20, **filters):
            return [
                Asset.build(
                    self.id,
                    "same",
                    title="Usine de Lacq en 1950",
                    creator="Anonyme",
                    image_url=f"http://x/{self.id}.jpg",
                )
            ]

    monkeypatch.setattr("mnemosyne.engine.build_connector", lambda d, http: OneWork(d, http))
    engine = Engine(config)
    engine.catalog.sync()
    try:
        assets = await engine.search("usine")
    finally:
        await engine.aclose()

    assert len(assets) == 1, "le même objet ne doit pas être compté deux fois"
    assert assets[0].source_id == "gallica"  # premier fournisseur (ordre catalogue)


@pytest.mark.asyncio
async def test_search_keeps_generic_titles_from_different_sources(
    config, sources_dir, monkeypatch
):
    """'Sans titre' cannot identify a work: both records are kept."""
    _add_second_source(sources_dir)

    class Generic(Connector):
        async def search(self, query, limit=20, **filters):
            return [
                Asset.build(self.id, "same", title="Sans titre", image_url=f"http://x/{self.id}.jpg")
            ]

    monkeypatch.setattr("mnemosyne.engine.build_connector", lambda d, http: Generic(d, http))
    engine = Engine(config)
    engine.catalog.sync()
    try:
        assets = await engine.search("usine")
    finally:
        await engine.aclose()

    assert len(assets) == 2


@pytest.mark.asyncio
async def test_one_hung_source_cannot_hold_the_whole_search(
    config, sources_dir, monkeypatch
):
    """A dead provider is capped by SOURCE_SEARCH_TIMEOUT_S, not by luck.

    The resolver's catalog_search fires one request per source: before the cap,
    a single host that never answered kept the tool call pending for minutes and
    (with the old tick) starved the biagent loop behind it.
    """
    _add_second_source(sources_dir)

    class Fast(Connector):
        async def search(self, query, limit=20, **filters):
            return [Asset.build(self.id, "1", title="Puits de Lacq 1950", image_url="http://x/1.jpg")]

    class Hung(Connector):
        async def search(self, query, limit=20, **filters):
            await asyncio.sleep(30)
            return []

    def _build(descriptor, http):
        return Hung(descriptor, http) if descriptor.id == "second" else Fast(descriptor, http)

    monkeypatch.setattr("mnemosyne.engine.build_connector", _build)
    monkeypatch.setattr("mnemosyne.engine.SOURCE_SEARCH_TIMEOUT_S", 0.2)

    engine = Engine(config)
    engine.catalog.sync()
    try:
        started = time.monotonic()
        assets = await engine.search("usine")
        elapsed = time.monotonic() - started
    finally:
        await engine.aclose()

    assert [a.source_id for a in assets] == ["gallica"]
    assert elapsed < 5, f"search took {elapsed:.1f}s despite the per-source cap"


@pytest.mark.asyncio
async def test_search_does_not_consume_the_harvest_budget(config, monkeypatch):
    """A read-only catalog search must not starve the harvest cap (task #154).

    The resolver's ~50 queries per sentence used to be counted as `harvest`;
    once 1000 was reached, every provider was skipped and the meta API answered
    "nothing" for the rest of the day.
    """
    monkeypatch.setattr(
        "mnemosyne.engine.build_connector",
        lambda descriptor, http: FakeConnector(descriptor, http),
    )
    engine = Engine(config)
    engine.catalog.sync()
    try:
        engine.governor.record("harvest", 10**6)  # harvest budget exhausted
        assets = await engine.search("puits de Lacq")
    finally:
        await engine.aclose()

    assert len(assets) == 2, "the harvest cap must not block a search"
    assert engine.governor.daily_count("search") >= 1
    assert engine.governor.daily_count("harvest") == 10**6


@pytest.mark.asyncio
async def test_the_daily_search_cap_is_its_own_ceiling(config, monkeypatch):
    monkeypatch.setattr(
        "mnemosyne.engine.build_connector",
        lambda descriptor, http: FakeConnector(descriptor, http),
    )
    engine = Engine(config)
    engine.catalog.sync()
    try:
        engine.governor.record("search", 10**6)
        assets = await engine.search("puits de Lacq")
    finally:
        await engine.aclose()
    assert assets == []
