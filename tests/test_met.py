"""Offline tests for the Metropolitan Museum of Art Open Access connector.

No network: a routing fake stands in for ``HttpClient.get_json`` so the v1.1
search call and the per-object ``/v1/objects/<id>`` calls are all served from
local fixtures.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mnemosyne.models import SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.met import MetConnector, _is_public_domain

DESCRIPTOR = Path(__file__).resolve().parents[1] / "config" / "sources" / "met.yaml"


def _object(object_id: int, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "objectID": object_id,
        "title": f"Object {object_id}",
        "artistDisplayName": "Anonymous",
        "objectDate": "ca. 1880",
        "objectBeginDate": 1880,
        "objectEndDate": 1880,
        "objectURL": f"https://www.metmuseum.org/art/collection/search/{object_id}",
        "primaryImage": f"https://images.metmuseum.org/{object_id}.jpg",
        "primaryImageSmall": f"https://images.metmuseum.org/{object_id}-small.jpg",
        "isPublicDomain": True,
        "medium": "Oil on canvas",
        "department": "European Paintings",
        "classification": "Paintings",
        "creditLine": "Gift of Someone, 1900",
    }
    base.update(overrides)
    return base


class _FakeHttp:
    """Routes GET calls by URL; never touches the network."""

    def __init__(self, search: dict[str, Any], objects: dict[str, Any]) -> None:
        self._search = search
        self._objects = objects
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        if url.endswith("/v1.1/search"):
            return self._search
        object_id = url.rstrip("/").rsplit("/", 1)[-1]
        return self._objects[object_id]

    def object_calls(self) -> int:
        return sum(1 for url, _ in self.calls if "/objects/" in url)


def _raw() -> dict[str, Any]:
    return yaml.safe_load(DESCRIPTOR.read_text(encoding="utf-8"))


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(**_raw())


def _search(*object_ids: int) -> dict[str, Any]:
    return {"total": len(object_ids), "objectIDs": list(object_ids)}


def test_met_descriptor_is_keyless_rest_cc0():
    raw = _raw()
    assert raw["id"] == "met"
    assert raw["protocol"] == "rest"
    assert raw["auth"] == "none"
    assert raw["license"] == "CC0-1.0"
    assert raw["rate_limit_per_s"] == 1.0
    assert raw["priority"] == 35
    assert "collectionapi.metmuseum.org" in raw["base_url"]
    assert "industrial-history" in raw["tags"]
    assert "steam engine" in raw["seeds"]


def test_met_uses_registered_connector():
    assert isinstance(build_connector(_descriptor(), _FakeHttp(_search(1), {})), MetConnector)


@pytest.mark.asyncio
async def test_met_search_normalizes_public_assets():
    objects = {"148401": _object(148401)}
    http = _FakeHttp(_search(148401), objects)
    connector = MetConnector(_descriptor(), http)

    assets = await connector.search("steam engine", limit=5)

    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "met"
    assert asset.source_asset_id == "148401"
    assert asset.title == "Object 148401"
    assert asset.creator == "Anonymous"
    assert asset.date_text == "ca. 1880"
    assert asset.year == 1880
    assert asset.license == "CC0-1.0"
    assert asset.rights == "Gift of Someone, 1900"
    assert asset.page_url == "https://www.metmuseum.org/art/collection/search/148401"
    assert asset.image_url == "https://images.metmuseum.org/148401.jpg"
    assert asset.thumbnail_url == "https://images.metmuseum.org/148401-small.jpg"
    assert asset.description == "Oil on canvas ; Paintings"
    assert asset.extra["met_object_id"] == 148401
    assert asset.extra["department"] == "European Paintings"
    assert asset.extra["classification"] == "Paintings"
    assert asset.extra["credit_line"] == "Gift of Someone, 1900"
    # search hit the v1.1 endpoint with hasImages=true, not the retired v1 one
    search_url, search_kwargs = http.calls[0]
    assert search_url.endswith("/v1.1/search")
    assert search_kwargs["params"]["q"] == "steam engine"
    assert search_kwargs["params"]["hasImages"] == "true"


@pytest.mark.asyncio
async def test_met_skips_non_public_domain():
    objects = {
        "2": _object(2, isPublicDomain=False),
        "3": _object(3),
    }
    http = _FakeHttp(_search(2, 3), objects)
    connector = MetConnector(_descriptor(), http)

    assets = await connector.search("factory", limit=5)

    assert [a.source_asset_id for a in assets] == ["3"]


@pytest.mark.asyncio
async def test_met_skips_missing_primary_image():
    objects = {
        "5": _object(5, primaryImage=""),
        "6": _object(6, primaryImageSmall=""),
    }
    http = _FakeHttp(_search(5, 6), objects)
    connector = MetConnector(_descriptor(), http)

    assets = await connector.search("locomotive", limit=5)

    # 5 is dropped (no image); 6 falls back to primaryImage for its thumbnail
    assert [a.source_asset_id for a in assets] == ["6"]
    assert assets[0].thumbnail_url == "https://images.metmuseum.org/6.jpg"


@pytest.mark.asyncio
async def test_met_respects_limit_and_stops_early():
    objects = {str(i): _object(i) for i in (10, 11, 12, 13, 14)}
    http = _FakeHttp(_search(10, 11, 12, 13, 14), objects)
    connector = MetConnector(_descriptor(), http)

    assets = await connector.search("steel mill", limit=2)

    assert [a.source_asset_id for a in assets] == ["10", "11"]
    # stopped after collecting `limit`: only two object look-ups were made
    assert http.object_calls() == 2


@pytest.mark.asyncio
async def test_met_caps_object_attempts_at_four_times_limit():
    ids = list(range(1, 21))
    objects = {str(i): _object(i, isPublicDomain=False) for i in ids}
    http = _FakeHttp(_search(*ids), objects)
    connector = MetConnector(_descriptor(), http)

    assets = await connector.search("coal mine", limit=2)

    assert assets == []
    # never scans all 20 ids: it gives up after 4 * limit = 8 attempts
    assert http.object_calls() == 8


@pytest.mark.asyncio
async def test_met_empty_search_returns_no_assets():
    http = _FakeHttp({"total": 0, "objectIDs": None}, {})
    connector = MetConnector(_descriptor(), http)

    assert await connector.search("nothing", limit=5) == []
    assert http.object_calls() == 0


def test_met_is_public_domain_accepts_bool_and_string():
    assert _is_public_domain({"isPublicDomain": True}) is True
    assert _is_public_domain({"isPublicDomain": "true"}) is True
    assert _is_public_domain({"isPublicDomain": False}) is False
    assert _is_public_domain({}) is False
