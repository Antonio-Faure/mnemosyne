"""Wikimedia Commons search: imageinfo/extmetadata into canonical assets (offline)."""

from __future__ import annotations

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.wikimedia import WikimediaConnector

BASE = "https://commons.wikimedia.org/w/api.php"

PAYLOAD = {
    "query": {
        "pages": [
            {
                "pageid": 123,
                "ns": 6,
                "title": "File:Usine de Lacq.jpg",
                "imageinfo": [
                    {
                        "url": "https://upload.wikimedia.org/x.jpg",
                        "thumburl": "https://upload.wikimedia.org/x_512.jpg",
                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Usine_de_Lacq.jpg",
                        "width": 2000,
                        "height": 1500,
                        "extmetadata": {
                            "LicenseShortName": {"value": "CC0"},
                            "Artist": {"value": "<a href='#'>Anonyme</a>"},
                            "DateTimeOriginal": {"value": "1950"},
                            "ImageDescription": {"value": "Usine <b>de</b> Lacq"},
                            "Credit": {"value": "musée"},
                        },
                    }
                ],
            },
            {"pageid": 124, "ns": 6, "title": "File:No image.jpg"},  # no imageinfo
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
        id="wikimedia",
        name="Wikimedia Commons",
        protocol=Protocol.REST,
        base_url=BASE,
        auth="none",
        license="varies",
    )


@pytest.mark.asyncio
async def test_search_maps_pages_and_strips_html():
    http = FakeHttp(PAYLOAD)
    connector = WikimediaConnector(_descriptor(), http)

    assets = await connector.search("usine", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.title == "Usine de Lacq.jpg"  # File: prefix removed
    assert asset.creator == "Anonyme"  # HTML stripped
    assert asset.description == "Usine de Lacq"
    assert asset.year == 1950
    assert asset.license == "CC0"
    assert asset.page_url == "https://commons.wikimedia.org/wiki/File:Usine_de_Lacq.jpg"
    assert asset.image_url == "https://upload.wikimedia.org/x.jpg"
    assert asset.thumbnail_url == "https://upload.wikimedia.org/x_512.jpg"
    assert asset.extra["ns"] == 6

    params = http.calls[0][1]["params"]
    assert params["gsrnamespace"] == "6"
    assert params["gsrsearch"] == "usine"


@pytest.mark.asyncio
async def test_search_without_pages_returns_empty():
    connector = WikimediaConnector(_descriptor(), FakeHttp({"query": {"pages": []}}))
    assert await connector.search("usine") == []
