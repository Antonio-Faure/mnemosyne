"""Deutsches Museum Digital (Omeka S REST API): normalization off-network."""

from __future__ import annotations

from typing import Any

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.deutsches_museum import DeutschesMuseumConnector

BASE = "https://digital.deutsches-museum.de/api"
FILES = "https://digital.deutsches-museum.de/files"

ITEMS: list[dict[str, Any]] = [
    {
        "@id": f"{BASE}/items/17",
        "o:id": 17,
        "o:title": "Zahnrad mit Pfeilverzahnung",
        "o:media": [
            {
                "@id": f"{BASE}/media/80",
                "o:id": 80,
                "o:media_type": "image/jpeg",
                "o:original_url": f"{FILES}/original/gear.jpg",
                "thumbnail_display_urls": {
                    "large": f"{FILES}/large/gear.jpg",
                    "medium": f"{FILES}/medium/gear.jpg",
                    "square": f"{FILES}/square/gear.jpg",
                },
                "o:data": {
                    "@id": "https://digital.deutsches-museum.de/iiif/2/80/info.json"
                },
            }
        ],
        "o:site": [{"o:id": 3, "o:slug": "iggi", "o:title": "IGGI"}],
        "thumbnail_display_urls": {
            "large": f"{FILES}/large/17.jpg",
            "medium": f"{FILES}/medium/17.jpg",
            "square": f"{FILES}/square/17.jpg",
        },
        "dcterms:title": [
            {"@value": "Zahnrad mit Pfeilverzahnung", "type": "literal"}
        ],
        "dcterms:description": [
            {"@value": "Modell eines Pfeilradgetriebes.", "type": "literal"}
        ],
        "dcterms:creator": [{"@value": "Deutsches Museum", "type": "literal"}],
        "dcterms:date": [{"@value": "1905", "type": "literal"}],
        "dcterms:rights": [{"@value": "CC BY-SA 4.0", "type": "literal"}],
    },
    {
        "@id": f"{BASE}/items/42",
        "o:id": 42,
        "o:media": [
            {"@id": f"{BASE}/media/99", "o:id": 99, "o:media_type": "image/tiff"}
        ],
        "o:site": [],
        "thumbnail_display_urls": {
            "large": f"{FILES}/large/42.jpg",
            "medium": f"{FILES}/medium/42.jpg",
            "square": f"{FILES}/square/42.jpg",
        },
        "dcterms:title": [{"@value": "Getriebe", "type": "literal"}],
        "dcterms:date": [{"@value": "um 1910", "type": "literal"}],
    },
    {
        "@id": f"{BASE}/items/43",
        "o:id": 43,
        "o:media": [],
        "thumbnail_display_urls": {"large": "", "medium": "", "square": ""},
        "dcterms:title": [{"@value": "Ohne Bild", "type": "literal"}],
    },
]


class FakeHttp:
    def __init__(self, payload: Any):
        self.payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        return self.payload


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="deutsches_museum",
        name="Deutsches Museum Digital",
        protocol=Protocol.REST,
        base_url=BASE,
        auth="none",
        license="varies",
    )


@pytest.mark.asyncio
async def test_search_normalizes_items():
    http = FakeHttp(ITEMS)
    connector = DeutschesMuseumConnector(_descriptor(), http)

    assets = await connector.search("Zahnrad", limit=10)

    assert len(assets) == 2  # item without any image is skipped
    first = assets[0]
    assert first.source_id == "deutsches_museum"
    assert first.source_asset_id == "17"
    assert first.title == "Zahnrad mit Pfeilverzahnung"
    assert first.description == "Modell eines Pfeilradgetriebes."
    assert first.creator == "Deutsches Museum"
    assert first.year == 1905
    assert first.license == "CC BY-SA 4.0"
    assert first.rights == "CC BY-SA 4.0"
    assert first.image_url == f"{FILES}/original/gear.jpg"
    assert first.thumbnail_url == f"{FILES}/large/gear.jpg"
    assert first.page_url == "https://digital.deutsches-museum.de/s/iggi/item/17"
    assert (
        first.iiif_id
        == "https://digital.deutsches-museum.de/iiif/2/80/info.json"
    )

    second = assets[1]
    assert second.source_asset_id == "42"
    assert second.image_url == f"{FILES}/large/42.jpg"
    assert second.thumbnail_url == f"{FILES}/medium/42.jpg"
    assert second.page_url == f"{BASE}/items/42"
    assert second.license == "varies"

    url, kwargs = http.calls[0]
    assert url == f"{BASE}/items"
    assert kwargs["params"]["search"] == "Zahnrad"
    assert kwargs["params"]["per_page"] == "10"


@pytest.mark.asyncio
async def test_search_survives_unexpected_payload():
    connector = DeutschesMuseumConnector(_descriptor(), FakeHttp({"maint": True}))
    assert await connector.search("Getriebe") == []


@pytest.mark.asyncio
async def test_search_respects_limit():
    connector = DeutschesMuseumConnector(_descriptor(), FakeHttp(ITEMS))
    assets = await connector.search("Zahnrad", limit=1)
    assert len(assets) == 1
