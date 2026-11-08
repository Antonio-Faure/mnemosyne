"""Encyclopedia of Life search + page detail, normalised into canonical assets.

Covers: a species page with two qualifying media (CC0 + CC BY) -> two assets,
skipping a CC BY-NC media, a non-image media, a media without a URL (and a
non-http URL), a page without ``dataObjects``, an empty search, the ``limit``
cap, search pagination (page 1 -> 2), the licence/attribution mapping, the title
fallbacks, the fact that no page detail is fetched once the limit is reached,
and the media-level licence normalisation.
"""

from __future__ import annotations

from typing import Any

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.eol import EolConnector, _normalize_license

BASE = "https://eol.org/api"

CC0 = "http://creativecommons.org/publicdomain/zero/1.0/"
CC_BY = "https://creativecommons.org/licenses/by/4.0/"
CC_BY_3 = "https://creativecommons.org/licenses/by/3.0/"
CC_BY_NC = "https://creativecommons.org/licenses/by-nc/4.0/"
CC_BY_SA = "https://creativecommons.org/licenses/by-sa/4.0/"
CC_BY_ND = "https://creativecommons.org/licenses/by-nd/4.0/"


def _data_object(
    media_url: str | None = "https://media.example.org/a.jpg",
    license: str | None = CC0,
    *,
    mime_type: str | None = "image/jpeg",
    rights_holder: str | None = None,
    attribution: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    if mime_type is not None:
        obj["mimeType"] = mime_type
    if license is not None:
        obj["license"] = license
    if media_url is not None:
        obj["mediaURL"] = media_url
    if rights_holder is not None:
        obj["rightsHolder"] = rights_holder
    if attribution is not None:
        obj["attribution"] = attribution
    if description is not None:
        obj["description"] = description
    return obj


def _page(
    data_objects: list[dict[str, Any]] | None,
    *,
    identifier: Any = 47109186,
    scientific_name: str | None = "Danaus plexippus",
) -> dict[str, Any]:
    taxon: dict[str, Any] = {"identifier": identifier, "scientificName": scientific_name}
    if data_objects is not None:
        taxon["dataObjects"] = data_objects
    return {"taxonConcept": taxon}


def _result(
    page_id: Any,
    *,
    title: str | None = "Danaus plexippus (monarch butterfly)",
    content: str | None = "The monarch butterfly is a milkweed butterfly.",
) -> dict[str, Any]:
    return {
        "id": page_id,
        "title": title,
        "link": f"https://eol.org/pages/{page_id}",
        "content": content,
    }


def _search_response(
    results: list[dict[str, Any]],
    total: int,
    *,
    page: int = 1,
    items_per_page: int = 50,
) -> dict[str, Any]:
    return {
        "totalResults": total,
        "startIndex": (page - 1) * items_per_page + 1,
        "itemsPerPage": items_per_page,
        "results": results,
    }


class FakeHttp:
    """Answers the EOL search and page-detail endpoints from canned payloads."""

    def __init__(
        self,
        search_pages: dict[int, dict[str, Any]] | None = None,
        page_details: dict[Any, dict[str, Any]] | None = None,
    ) -> None:
        self.search_pages = search_pages or {}
        self.page_details = page_details or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        params = kwargs.get("params") or {}
        if url.endswith("/search/1.0.json"):
            page = params.get("page", 1)
            return self.search_pages.get(page, _search_response([], 0, page=page))
        return self.page_details.get(self._page_id(url), {"taxonConcept": {}})

    @staticmethod
    def _page_id(url: str) -> Any:
        segment = url.rsplit("/pages/1.0/", 1)[-1].split(".json", 1)[0]
        try:
            return int(segment)
        except ValueError:
            return segment

    def page_urls(self) -> list[str]:
        return [url for url, _ in self.calls if "/pages/1.0/" in url]

    def search_pages_requested(self) -> list[int]:
        return [
            kwargs["params"]["page"]
            for url, kwargs in self.calls
            if url.endswith("/search/1.0.json")
        ]


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="eol",
        name="Encyclopedia of Life",
        protocol=Protocol.REST,
        base_url=BASE,
        auth="none",
        license="CC0-1.0 / CC-BY-4.0",
    )


def _connector(
    search_pages: dict[int, dict[str, Any]] | None = None,
    page_details: dict[Any, dict[str, Any]] | None = None,
) -> tuple[EolConnector, FakeHttp]:
    http = FakeHttp(search_pages, page_details)
    return EolConnector(_descriptor(), http), http


@pytest.mark.asyncio
async def test_two_media_cc0_and_cc_by_yield_two_assets():
    connector, _ = _connector(
        {1: _search_response([_result(1)], 1)},
        {
            1: _page(
                [
                    _data_object("https://media.example.org/1.jpg", CC0),
                    _data_object("https://media.example.org/2.jpg", CC_BY),
                ]
            )
        },
    )

    assets = await connector.search("monarch butterfly", limit=10)

    assert len(assets) == 2  # one Asset per qualifying media
    assert assets[0].license == "CC0-1.0"
    assert assets[1].license == "CC-BY-4.0"
    assert assets[0].id != assets[1].id


@pytest.mark.asyncio
async def test_cc_by_nc_media_is_ignored():
    connector, _ = _connector(
        {1: _search_response([_result(1)], 1)},
        {1: _page([_data_object("https://media.example.org/nc.jpg", CC_BY_NC)])},
    )

    assert await connector.search("mushroom", limit=10) == []


@pytest.mark.asyncio
async def test_non_image_media_is_ignored():
    connector, _ = _connector(
        {1: _search_response([_result(1)], 1)},
        {
            1: _page(
                [
                    _data_object(
                        "https://media.example.org/doc.pdf",
                        CC0,
                        mime_type="application/pdf",
                    ),
                    _data_object(
                        "https://media.example.org/clip.mp4",
                        CC0,
                        mime_type="video/mp4",
                    ),
                ]
            )
        },
    )

    assert await connector.search("bird", limit=10) == []


@pytest.mark.asyncio
async def test_media_without_url_is_ignored():
    connector, _ = _connector(
        {1: _search_response([_result(1)], 1)},
        {1: _page([_data_object(media_url=None, license=CC0)])},
    )

    assert await connector.search("coral", limit=10) == []


@pytest.mark.asyncio
async def test_media_with_non_http_url_is_ignored():
    connector, _ = _connector(
        {1: _search_response([_result(1)], 1)},
        {1: _page([_data_object("ftp://media.example.org/x.jpg", CC0)])},
    )

    assert await connector.search("beetle", limit=10) == []


@pytest.mark.asyncio
async def test_page_without_data_objects_is_ignored():
    connector, _ = _connector(
        {1: _search_response([_result(1)], 1)},
        {1: _page(None)},  # taxonConcept present but no dataObjects
    )

    assert await connector.search("fern", limit=10) == []


@pytest.mark.asyncio
async def test_empty_search_returns_empty():
    connector, http = _connector({1: _search_response([], 0)})

    assert await connector.search("orchid", limit=10) == []
    # a single (empty) search page was fetched, then the loop stopped
    assert len(http.calls) == 1


@pytest.mark.asyncio
async def test_limit_is_respected():
    connector, _ = _connector(
        {1: _search_response([_result(1)], 1)},
        {
            1: _page(
                [
                    _data_object("https://media.example.org/1.jpg", CC0),
                    _data_object("https://media.example.org/2.jpg", CC0),
                    _data_object("https://media.example.org/3.jpg", CC0),
                ]
            )
        },
    )

    assets = await connector.search("fossil", limit=2)

    assert len(assets) == 2


@pytest.mark.asyncio
async def test_search_pagination_page_1_then_2():
    connector, http = _connector(
        {
            1: _search_response([_result(11)], 2, page=1, items_per_page=1),
            2: _search_response([_result(22)], 2, page=2, items_per_page=1),
        },
        {
            11: _page([_data_object("https://media.example.org/a.jpg", CC0)], identifier=11),
            22: _page([_data_object("https://media.example.org/b.jpg", CC_BY)], identifier=22),
        },
    )

    assets = await connector.search("papillon", limit=20)

    assert len(assets) == 2
    assert http.search_pages_requested() == [1, 2]


@pytest.mark.asyncio
async def test_no_page_request_when_limit_already_reached():
    connector, http = _connector(
        {1: _search_response([_result(1), _result(2)], 2)},
        {1: _page([_data_object("https://media.example.org/a.jpg", CC0)], identifier=1)},
    )

    assets = await connector.search("bird", limit=1)

    assert len(assets) == 1
    # the limit was reached on result 1, so result 2's page is never fetched
    assert http.page_urls() == [f"{BASE}/pages/1.0/1.json"]


@pytest.mark.asyncio
async def test_license_and_attribution_mapping():
    connector, _ = _connector(
        {1: _search_response([_result(42, title="ignored title", content="EOL summary")], 1)},
        {
            42: _page(
                [
                    _data_object(
                        "https://media.example.org/x.jpg",
                        CC_BY,
                        rights_holder="Natural History Museum",
                        description="Monarch on milkweed",
                    )
                ],
                identifier=42,
                scientific_name="Danaus plexippus",
            )
        },
    )

    asset = (await connector.search("danaus", limit=10))[0]

    assert asset.title == "Danaus plexippus"
    assert asset.creator == "Natural History Museum"
    assert asset.description == "Monarch on milkweed"
    assert asset.date_text is None
    assert asset.year is None
    assert asset.license == "CC-BY-4.0"
    assert asset.rights == "Natural History Museum"
    assert asset.page_url == "https://eol.org/pages/42"
    assert asset.image_url == "https://media.example.org/x.jpg"
    assert asset.thumbnail_url == "https://media.example.org/x.jpg"
    assert asset.extra["eol_page_id"] == 42
    assert asset.extra["scientific_name"] == "Danaus plexippus"
    assert asset.extra["media_license"] == CC_BY
    assert asset.extra["rights_holder"] == "Natural History Museum"


@pytest.mark.asyncio
async def test_rights_falls_back_to_attribution():
    connector, _ = _connector(
        {1: _search_response([_result(7)], 1)},
        {
            7: _page(
                [
                    _data_object(
                        "https://media.example.org/y.jpg",
                        CC0,
                        attribution="Smithsonian",
                    )
                ],
                identifier=7,
            )
        },
    )

    asset = (await connector.search("coral", limit=10))[0]

    assert asset.creator is None
    assert asset.rights == "Smithsonian"


@pytest.mark.asyncio
async def test_description_falls_back_to_content_then_empty():
    long_content = "x" * 900
    connector, _ = _connector(
        {1: _search_response([_result(8, content=long_content)], 1)},
        {8: _page([_data_object("https://media.example.org/z.jpg", CC0)], identifier=8)},
    )

    asset = (await connector.search("fern", limit=10))[0]

    assert len(asset.description) == 600  # result.content truncated to ~600


@pytest.mark.asyncio
async def test_title_falls_back_to_result_title_then_page_id():
    connector, _ = _connector(
        {1: _search_response([_result(51, title="Monarch"), _result(52, title=None)], 2)},
        {
            51: _page(
                [_data_object("https://media.example.org/51.jpg", CC0)],
                identifier=51,
                scientific_name=None,
            ),
            52: _page(
                [_data_object("https://media.example.org/52.jpg", CC0)],
                identifier=52,
                scientific_name=None,
            ),
        },
    )

    assets = await connector.search("tree", limit=10)

    assert assets[0].title == "Monarch"
    assert assets[1].title == "EOL page 52"


@pytest.mark.asyncio
async def test_search_and_detail_send_expected_params():
    connector, http = _connector(
        {1: _search_response([_result(5)], 1)},
        {5: _page([], identifier=5)},
    )

    await connector.search("orchid", limit=100)

    search_url, search_kwargs = http.calls[0]
    assert search_url == f"{BASE}/search/1.0.json"
    assert search_kwargs["params"] == {"q": "orchid", "page": 1}

    detail_url, detail_kwargs = http.calls[1]
    assert detail_url == f"{BASE}/pages/1.0/5.json"
    detail_params = detail_kwargs["params"]
    assert detail_params["images_per_page"] == 50  # min(max(100, 5), 50)
    assert detail_params["common_names"] == "false"
    assert detail_params["details"] == "true"


@pytest.mark.asyncio
async def test_images_per_page_has_a_floor_of_five():
    connector, http = _connector(
        {1: _search_response([_result(5)], 1)},
        {5: _page([], identifier=5)},
    )

    await connector.search("bird", limit=2)

    detail_params = http.calls[1][1]["params"]
    assert detail_params["images_per_page"] == 5  # min(max(2, 5), 50)


@pytest.mark.asyncio
async def test_zero_or_negative_limit_returns_empty_without_requests():
    connector, http = _connector({1: _search_response([_result(1)], 1)})

    assert await connector.search("bird", limit=0) == []
    assert http.calls == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (CC0, "CC0-1.0"),
        ("https://creativecommons.org/publicdomain/zero/1.0/", "CC0-1.0"),
        ("http://www.creativecommons.org/publicdomain/zero/1.0/", "CC0-1.0"),
        (CC_BY, "CC-BY-4.0"),
        ("http://creativecommons.org/licenses/by/4.0/legalcode", "CC-BY-4.0"),
        ("https://www.creativecommons.org/licenses/by/4.0", "CC-BY-4.0"),
        (CC_BY_3, "CC-BY-3.0"),
        ("http://creativecommons.org/licenses/by/3.0/", "CC-BY-3.0"),
        (CC_BY_NC, None),
        (CC_BY_SA, None),
        (CC_BY_ND, None),
        ("https://creativecommons.org/publicdomain/mark/1.0/", None),
        (None, None),
        ("", None),
    ],
)
def test_normalize_license(value, expected):
    assert _normalize_license(value) == expected
