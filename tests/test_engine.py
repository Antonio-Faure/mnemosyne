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
