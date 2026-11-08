"""NASA Image and Video Library: REST search normalised into canonical assets (offline)."""

from __future__ import annotations

from typing import Any

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.nasa import NasaConnector

BASE = "https://images-api.nasa.gov"


def _image_item(nasa_id: str = "PIA12345", **data_overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "nasa_id": nasa_id,
        "title": "Pillars of Creation",
        "description": "A" * 700,
        "date_created": "2015-01-05T00:00:00Z",
        "center": "GSFC",
        "keywords": ["nebula", "space"],
        "media_type": "image",
        "photographer": "NASA",
        "secondary_creator": "Hubble",
        "location": "Orion",
    }
    data.update(data_overrides)
    return {
        "data": [data],
        "links": [
            {"href": f"https://images-assets.nasa.gov/image/{nasa_id}/{nasa_id}~medium.jpg"},
            {"href": f"https://images-assets.nasa.gov/image/{nasa_id}/{nasa_id}~large.jpg"},
            {"href": f"https://images-assets.nasa.gov/image/{nasa_id}/{nasa_id}~thumb.jpg"},
        ],
    }


def _collection(
    items: list[dict[str, Any]], total_hits: int | None = None
) -> dict[str, Any]:
    metadata: dict[str, Any] = {} if total_hits is None else {"total_hits": total_hits}
    return {"collection": {"items": items, "metadata": metadata, "links": []}}


class FakeHttp:
    """Returns a per-page canned NASA collection and records the calls."""

    def __init__(self, pages: dict[int, dict[str, Any]]) -> None:
        self.pages = pages
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        page = (kwargs.get("params") or {}).get("page")
        return self.pages.get(page, _collection([]))


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="nasa",
        name="NASA Image and Video Library",
        protocol=Protocol.REST,
        base_url=BASE,
        auth="none",
        license="Public Domain (NASA)",
        rights="NASA content generally not copyrighted; some items may be third-party",
    )


@pytest.mark.asyncio
async def test_search_maps_image_item_and_picks_large_and_thumb():
    http = FakeHttp({1: _collection([_image_item()], total_hits=1)})
    connector = NasaConnector(_descriptor(), http)

    assets = await connector.search("nebula", limit=10)

    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "nasa"
    assert asset.source_asset_id == "PIA12345"
    assert asset.title == "Pillars of Creation"
    assert asset.creator == "NASA"
    assert asset.year == 2015
    assert len(asset.description) == 600  # truncated from 700
    assert asset.image_url.endswith("PIA12345~large.jpg")
    assert asset.thumbnail_url.endswith("PIA12345~thumb.jpg")
    assert asset.page_url == "https://images.nasa.gov/details/PIA12345"
    assert asset.license == "Public Domain (NASA)"
    assert asset.extra["center"] == "GSFC"
    assert asset.extra["nasa_id"] == "PIA12345"
    assert asset.extra["keywords"] == ["nebula", "space"]

    params = http.calls[0][1]["params"]
    assert params["q"] == "nebula"
    assert params["media_type"] == "image"
    assert params["page"] == 1
    assert params["page_size"] == 10  # min(max(10, 10), 100)


@pytest.mark.asyncio
async def test_item_without_links_is_skipped():
    no_links = {"data": [{"nasa_id": "X1", "media_type": "image"}], "links": []}
    http = FakeHttp({1: _collection([no_links, _image_item("OK1")], total_hits=2)})

    assets = await NasaConnector(_descriptor(), http).search("x", limit=10)

    assert [a.source_asset_id for a in assets] == ["OK1"]


@pytest.mark.asyncio
async def test_non_image_item_is_skipped():
    video = {
        "data": [{"nasa_id": "V1", "media_type": "video", "title": "vid"}],
        "links": [{"href": "https://images-assets.nasa.gov/video/V1/V1~large.jpg"}],
    }
    http = FakeHttp({1: _collection([video, _image_item("OK2")], total_hits=2)})

    assets = await NasaConnector(_descriptor(), http).search("x", limit=10)

    assert [a.source_asset_id for a in assets] == ["OK2"]


@pytest.mark.asyncio
async def test_empty_response_returns_empty_and_stops():
    http = FakeHttp({1: _collection([], total_hits=0)})

    assets = await NasaConnector(_descriptor(), http).search("nothing", limit=10)

    assert assets == []
    assert len(http.calls) == 1


@pytest.mark.asyncio
async def test_limit_is_respected():
    items = [_image_item(f"ID{i}") for i in range(5)]
    http = FakeHttp({1: _collection(items, total_hits=5)})

    assets = await NasaConnector(_descriptor(), http).search("x", limit=2)

    assert len(assets) == 2
    assert [a.source_asset_id for a in assets] == ["ID0", "ID1"]


@pytest.mark.asyncio
async def test_page_size_is_clamped_to_100():
    http = FakeHttp({1: _collection([_image_item()], total_hits=1)})

    await NasaConnector(_descriptor(), http).search("x", limit=500)

    assert http.calls[0][1]["params"]["page_size"] == 100


@pytest.mark.asyncio
async def test_pagination_advances_page_1_to_page_2():
    page1 = _collection([_image_item("A"), _image_item("B")], total_hits=100)
    page2 = _collection([_image_item("C"), _image_item("D")], total_hits=100)
    http = FakeHttp({1: page1, 2: page2})

    assets = await NasaConnector(_descriptor(), http).search("x", limit=3)

    assert [a.source_asset_id for a in assets] == ["A", "B", "C"]
    pages_requested = [call[1]["params"]["page"] for call in http.calls]
    assert pages_requested == [1, 2]


@pytest.mark.asyncio
async def test_nasa_id_with_spaces_is_url_encoded_in_page_url():
    spaced = {
        "data": [{"nasa_id": "MSFC 123", "media_type": "image", "title": "T"}],
        "links": [{"href": "https://images-assets.nasa.gov/image/x/x~large.jpg"}],
    }
    http = FakeHttp({1: _collection([spaced], total_hits=1)})

    assets = await NasaConnector(_descriptor(), http).search("x", limit=10)

    assert assets[0].page_url == "https://images.nasa.gov/details/MSFC%20123"


@pytest.mark.asyncio
async def test_title_falls_back_to_nasa_id():
    bare = {
        "data": [{"nasa_id": "ABC", "media_type": "image"}],
        "links": [{"href": "https://images-assets.nasa.gov/image/ABC/ABC~large.jpg"}],
    }
    http = FakeHttp({1: _collection([bare], total_hits=1)})

    assets = await NasaConnector(_descriptor(), http).search("x", limit=10)

    assert assets[0].title == "NASA ABC"


@pytest.mark.asyncio
async def test_creator_falls_back_to_secondary_creator_then_center():
    item = _image_item("C1", photographer=None, secondary_creator="Hubble Team")
    http = FakeHttp({1: _collection([item], total_hits=1)})
    assets = await NasaConnector(_descriptor(), http).search("x", limit=10)
    assert assets[0].creator == "Hubble Team"

    item2 = _image_item("C2", photographer=None, secondary_creator=None, center="JPL")
    http2 = FakeHttp({1: _collection([item2], total_hits=1)})
    assets2 = await NasaConnector(_descriptor(), http2).search("x", limit=10)
    assert assets2[0].creator == "JPL"
