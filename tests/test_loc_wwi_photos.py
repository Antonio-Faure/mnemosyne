"""Offline tests for the Library of Congress — WWI photographs JSON connector."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mnemosyne.models import SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.loc_wwi_photos import LocWwiPhotosConnector

DESCRIPTOR = Path(__file__).resolve().parents[1] / "config" / "sources" / "loc_wwi_photos.yaml"

_SAMPLE: dict[str, Any] = {
    "pagination": {"of": 1, "page": 1, "perpage": 25, "total": 1},
    "results": [
        {
            "id": "http://www.loc.gov/item/2002722425/",
            "title": "German army entering Brussels, August 1914",
            "date": "1914",
            "description": [
                "Photograph shows German troops marching into Brussels, Belgium.",
            ],
            "image_url": [
                "https://tile.loc.gov/storage-services/service/pnp/ggbain/12345/12345t.gif",
                "https://tile.loc.gov/storage-services/service/pnp/ggbain/12345/12345v.jpg",
            ],
            "url": "https://www.loc.gov/item/2002722425/",
            "original_format": ["photo, print, drawing"],
            "online_format": ["image"],
            "contributor": ["Bain News Service"],
            "subject": ["World War, 1914-1918", "Belgium"],
            "item": {"rights": ["No known restrictions on publication."]},
        }
    ],
}


class _FakeHttp:
    """Captures calls and returns a canned payload; never touches the network."""

    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        return self._payload


def _raw() -> dict[str, Any]:
    return yaml.safe_load(DESCRIPTOR.read_text(encoding="utf-8"))


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(**_raw())


def test_loc_descriptor_is_keyless_rest():
    raw = _raw()
    assert raw["id"] == "loc_wwi_photos"
    assert raw["protocol"] == "rest"
    assert raw["auth"] == "none"
    assert "world-war-i" in raw["base_url"]
    assert raw["license"]


def test_loc_uses_registered_connector():
    connector = build_connector(_descriptor(), _FakeHttp({}))
    assert isinstance(connector, LocWwiPhotosConnector)


@pytest.mark.asyncio
async def test_loc_search_normalizes_assets():
    http = _FakeHttp(_SAMPLE)
    connector = LocWwiPhotosConnector(_descriptor(), http)

    assets = await connector.search("Belgium 1914", limit=5)

    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "loc_wwi_photos"
    assert asset.source_asset_id == "2002722425"
    assert asset.title == "German army entering Brussels, August 1914"
    assert asset.creator == "Bain News Service"
    assert asset.year == 1914
    assert asset.date_text == "1914"
    assert asset.description.startswith("Photograph shows German troops")
    assert asset.rights == "No known restrictions on publication."
    assert asset.license == "varies"
    assert asset.page_url == "https://www.loc.gov/item/2002722425/"
    # largest derivative kept as image, smallest as thumbnail
    assert asset.image_url.endswith("12345v.jpg")
    assert asset.thumbnail_url.endswith("12345t.gif")
    assert asset.extra["source"] == "loc-json"
    assert asset.extra["id"] == "http://www.loc.gov/item/2002722425/"
    assert asset.extra["subject"] == ["World War, 1914-1918", "Belgium"]

    url, kwargs = http.calls[0]
    assert "world-war-i" in url
    assert kwargs["params"]["fo"] == "json"
    assert "Belgium" in kwargs["params"]["q"]


@pytest.mark.asyncio
async def test_loc_skips_results_without_image():
    payload = {
        "results": [
            {"id": "http://www.loc.gov/item/1/", "title": "No image", "image_url": []},
            {
                "id": "http://www.loc.gov/item/2/",
                "title": "Has image",
                "image_url": ["https://tile.loc.gov/x.jpg"],
            },
        ]
    }
    connector = LocWwiPhotosConnector(_descriptor(), _FakeHttp(payload))
    assets = await connector.search("x", limit=10)
    assert [a.source_asset_id for a in assets] == ["2"]


@pytest.mark.asyncio
async def test_loc_survives_unexpected_payload():
    assert await LocWwiPhotosConnector(_descriptor(), _FakeHttp(None)).search("x") == []
    assert (
        await LocWwiPhotosConnector(_descriptor(), _FakeHttp({"results": "nope"})).search("x")
        == []
    )
