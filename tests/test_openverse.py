"""Openverse search: JSON results into canonical assets (offline)."""

from __future__ import annotations

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.openverse import OpenverseConnector

BASE = "https://api.openverse.org/v1"

PAYLOAD = {
    "result_count": 1,
    "results": [
        {
            "id": "abc-123",
            "title": "Usine sidérurgique",
            "description": "Acier",
            "creator": "Anonyme",
            "created_on": "1950-01-01",
            "license": "cc0",
            "license_version": "1.0",
            "foreign_landing_url": "https://example.org/notice/1",
            "url": "https://example.org/img/1.jpg",
            "thumbnail": "https://example.org/thumb/1.jpg",
            "width": 1200,
            "height": 800,
            "provider": "flickr",
            "source": "flickr",
        }
    ],
}


class FakeHttp:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict]] = []

    async def get_json(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.payload


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="openverse",
        name="Openverse",
        protocol=Protocol.REST,
        base_url=BASE,
        auth="none",
        license="varies",
    )


@pytest.mark.asyncio
async def test_search_maps_results():
    http = FakeHttp(PAYLOAD)
    connector = OpenverseConnector(_descriptor(), http)

    assets = await connector.search("usine", limit=5)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.title == "Usine sidérurgique"
    assert asset.creator == "Anonyme"
    assert asset.year == 1950
    assert asset.license == "cc0 1.0"
    assert asset.page_url == "https://example.org/notice/1"
    assert asset.image_url == "https://example.org/img/1.jpg"
    assert asset.thumbnail_url == "https://example.org/thumb/1.jpg"
    assert asset.extra["provider"] == "flickr"

    url, kwargs = http.calls[0]
    assert url.endswith("/images/")
    assert kwargs["params"]["q"] == "usine"


@pytest.mark.asyncio
async def test_search_without_results_returns_empty():
    connector = OpenverseConnector(_descriptor(), FakeHttp({"results": []}))
    assert await connector.search("usine") == []
