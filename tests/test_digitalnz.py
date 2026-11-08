"""DigitalNZ connector: per-record filters + normalization (no network)."""

from __future__ import annotations

from typing import Any

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.digitalnz import DigitalNzConnector

BASE_URL = "https://api.digitalnz.org/v3/records.json"


class FakeHttp:
    """Records calls and returns a canned DigitalNZ ``records.json`` payload."""

    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        return self.payload


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="digitalnz",
        name="DigitalNZ — Te Puna Mātauranga o Aotearoa",
        protocol=Protocol.REST,
        base_url=BASE_URL,
        auth="none",
        license="varies",
        rights="per record",
    )


def _payload(*records: dict[str, Any]) -> dict[str, Any]:
    return {"search": {"results": list(records)}}


def _record(**overrides: Any) -> dict[str, Any]:
    """A reusable public-domain record with a real image (the "Waitangi Falls" shape)."""
    record: dict[str, Any] = {
        "id": 43819001,
        "title": "Waitangi Falls. Bay of Islands.",
        "description": "Waterfall in the Bay of Islands.",
        "creator": ["Denton, Frank James"],
        "date": ["1890-01-01T12:00:00.000Z"],
        "display_date": "1890-1899",
        "rights": "No known Copyright",
        "copyright": ["No known copyright restrictions"],
        "usage": ["Share", "Modify", "Use commercially"],
        "is_commercial_use": None,
        "rights_url": ["https://api.digitalnz.org/records/43819001.json"],
        "display_content_partner": "Auckland Libraries",
        "content_partner": ["Auckland Libraries"],
        "landing_url": "https://kura.aucklandlibraries.govt.nz/digital/collection/photos/id/43819001",
        "large_thumbnail_url": "https://kura.aucklandlibraries.govt.nz/digital/api/singleitem/image/photos/43819001/large.jpg",
        "thumbnail_url": "https://kura.aucklandlibraries.govt.nz/digital/api/singleitem/image/photos/43819001/thumb.jpg",
        "object_url": None,
    }
    record.update(overrides)
    return record


async def test_keeps_public_domain_record_with_image():
    http = FakeHttp(_payload(_record()))
    connector = DigitalNzConnector(_descriptor(), http)

    assets = await connector.search("Waitangi", limit=10)

    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "digitalnz"
    assert asset.source_asset_id == "43819001"
    assert asset.title == "Waitangi Falls. Bay of Islands."
    assert asset.creator == "Denton, Frank James"
    assert asset.year == 1890
    assert asset.image_url == _record()["large_thumbnail_url"]
    assert asset.thumbnail_url == _record()["thumbnail_url"]
    assert asset.page_url == _record()["landing_url"]
    assert asset.extra["dnz_id"] == "43819001"
    assert asset.extra["partner"] == "Auckland Libraries"
    assert asset.extra["rights_url"] == "https://api.digitalnz.org/records/43819001.json"


async def test_falls_back_to_thumbnail_when_large_missing():
    http = FakeHttp(_payload(_record(large_thumbnail_url=None)))
    connector = DigitalNzConnector(_descriptor(), http)

    assets = await connector.search("Waitangi", limit=10)

    assert len(assets) == 1
    assert assets[0].image_url == _record()["thumbnail_url"]
    assert assets[0].thumbnail_url == _record()["thumbnail_url"]


async def test_skips_record_without_image():
    http = FakeHttp(_payload(_record(large_thumbnail_url=None, thumbnail_url=None)))
    connector = DigitalNzConnector(_descriptor(), http)

    assets = await connector.search("Waitangi", limit=10)

    assert assets == []


async def test_rejects_all_rights_reserved():
    # Passes the commercial-usage filter but the rights text forbids reuse.
    http = FakeHttp(_payload(_record(rights="All rights reserved", copyright=[])))
    connector = DigitalNzConnector(_descriptor(), http)

    assets = await connector.search("Waitangi", limit=10)

    assert assets == []


async def test_rejects_cc_by_nc():
    http = FakeHttp(_payload(_record(rights="CC BY-NC 4.0", copyright=[])))
    connector = DigitalNzConnector(_descriptor(), http)

    assets = await connector.search("Waitangi", limit=10)

    assert assets == []


async def test_rejects_explicit_non_commercial_flag():
    # ``usage`` lists "Use commercially" but the API explicitly says no.
    http = FakeHttp(_payload(_record(is_commercial_use=False)))
    connector = DigitalNzConnector(_descriptor(), http)

    assets = await connector.search("Waitangi", limit=10)

    assert assets == []


async def test_rejects_record_without_commercial_usage():
    http = FakeHttp(_payload(_record(usage=["Share", "Modify"])))
    connector = DigitalNzConnector(_descriptor(), http)

    assets = await connector.search("Waitangi", limit=10)

    assert assets == []


async def test_query_parameters():
    http = FakeHttp(_payload(_record()))
    connector = DigitalNzConnector(_descriptor(), http)

    await connector.search("1914", limit=10)

    assert len(http.calls) == 1
    url, kwargs = http.calls[0]
    assert url == BASE_URL
    params = kwargs["params"]
    assert params["text"] == "1914"
    assert params["and[category][]"] == "Images"
    assert params["and[usage][]"] == "Use commercially"
    assert params["per_page"] == "10"
    assert params["page"] == "1"


async def test_per_page_is_bounded_to_100():
    http = FakeHttp(_payload(_record()))
    connector = DigitalNzConnector(_descriptor(), http)

    await connector.search("gold mining", limit=500)

    params = http.calls[0][1]["params"]
    assert params["per_page"] == "100"
