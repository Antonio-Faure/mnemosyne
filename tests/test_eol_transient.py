"""EOL connector — transient CDN errors (HTTP 520/429/5xx) are tolerated.

Offline regression tests for task #149. The resolver saw a transient Cloudflare
HTTP 520 on ``/search/1.0.json``. A transient server/CDN status must *drop the
result set* (the source keeps working) instead of raising and degrading the
whole source — while a real access/rights error (e.g. 403) is **not** masked.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.eol import EolConnector

BASE = "https://eol.org/api"
CC0 = "http://creativecommons.org/publicdomain/zero/1.0/"


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="eol",
        name="Encyclopedia of Life",
        protocol=Protocol.REST,
        base_url=BASE,
        auth="none",
        license="CC0-1.0 / CC-BY-4.0",
    )


def _search_response(results: list[dict[str, Any]], total: int, page: int = 1) -> dict:
    return {
        "totalResults": total,
        "startIndex": (page - 1) * 50 + 1,
        "itemsPerPage": 50,
        "results": results,
    }


def _result(page_id: Any) -> dict[str, Any]:
    return {"id": page_id, "title": f"Taxon {page_id}", "content": "summary"}


def _page(*media: dict[str, Any], identifier: Any = 1) -> dict[str, Any]:
    return {
        "taxonConcept": {
            "identifier": identifier,
            "scientificName": "Danaus plexippus",
            "dataObjects": list(media),
        }
    }


def _image_media(url: str = "https://media.example.org/a.jpg") -> dict[str, Any]:
    return {"mimeType": "image/jpeg", "license": CC0, "mediaURL": url}


def _status_error(url: str, status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", url)
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(f"HTTP {status}", request=request, response=response)


class _FlakyHttp:
    """Raising fake: any URL containing ``fail_marker`` raises ``status``."""

    def __init__(
        self,
        search_pages: dict[int, dict[str, Any]],
        page_details: dict[Any, dict[str, Any]],
        fail_marker: str | None = None,
        status: int = 520,
    ) -> None:
        self.search_pages = search_pages
        self.page_details = page_details
        self.fail_marker = fail_marker
        self.status = status
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        if self.fail_marker and self.fail_marker in url:
            raise _status_error(url, self.status)
        params = kwargs.get("params") or {}
        if url.endswith("/search/1.0.json"):
            return self.search_pages.get(params.get("page", 1), _search_response([], 0))
        segment = url.rsplit("/pages/1.0/", 1)[-1].split(".json", 1)[0]
        try:
            key: Any = int(segment)
        except ValueError:
            key = segment
        return self.page_details.get(key, {"taxonConcept": {}})


@pytest.mark.asyncio
async def test_transient_520_on_search_is_tolerated():
    http = _FlakyHttp(
        {1: _search_response([_result(1)], 1)},
        {},
        fail_marker="/search/",
        status=520,
    )
    connector = EolConnector(_descriptor(), http)

    # 520 is transient: the source returns no results instead of raising
    assert await connector.search("monarch butterfly", limit=5) == []


@pytest.mark.asyncio
async def test_transient_520_on_page_detail_is_skipped():
    http = _FlakyHttp(
        {1: _search_response([_result(1), _result(2)], 2)},
        {2: _page(_image_media("https://media.example.org/2.jpg"), identifier=2)},
        fail_marker="/pages/1.0/1.json",
        status=520,
    )
    connector = EolConnector(_descriptor(), http)

    assets = await connector.search("monarch butterfly", limit=10)

    # the species whose detail 520s is skipped; the other still yields an asset
    assert [a.extra["eol_page_id"] for a in assets] == [2]


@pytest.mark.asyncio
async def test_real_403_on_search_is_not_masked():
    http = _FlakyHttp({}, {}, fail_marker="/search/", status=403)
    connector = EolConnector(_descriptor(), http)

    with pytest.raises(httpx.HTTPStatusError):
        await connector.search("monarch butterfly", limit=5)
