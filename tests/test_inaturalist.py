"""iNaturalist observations: REST results normalised into canonical assets (offline).

Covers: multi-photo observations (one Asset per qualifying photo), licence
re-checking (only ``cc0`` / ``cc-by``), skipped photos (no url / other licence),
observations without photos, empty responses, the ``limit`` cap, pagination
(page 1 -> 2), the ``square.jpg`` -> ``large.jpg`` rendition swap, and the
licence/attribution mapping.
"""

from __future__ import annotations

from typing import Any

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.inaturalist import INaturalistConnector

BASE = "https://api.inaturalist.org/v1"


def _photo(
    photo_id: int | None,
    license_code: str | None,
    url: str | None = "https://inaturalist-open-data.s3.amazonaws.com/photos/1/square.jpg",
    attribution: str | None = "(c) Alice, some rights reserved",
    width: int = 2048,
    height: int = 1536,
) -> dict[str, Any]:
    photo: dict[str, Any] = {
        "id": photo_id,
        "license_code": license_code,
        "attribution": attribution,
        "original_dimensions": {"width": width, "height": height},
    }
    if url is not None:
        photo["url"] = url
    return photo


def _observation(
    obs_id: int,
    photos: list[dict[str, Any]],
    *,
    taxon: dict[str, Any] | None = None,
    species_guess: str | None = None,
    place_guess: str | None = "Jardin des Plantes, Paris",
    quality_grade: str = "research",
    login: str | None = "alice",
    observed_on: str | None = "2021-06-01",
) -> dict[str, Any]:
    user = {"login": login} if login is not None else {}
    return {
        "id": obs_id,
        "species_guess": species_guess,
        "observed_on": observed_on,
        "place_guess": place_guess,
        "quality_grade": quality_grade,
        "user": user,
        "taxon": taxon or {},
        "photos": photos,
    }


def _page(results: list[dict[str, Any]], total_results: int, page: int = 1) -> dict[str, Any]:
    return {"total_results": total_results, "page": page, "per_page": 20, "results": results}


class FakeHttp:
    """Returns a per-page canned iNaturalist payload and records the calls."""

    def __init__(self, pages: dict[int, dict[str, Any]]) -> None:
        self.pages = pages
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        page = (kwargs.get("params") or {}).get("page")
        return self.pages.get(page, _page([], 0, page))


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="inaturalist",
        name="iNaturalist — Observations",
        protocol=Protocol.REST,
        base_url=BASE,
        auth="none",
        license="CC0-1.0 / CC-BY-4.0",
    )


def _connector(pages: dict[int, dict[str, Any]]) -> tuple[INaturalistConnector, FakeHttp]:
    http = FakeHttp(pages)
    return INaturalistConnector(_descriptor(), http), http


@pytest.mark.asyncio
async def test_two_photos_cc0_and_cc_by_yield_two_assets():
    obs = _observation(
        101,
        [
            _photo(5001, "cc0"),
            _photo(5002, "cc-by"),
        ],
        taxon={"name": "Quercus robur", "preferred_common_name": "Chêne commun"},
    )
    connector, _ = _connector({1: _page([obs], total_results=1)})

    assets = await connector.search("chene", limit=10)

    assert len(assets) == 2  # one Asset per qualifying photo
    assert assets[0].license == "CC0-1.0"
    assert assets[1].license == "CC-BY-4.0"
    assert assets[0].source_asset_id == "5001"
    assert assets[1].source_asset_id == "5002"
    assert assets[0].id != assets[1].id


@pytest.mark.asyncio
async def test_cc_by_nc_photo_is_ignored():
    obs = _observation(102, [_photo(5100, "cc-by-nc")])
    connector, _ = _connector({1: _page([obs], total_results=1)})

    assert await connector.search("mousse", limit=10) == []


@pytest.mark.asyncio
async def test_photo_without_url_is_ignored():
    obs = _observation(103, [_photo(5200, "cc0", url=None)])
    connector, _ = _connector({1: _page([obs], total_results=1)})

    assert await connector.search("fougere", limit=10) == []


@pytest.mark.asyncio
async def test_observation_without_photos_is_ignored():
    obs = _observation(104, [])
    connector, _ = _connector({1: _page([obs], total_results=1)})

    assert await connector.search("lichens", limit=10) == []


@pytest.mark.asyncio
async def test_empty_response_returns_empty():
    connector, http = _connector({1: _page([], total_results=0)})

    assert await connector.search("orchidee", limit=10) == []
    # a single (empty) page was fetched, then the loop stopped
    assert len(http.calls) == 1


@pytest.mark.asyncio
async def test_limit_is_respected():
    obs = [
        _observation(200 + i, [_photo(6000 + i, "cc0")], taxon={"name": f"sp{i}"})
        for i in range(5)
    ]
    connector, _ = _connector({1: _page(obs, total_results=5)})

    assets = await connector.search("oiseau", limit=3)

    assert len(assets) == 3


@pytest.mark.asyncio
async def test_pagination_goes_from_page_1_to_page_2():
    obs_a = _observation(301, [_photo(7001, "cc0")], taxon={"name": "Papilio machaon"})
    obs_b = _observation(302, [_photo(7002, "cc-by")], taxon={"name": "Vanessa cardui"})
    # total_results=25 with limit=20 -> per_page=20 -> last page = ceil(25/20) = 2
    pages = {
        1: _page([obs_a], total_results=25, page=1),
        2: _page([obs_b], total_results=25, page=2),
    }
    connector, http = _connector(pages)

    assets = await connector.search("papillon", limit=20)

    assert len(assets) == 2
    requested_pages = [kwargs["params"]["page"] for _, kwargs in http.calls]
    assert requested_pages == [1, 2]


@pytest.mark.asyncio
async def test_square_jpg_is_swapped_for_large_jpg():
    url = "https://inaturalist-open-data.s3.amazonaws.com/photos/761119213/square.jpg"
    obs = _observation(401, [_photo(8001, "cc0", url=url)])
    connector, _ = _connector({1: _page([obs], total_results=1)})

    assets = await connector.search("libellule", limit=10)

    assert assets[0].image_url == (
        "https://inaturalist-open-data.s3.amazonaws.com/photos/761119213/large.jpg"
    )
    assert assets[0].thumbnail_url == url


@pytest.mark.asyncio
async def test_non_square_url_falls_back_unchanged():
    url = "https://inaturalist-open-data.s3.amazonaws.com/photos/9/original.jpg"
    obs = _observation(402, [_photo(8002, "cc-by", url=url)])
    connector, _ = _connector({1: _page([obs], total_results=1)})

    assets = await connector.search("tresor", limit=10)

    assert assets[0].image_url == url


@pytest.mark.asyncio
async def test_license_and_attribution_mapping():
    obs = _observation(
        501,
        [_photo(9001, "cc-by", attribution="(c) Bob, CC BY")],
        taxon={"name": "Amanita muscaria", "preferred_common_name": "Amanite tue-mouches"},
        place_guess="Forêt de Fontainebleau",
        login="bob",
        observed_on="2019-09-14",
    )
    connector, _ = _connector({1: _page([obs], total_results=1)})

    asset = (await connector.search("amantie", limit=10))[0]

    assert asset.title == "Amanite tue-mouches"
    assert asset.creator == "bob"
    assert asset.description == "Forêt de Fontainebleau"
    assert asset.date_text == "2019-09-14"
    assert asset.year == 2019
    assert asset.license == "CC-BY-4.0"
    assert asset.rights == "(c) Bob, CC BY"
    assert asset.page_url == "https://www.inaturalist.org/observations/501"
    assert asset.width == 2048
    assert asset.height == 1536
    assert asset.extra["observation_id"] == 501
    assert asset.extra["photo_id"] == 9001
    assert asset.extra["taxon"] == "Amanita muscaria"
    assert asset.extra["license_code"] == "cc-by"
    assert asset.extra["attribution"] == "(c) Bob, CC BY"
    assert asset.extra["place_guess"] == "Forêt de Fontainebleau"
    assert asset.extra["quality_grade"] == "research"
    assert asset.extra["observed_on"] == "2019-09-14"


@pytest.mark.asyncio
async def test_search_sends_expected_query_params():
    connector, http = _connector({1: _page([], total_results=0)})

    await connector.search("marguerite", limit=5)

    url, kwargs = http.calls[0]
    params = kwargs["params"]
    assert url == f"{BASE}/observations"
    assert params["q"] == "marguerite"
    assert params["photos"] == "true"
    assert params["photo_license"] == "cc0,cc-by"
    assert params["quality_grade"] == "research"
    assert params["per_page"] == 10  # min(max(5, 10), 200)
    assert params["page"] == 1


@pytest.mark.asyncio
async def test_title_falls_back_to_species_guess_then_name():
    # no preferred_common_name -> uses species_guess
    obs = _observation(601, [_photo(9101, "cc0")], species_guess="Champignon", taxon={})
    connector, _ = _connector({1: _page([obs], total_results=1)})
    asset = (await connector.search("champi", limit=10))[0]
    assert asset.title == "Champignon"
