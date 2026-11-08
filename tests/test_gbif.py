"""GBIF occurrence search: REST results normalised into canonical assets (offline).

Covers: an occurrence with two qualifying media (CC0 + CC BY) -> two assets,
skipping a CC BY-NC media, a media without a licence, a media without an
identifier (and a non-http identifier), an occurrence without media, an empty
response, the ``limit`` cap, pagination (offset 0 -> 40), ``endOfRecords``, the
``limit`` clamp to 300, the licence/attribution mapping, and the media-level
licence normalisation.
"""

from __future__ import annotations

from typing import Any

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.gbif import GbifConnector, _normalize_license

BASE = "https://api.gbif.org/v1"

CC0 = "http://creativecommons.org/publicdomain/zero/1.0/"
CC_BY = "https://creativecommons.org/licenses/by/4.0/"
CC_BY_NC = "https://creativecommons.org/licenses/by-nc/4.0/"


def _media(
    identifier: str | None = "https://images.example.org/a.jpg",
    license: str | None = CC0,
    *,
    media_type: str | None = "StillImage",
    fmt: str | None = "image/jpeg",
    creator: str | None = None,
    rights_holder: str | None = None,
    title: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    media: dict[str, Any] = {}
    if identifier is not None:
        media["identifier"] = identifier
    if license is not None:
        media["license"] = license
    if media_type is not None:
        media["type"] = media_type
    if fmt is not None:
        media["format"] = fmt
    if creator is not None:
        media["creator"] = creator
    if rights_holder is not None:
        media["rightsHolder"] = rights_holder
    if title is not None:
        media["title"] = title
    if description is not None:
        media["description"] = description
    return media


def _occurrence(
    key: int,
    media: list[dict[str, Any]],
    *,
    scientific_name: str | None = "Danaus plexippus",
    species: str | None = "Danaus plexippus",
    taxon_key: int | None = 7943983,
    event_date: str | None = "2021-06-01",
    year: int | None = 2021,
    country: str | None = "Canada",
    recorded_by: str | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "scientificName": scientific_name,
        "species": species,
        "taxonKey": taxon_key,
        "eventDate": event_date,
        "year": year,
        "country": country,
        "recordedBy": recorded_by,
        "media": media,
    }


def _page(
    results: list[dict[str, Any]],
    count: int,
    offset: int = 0,
    end_of_records: bool = False,
) -> dict[str, Any]:
    return {
        "offset": offset,
        "limit": 20,
        "endOfRecords": end_of_records,
        "count": count,
        "results": results,
    }


class FakeHttp:
    """Returns a per-offset canned GBIF payload and records the calls."""

    def __init__(self, pages: dict[int, dict[str, Any]]) -> None:
        self.pages = pages
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        offset = (kwargs.get("params") or {}).get("offset", 0)
        return self.pages.get(offset, _page([], 0, offset, end_of_records=True))


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="gbif",
        name="GBIF — Global Biodiversity Information Facility",
        protocol=Protocol.REST,
        base_url=BASE,
        auth="none",
        license="varies (CC0-1.0 / CC-BY-4.0)",
    )


def _connector(pages: dict[int, dict[str, Any]]) -> tuple[GbifConnector, FakeHttp]:
    http = FakeHttp(pages)
    return GbifConnector(_descriptor(), http), http


@pytest.mark.asyncio
async def test_two_media_cc0_and_cc_by_yield_two_assets():
    occ = _occurrence(
        1699371086,
        [
            _media("https://img.example.org/1.jpg", CC0),
            _media("https://img.example.org/2.jpg", CC_BY),
        ],
    )
    connector, _ = _connector({0: _page([occ], count=1, end_of_records=True)})

    assets = await connector.search("monarch butterfly", limit=10)

    assert len(assets) == 2  # one Asset per qualifying media
    assert assets[0].license == "CC0-1.0"
    assert assets[1].license == "CC-BY-4.0"
    assert assets[0].id != assets[1].id


@pytest.mark.asyncio
async def test_cc_by_nc_media_is_ignored():
    occ = _occurrence(102, [_media("https://img.example.org/nc.jpg", CC_BY_NC)])
    connector, _ = _connector({0: _page([occ], count=1, end_of_records=True)})

    assert await connector.search("mushroom", limit=10) == []


@pytest.mark.asyncio
async def test_media_without_license_is_ignored():
    occ = _occurrence(103, [_media("https://img.example.org/nolicense.jpg", license=None)])
    connector, _ = _connector({0: _page([occ], count=1, end_of_records=True)})

    assert await connector.search("coral", limit=10) == []


@pytest.mark.asyncio
async def test_media_without_identifier_is_ignored():
    occ = _occurrence(104, [_media(identifier=None)])
    connector, _ = _connector({0: _page([occ], count=1, end_of_records=True)})

    assert await connector.search("fossil", limit=10) == []


@pytest.mark.asyncio
async def test_media_with_non_http_identifier_is_ignored():
    occ = _occurrence(105, [_media("ftp://img.example.org/x.jpg", CC0)])
    connector, _ = _connector({0: _page([occ], count=1, end_of_records=True)})

    assert await connector.search("beetle", limit=10) == []


@pytest.mark.asyncio
async def test_occurrence_without_media_is_ignored():
    occ = _occurrence(106, [])
    connector, _ = _connector({0: _page([occ], count=1, end_of_records=True)})

    assert await connector.search("lichen", limit=10) == []


@pytest.mark.asyncio
async def test_mixed_occurrence_keeps_only_qualifying_media():
    occ = _occurrence(
        107,
        [
            _media("https://img.example.org/a.jpg", CC0),
            _media("https://img.example.org/b.jpg", CC_BY_NC),
            _media("https://img.example.org/c.jpg", CC_BY),
            _media(identifier=None),
        ],
    )
    connector, _ = _connector({0: _page([occ], count=1, end_of_records=True)})

    assets = await connector.search("herbarium", limit=10)

    assert len(assets) == 2
    assert {a.image_url for a in assets} == {
        "https://img.example.org/a.jpg",
        "https://img.example.org/c.jpg",
    }


@pytest.mark.asyncio
async def test_empty_response_returns_empty():
    connector, http = _connector({0: _page([], count=0, end_of_records=True)})

    assert await connector.search("orchid", limit=10) == []
    # a single (empty) page was fetched, then the loop stopped
    assert len(http.calls) == 1


@pytest.mark.asyncio
async def test_limit_is_respected():
    occs = [
        _occurrence(200 + i, [_media(f"https://img.example.org/{i}.jpg", CC0)])
        for i in range(5)
    ]
    connector, _ = _connector({0: _page(occs, count=5, end_of_records=True)})

    assets = await connector.search("bird", limit=3)

    assert len(assets) == 3


@pytest.mark.asyncio
async def test_pagination_advances_offset_by_page_size():
    occ_a = _occurrence(301, [_media("https://img.example.org/a.jpg", CC0)])
    occ_b = _occurrence(302, [_media("https://img.example.org/b.jpg", CC_BY)])
    pages = {
        0: _page([occ_a], count=100, offset=0),
        40: _page([occ_b], count=100, offset=40, end_of_records=True),
    }
    connector, http = _connector(pages)

    assets = await connector.search("papillon", limit=20)

    assert len(assets) == 2
    requested_offsets = [kwargs["params"]["offset"] for _, kwargs in http.calls]
    assert requested_offsets == [0, 40]


@pytest.mark.asyncio
async def test_duplicate_assets_across_pages_are_emitted_once():
    occ = _occurrence(304, [_media("https://img.example.org/dup.jpg", CC0)])
    pages = {
        0: _page([occ], count=100, offset=0),
        40: _page([occ], count=100, offset=40, end_of_records=True),
    }
    connector, _ = _connector(pages)

    assets = await connector.search("papillon", limit=20)

    assert len(assets) == 1
    assert assets[0].source_asset_id == "304-0"


@pytest.mark.asyncio
async def test_end_of_records_stops_pagination():
    occ = _occurrence(303, [_media("https://img.example.org/z.jpg", CC0)])
    connector, http = _connector({0: _page([occ], count=10, end_of_records=True)})

    assets = await connector.search("fern", limit=20)

    assert len(assets) == 1
    assert len(http.calls) == 1


@pytest.mark.asyncio
async def test_search_sends_expected_params_and_clamps_limit():
    connector, http = _connector({0: _page([], count=0, end_of_records=True)})

    await connector.search("orchid", limit=1000)

    url, kwargs = http.calls[0]
    params = kwargs["params"]
    assert url == f"{BASE}/occurrence/search"
    assert params["q"] == "orchid"
    assert params["mediaType"] == "StillImage"
    assert params["limit"] == 300  # min(max(1000 * 2, 10), 300)
    assert params["offset"] == 0


@pytest.mark.asyncio
async def test_license_and_attribution_mapping():
    occ = _occurrence(
        42,
        [
            _media(
                "https://img.example.org/x.jpg",
                CC_BY,
                creator="Alice Photographer",
                rights_holder="Natural History Museum",
                description="Herbier specimen",
            )
        ],
        scientific_name="Papilio machaon",
        species="Papilio machaon",
        taxon_key=1932767,
        event_date="2019-09-14",
        year=2019,
        country="France",
        recorded_by=None,
    )
    connector, _ = _connector({0: _page([occ], count=1, end_of_records=True)})

    asset = (await connector.search("papilio", limit=10))[0]

    assert asset.title == "Papilio machaon"
    assert asset.creator == "Alice Photographer"  # recordedBy absent -> media.creator
    assert asset.description == "Herbier specimen"
    assert asset.date_text == "2019-09-14"
    assert asset.year == 2019
    assert asset.license == "CC-BY-4.0"
    assert asset.rights == "Natural History Museum"
    assert asset.page_url == "https://www.gbif.org/occurrence/42"
    assert asset.image_url == "https://img.example.org/x.jpg"
    assert asset.thumbnail_url == "https://img.example.org/x.jpg"
    assert asset.extra["occurrence_key"] == 42
    assert asset.extra["taxon_key"] == 1932767
    assert asset.extra["species"] == "Papilio machaon"
    assert asset.extra["country"] == "France"
    assert asset.extra["media_license"] == CC_BY
    assert asset.extra["media_creator"] == "Alice Photographer"
    assert asset.extra["rights_holder"] == "Natural History Museum"


@pytest.mark.asyncio
async def test_recorded_by_takes_precedence_for_creator():
    occ = _occurrence(
        43,
        [_media("https://img.example.org/y.jpg", CC0, creator="Media Creator")],
        recorded_by="Field Collector",
    )
    connector, _ = _connector({0: _page([occ], count=1, end_of_records=True)})

    asset = (await connector.search("bee", limit=10))[0]

    assert asset.creator == "Field Collector"
    # no rightsHolder -> rights falls back to the creator
    assert asset.rights == "Field Collector"


@pytest.mark.asyncio
async def test_title_falls_back_to_species_then_key():
    occ1 = _occurrence(
        50, [_media("https://img.example.org/q.jpg", CC0)],
        scientific_name=None, species="Quercus robur",
    )
    occ2 = _occurrence(
        51, [_media("https://img.example.org/r.jpg", CC0)],
        scientific_name=None, species=None,
    )
    connector, _ = _connector({0: _page([occ1, occ2], count=2, end_of_records=True)})

    assets = await connector.search("tree", limit=10)

    assert assets[0].title == "Quercus robur"
    assert assets[1].title == "GBIF occurrence 51"


@pytest.mark.asyncio
async def test_year_falls_back_to_occurrence_year_when_event_date_missing():
    occ = _occurrence(
        60, [_media("https://img.example.org/s.jpg", CC0)],
        event_date=None, year=2007,
    )
    connector, _ = _connector({0: _page([occ], count=1, end_of_records=True)})

    asset = (await connector.search("fossil", limit=10))[0]

    assert asset.date_text == "2007"
    assert asset.year == 2007


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (CC0, "CC0-1.0"),
        ("https://creativecommons.org/publicdomain/zero/1.0/", "CC0-1.0"),
        ("http://www.creativecommons.org/publicdomain/zero/1.0/", "CC0-1.0"),
        (CC_BY, "CC-BY-4.0"),
        ("http://creativecommons.org/licenses/by/4.0/legalcode", "CC-BY-4.0"),
        ("https://www.creativecommons.org/licenses/by/4.0", "CC-BY-4.0"),
        (CC_BY_NC, None),
        ("https://creativecommons.org/licenses/by-sa/4.0/", None),
        ("https://creativecommons.org/publicdomain/mark/1.0/", None),
        (None, None),
        ("", None),
    ],
)
def test_normalize_license(value, expected):
    assert _normalize_license(value) == expected
