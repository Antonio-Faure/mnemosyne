"""Offline tests for the Library of Congress — Prints & Photographs JSON connector."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mnemosyne.models import SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.loc_pp import LocPpConnector

DESCRIPTOR = Path(__file__).resolve().parents[1] / "config" / "sources" / "loc_pp.yaml"

_SAMPLE: dict[str, Any] = {
    "pagination": {"of": 1, "page": 1, "perpage": 25, "total": 1},
    "results": [
        {
            "id": "http://www.loc.gov/item/2003654321/",
            "title": "Burning oil well, Texas",
            "date": "1918",
            "description": [
                "Photograph shows a gusher on fire and fire-control crew at a "
                "Texas oil field.",
            ],
            "image_url": [
                "https://tile.loc.gov/storage-services/service/pnp/det/12345/12345t.gif",
                "https://tile.loc.gov/storage-services/service/pnp/det/12345/12345v.jpg",
            ],
            "url": "https://www.loc.gov/item/2003654321/",
            "original_format": ["photo, print, drawing"],
            "online_format": ["image"],
            "contributor": ["Standard Oil Company"],
            "subject": ["Oil wells", "Fires", "Texas"],
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


def test_loc_pp_descriptor_is_keyless_rest():
    raw = _raw()
    assert raw["id"] == "loc_pp"
    assert raw["protocol"] == "rest"
    assert raw["auth"] == "none"
    assert "pictures" in raw["base_url"]
    assert raw["license"]


def test_loc_pp_uses_registered_connector():
    connector = build_connector(_descriptor(), _FakeHttp({}))
    assert isinstance(connector, LocPpConnector)


@pytest.mark.asyncio
async def test_loc_pp_search_normalizes_assets():
    http = _FakeHttp(_SAMPLE)
    connector = LocPpConnector(_descriptor(), http)

    assets = await connector.search("oil well fire", limit=5)

    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "loc_pp"
    assert asset.source_asset_id == "2003654321"
    assert asset.title == "Burning oil well, Texas"
    assert asset.creator == "Standard Oil Company"
    assert asset.year == 1918
    assert asset.date_text == "1918"
    assert asset.description.startswith("Photograph shows")
    assert asset.rights == "No known restrictions on publication."
    assert asset.license == "varies"
    assert asset.page_url == "https://www.loc.gov/item/2003654321/"
    # largest derivative kept as image, smallest as thumbnail
    assert asset.image_url.endswith("12345v.jpg")
    assert asset.thumbnail_url.endswith("12345t.gif")
    assert asset.extra["source"] == "loc-json"
    assert asset.extra["id"] == "http://www.loc.gov/item/2003654321/"
    assert asset.extra["subject"] == ["Oil wells", "Fires", "Texas"]

    url, kwargs = http.calls[0]
    assert url == "https://www.loc.gov/pictures/"
    assert kwargs["params"]["fo"] == "json"
    assert kwargs["params"]["q"] == "oil well fire"


@pytest.mark.asyncio
async def test_loc_pp_skips_results_without_image():
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
    connector = LocPpConnector(_descriptor(), _FakeHttp(payload))
    assets = await connector.search("x", limit=10)
    assert [a.source_asset_id for a in assets] == ["2"]


@pytest.mark.asyncio
async def test_loc_pp_survives_unexpected_payload():
    assert await LocPpConnector(_descriptor(), _FakeHttp(None)).search("x") == []
    assert (
        await LocPpConnector(_descriptor(), _FakeHttp({"results": "nope"})).search("x")
        == []
    )
