"""Internet Archive advanced search: JSON docs into canonical assets (offline)."""

from __future__ import annotations

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.internet_archive import InternetArchiveConnector

BASE = "https://archive.org/advancedsearch.php"

PAYLOAD = {
    "response": {
        "docs": [
            {
                "identifier": "usine-1950",
                "title": ["Usine de Lacq"],
                "creator": "Anonyme",
                "date": "1950",
                "licenseurl": "http://creativecommons.org/publicdomain/mark/1.0/",
                "description": ["Vue d'usine"],
            },
            {"title": ["no identifier -> skipped"]},
        ]
    }
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
        id="internet_archive",
        name="Internet Archive",
        protocol=Protocol.REST,
        base_url=BASE,
        auth="none",
        license="varies",
    )


@pytest.mark.asyncio
async def test_search_maps_docs_and_skips_identifierless():
    http = FakeHttp(PAYLOAD)
    connector = InternetArchiveConnector(_descriptor(), http)

    assets = await connector.search("usine", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.title == "Usine de Lacq"
    assert asset.creator == "Anonyme"
    assert asset.year == 1950
    assert asset.description == "Vue d'usine"
    assert asset.license.endswith("mark/1.0/")
    assert asset.page_url == "https://archive.org/details/usine-1950"
    assert asset.image_url == "https://archive.org/services/img/usine-1950"
    assert asset.extra["ia_identifier"] == "usine-1950"

    params = http.calls[0][1]["params"]
    assert "mediatype:image" in params["q"]
    assert params["output"] == "json"


@pytest.mark.asyncio
async def test_search_without_docs_returns_empty():
    connector = InternetArchiveConnector(_descriptor(), FakeHttp({"response": {"docs": []}}))
    assert await connector.search("usine") == []
