import pytest

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
