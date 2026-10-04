"""DPLA connector: normalization + key handling (no network)."""

from __future__ import annotations

from typing import Any

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.dpla import DplaConnector

SAMPLE: dict[str, Any] = {
    "count": 2,
    "start": 0,
    "docs": [
        {
            "id": "dp0001",
            "object": "https://example.org/img/derrick.jpg",
            "isShownAt": "https://example.org/item/dp0001",
            "provider": {
                "name": "The Portal to Texas History",
                "@id": "http://dp.la/api/contributor/tx",
            },
            "dataProvider": {"name": "UNT Libraries"},
            "rights": "http://rightsstatements.org/vocab/NoC-US/1.0/",
            "sourceResource": {
                "title": ["Oil derrick near Beaumont"],
                "creator": ["Anonyme"],
                "description": ["View of an oil derrick."],
                "date": [{"begin": "1905", "displayDate": "1905"}],
                "subject": [{"name": "Petroleum industry"}, {"name": "Texas"}],
            },
        },
        {
            "id": "dp0002",
            "object": "https://example.org/img/mill.jpg",
            "isShownAt": "https://example.org/item/dp0002",
            "sourceResource": {
                "title": "Steel mill",
                "date": "1910",
            },
        },
    ],
}


class FakeHttp:
    """Records calls and returns a canned DPLA payload."""

    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        return self.payload


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="dpla",
        name="Digital Public Library of America",
        protocol=Protocol.REST,
        base_url="https://api.dp.la/v2",
        auth="api_key",
        key_env="DPLA_API_KEY",
        license="varies",
        rights="per record",
    )


async def test_search_normalizes_items(monkeypatch):
    monkeypatch.setenv("DPLA_API_KEY", "secret-key")
    http = FakeHttp(SAMPLE)
    connector = DplaConnector(_descriptor(), http)

    assets = await connector.search("derrick", limit=10)

    assert len(assets) == 2
    first = assets[0]
    assert first.source_id == "dpla"
    assert first.source_asset_id == "dp0001"
    assert first.title == "Oil derrick near Beaumont"
    assert first.creator == "Anonyme"
    assert first.year == 1905
    assert first.image_url == "https://example.org/img/derrick.jpg"
    assert first.page_url == "https://example.org/item/dp0001"
    assert first.license == "http://rightsstatements.org/vocab/NoC-US/1.0/"
    assert first.extra["provider"] == "The Portal to Texas History"
    assert first.extra["data_provider"] == "UNT Libraries"
    assert first.extra["subjects"] == ["Petroleum industry", "Texas"]

    second = assets[1]
    assert second.title == "Steel mill"
    assert second.year == 1910
    # subject absence must not crash / leak provider shape
    assert second.extra["subjects"] == []

    url, kwargs = http.calls[0]
    assert url == "https://api.dp.la/v2"
    assert kwargs["params"]["api_key"] == "secret-key"
    assert kwargs["params"]["q"] == "derrick"
    assert kwargs["params"]["page_size"] == "10"
    assert kwargs["params"]["page"] == "1"


async def test_search_without_key_returns_empty(monkeypatch):
    monkeypatch.delenv("DPLA_API_KEY", raising=False)
    http = FakeHttp(SAMPLE)
    connector = DplaConnector(_descriptor(), http)

    assert await connector.search("derrick") == []
    assert http.calls == []  # no key -> never hits the network


async def test_search_skips_items_without_image(monkeypatch):
    monkeypatch.setenv("DPLA_API_KEY", "k")
    http = FakeHttp({"docs": [{"id": "x", "sourceResource": {"title": "sans image"}}]})
    connector = DplaConnector(_descriptor(), http)

    assert await connector.search("x") == []
