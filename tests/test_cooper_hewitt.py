"""Cooper Hewitt GraphQL connector: normalization + filtering (no network).

Fixtures mirror the real GraphQL payload shape: ``summary``/``date``/``legal``/
``department``/``classification``/``multimedia`` come back as JSON scalars, each
media rendition (``original``/``large``/``preview``) is an object with a ``url``
key, and ``maker`` is a ``[Agent]`` list. Only media with ``cc0 == True`` and an
image URL are kept; one media becomes one Asset.
"""

from __future__ import annotations

from typing import Any

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.cooper_hewitt import CooperHewittConnector


def _rendition(url: str | None) -> dict[str, Any] | None:
    return {"url": url, "format": "jpeg"} if url else None


def _media(
    media_id: str,
    *,
    cc0: bool = True,
    original: str | None = "orig",
    large: str | None = "large",
    preview: str | None = "preview",
) -> dict[str, Any]:
    base = "https://ciim-static-media.s3.us-east-1.amazonaws.com"
    return {
        "id": media_id,
        "cc0": cc0,
        "type": "image",
        "original": _rendition(f"{base}/{media_id}/orig.jpg" if original else None),
        "large": _rendition(f"{base}/{media_id}/large.jpg" if large else None),
        "preview": _rendition(f"{base}/{media_id}/preview.jpg" if preview else None),
    }


SAMPLE: dict[str, Any] = {
    "data": {
        "object": [
            {
                # CC0, several media -> several Assets
                "id": "object-182872",
                "summary": {"title": "Sidewall"},
                "date": [{"from": "1835", "to": "1850", "value": "1835–50"}],
                "maker": None,
                "legal": {"cc0": True, "credit": "Gift of Wiscasset Public Library"},
                "identifier": [{"value": "1985-36-1-a/d", "type": "accession number"}],
                "department": [
                    {"id": "department-3", "summary": {"title": "Wallcoverings Department"}}
                ],
                "classification": [
                    {"id": "classification-109", "summary": {"title": "transportation"}}
                ],
                "multimedia": [
                    _media("media-143072"),
                    _media("media-264682"),
                ],
            },
            {
                # media not CC0 (and original null) -> fully ignored
                "id": "object-113110",
                "summary": {"title": "Print"},
                "date": None,
                "maker": None,
                "legal": {"credit": "Gift of Mrs. Dexter J. Purinton"},
                "identifier": [{"value": "1955-78-23-a", "type": "accession number"}],
                "department": [
                    {
                        "id": "department-9",
                        "summary": {
                            "title": "Drawings, Prints, and Graphic Design Department"
                        },
                    }
                ],
                "classification": None,
                "multimedia": [_media("media-203353", cc0=False, original=None)],
            },
            {
                # CC0, one media, maker + date -> one rich Asset
                "id": "object-114372",
                "summary": {"title": "Charing Cross Station, London (Drawing)"},
                "date": [{"from": "1875", "to": "1885", "value": "ca. 1880"}],
                "maker": [
                    {"id": "agent-26231", "summary": {"title": "William Louis Sonntag, Jr."}}
                ],
                "legal": {
                    "cc0": True,
                    "credit": "Gift of William H. Matthews",
                },
                "identifier": [{"value": "1956-183-2", "type": "accession number"}],
                "department": [
                    {
                        "id": "department-9",
                        "summary": {
                            "title": "Drawings, Prints, and Graphic Design Department"
                        },
                    }
                ],
                "classification": [
                    {"id": "classification-109", "summary": {"title": "transportation"}}
                ],
                "multimedia": [_media("media-212915")],
            },
        ]
    }
}


class FakeHttp:
    """Records calls and replays canned payloads (one per call, last repeats)."""

    def __init__(self, *payloads: Any):
        self.payloads = list(payloads)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        idx = min(len(self.calls) - 1, len(self.payloads) - 1)
        return self.payloads[idx]


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="cooper_hewitt",
        name="Cooper Hewitt, Smithsonian Design Museum — Collections",
        protocol=Protocol.REST,
        base_url="https://api.cooperhewitt.org/",
        auth="none",
        license="CC0-1.0",
        rights="CC0 media only",
    )


async def test_search_normalizes_cc0_media():
    http = FakeHttp(SAMPLE)
    connector = CooperHewittConnector(_descriptor(), http)

    assets = await connector.search("steam engine", limit=10)

    # 2 cc0 media on Sidewall + 1 on Charing Cross; the non-cc0 Print is dropped
    assert len(assets) == 3
    by_media = {a.source_asset_id: a for a in assets}
    assert set(by_media) == {"media-143072", "media-264682", "media-212915"}

    asset = by_media["media-212915"]
    assert asset.source_id == "cooper_hewitt"
    assert asset.title == "Charing Cross Station, London (Drawing)"
    assert asset.creator == "William Louis Sonntag, Jr."
    assert asset.date_text == "ca. 1880"
    assert asset.year == 1880
    assert asset.license == "CC0-1.0"
    assert asset.rights == "CC0 media only"
    assert asset.page_url == (
        "https://collection.cooperhewitt.org/objects/114372/"
    )
    assert asset.image_url.endswith("/media-212915/orig.jpg")
    assert asset.thumbnail_url.endswith("/media-212915/preview.jpg")
    assert asset.tags == ["transportation"]
    assert asset.extra["cooper_id"] == "object-114372"
    assert asset.extra["media_id"] == "media-212915"
    assert asset.extra["credit"] == "Gift of William H. Matthews"
    assert asset.extra["department"] == [
        "Drawings, Prints, and Graphic Design Department"
    ]
    assert asset.extra["classification"] == ["transportation"]

    # the GraphQL request goes to the endpoint via the `query` GET parameter
    url, kwargs = http.calls[0]
    assert url == "https://api.cooperhewitt.org/"
    query = kwargs["params"]["query"]
    assert 'general: "steam engine"' in query
    assert "hasImages: true" in query
    assert "size: 10" in query
    assert "maker { id summary }" in query


async def test_non_cc0_media_ignored():
    payload = {"data": {"object": [SAMPLE["data"]["object"][1]]}}
    connector = CooperHewittConnector(_descriptor(), FakeHttp(payload))

    assert await connector.search("steam engine") == []


async def test_media_without_image_url_ignored():
    obj = {
        "id": "object-1",
        "summary": {"title": "No image"},
        "legal": {"cc0": True},
        "multimedia": [_media("media-x", original=None, large=None, preview="p")],
    }
    connector = CooperHewittConnector(
        _descriptor(), FakeHttp({"data": {"object": [obj]}})
    )

    assert await connector.search("x") == []


async def test_falls_back_to_large_when_original_missing():
    obj = {
        "id": "object-2",
        "summary": {"title": "Large only"},
        "legal": {"cc0": True},
        "multimedia": [_media("media-y", original=None, large="large", preview="p")],
    }
    connector = CooperHewittConnector(
        _descriptor(), FakeHttp({"data": {"object": [obj]}})
    )

    assets = await connector.search("x")
    assert len(assets) == 1
    assert assets[0].image_url.endswith("/media-y/large.jpg")


async def test_empty_response_yields_no_assets():
    http = FakeHttp({"data": {"object": []}})
    connector = CooperHewittConnector(_descriptor(), http)

    assert await connector.search("steam engine") == []
    assert len(http.calls) == 1  # empty page -> no further pages requested


async def test_size_is_clamped_to_250():
    http = FakeHttp({"data": {"object": []}})
    connector = CooperHewittConnector(_descriptor(), http)

    await connector.search("steam engine", limit=100000)

    query = http.calls[0][1]["params"]["query"]
    assert "size: 250" in query
    assert "size: 100000" not in query


async def test_pagination_walks_pages_until_limit():
    # page 1: two objects without usable media -> 0 assets, but full page
    page1 = {
        "data": {
            "object": [
                {
                    "id": "object-1",
                    "summary": {"title": "A"},
                    "legal": {"cc0": True},
                    "multimedia": [_media("m1", cc0=False)],
                },
                {
                    "id": "object-2",
                    "summary": {"title": "B"},
                    "legal": {"cc0": True},
                    "multimedia": [_media("m2", cc0=False)],
                },
            ]
        }
    }
    # page 2: two cc0 objects -> 2 assets, reaching the limit
    page2 = {
        "data": {
            "object": [
                {
                    "id": "object-3",
                    "summary": {"title": "C"},
                    "legal": {"cc0": True},
                    "multimedia": [_media("m3")],
                },
                {
                    "id": "object-4",
                    "summary": {"title": "D"},
                    "legal": {"cc0": True},
                    "multimedia": [_media("m4")],
                },
            ]
        }
    }
    http = FakeHttp(page1, page2)
    connector = CooperHewittConnector(_descriptor(), http)

    assets = await connector.search("steam engine", limit=2, max_pages=5)

    assert len(assets) == 2
    assert {a.source_asset_id for a in assets} == {"m3", "m4"}
    assert len(http.calls) == 2
    assert "page: 1" in http.calls[0][1]["params"]["query"]
    assert "page: 2" in http.calls[1][1]["params"]["query"]


async def test_query_string_is_escaped():
    http = FakeHttp({"data": {"object": []}})
    connector = CooperHewittConnector(_descriptor(), http)

    await connector.search('steam "engine"')

    query = http.calls[0][1]["params"]["query"]
    assert 'general: "steam \\"engine\\""' in query


async def test_empty_query_short_circuits():
    http = FakeHttp({"data": {"object": []}})
    connector = CooperHewittConnector(_descriptor(), http)

    assert await connector.search("   ") == []
    assert http.calls == []
