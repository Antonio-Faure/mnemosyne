"""AUC (American University in Cairo) CONTENTdm host — offline mock tests.

The generic :class:`ContentDmConnector` already serves every CONTENTdm host; this
module proves the AUC descriptor is wired to it and that the host behaves as a
real keyless image source:

* a public-domain item ("This item is in the public domain.") resolves to an
  asset whose ``http`` IIIF ``imageUri`` is upgraded to ``https`` and bounded to
  the ``!1200,1200`` / ``!400,400`` size variants;
* a copyrighted AUC photograph ("Copyright the American University in Cairo" +
  "Contact host ...") is correctly rejected by the per-record licence filter;
* a non-image (compound book, ``application/octet-stream``) is skipped.

Everything is served by a local ``FakeHttp``; no network is touched.
"""

from __future__ import annotations

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import CONNECTORS
from mnemosyne.sources.contentdm import ContentDmConnector

AUC = "https://digitalcollections.aucegypt.edu"


def _field(key: str, label: str, value: str) -> dict:
    return {"key": key, "label": label, "value": value}


def _detail(
    *,
    content_type: str = "image/jp2",
    image_uri: str | None = None,
    fields: list[dict] | None = None,
) -> dict:
    return {
        "contentType": content_type,
        "imageUri": image_uri,
        "thumbnailUri": None,
        "fields": fields or [],
    }


def _search_item(alias: str, item_id: str) -> dict:
    return {
        "collectionAlias": alias,
        "itemId": item_id,
        "itemLink": f"/collection/{alias}/id/{item_id}",
    }


def _search_page(items: list[dict]) -> dict:
    return {"totalResults": len(items), "items": items}


def _iiif_http(alias: str, item_id: str) -> str:
    return f"http://digitalcollections.aucegypt.edu/iiif/2/{alias}:{item_id}/full/full/0/default.jpg"


class FakeHttp:
    """Dispatch on the CONTENTdm URLs, mirroring the real host's JSON shape."""

    def __init__(self, search_pages: dict[int, dict], details: dict[tuple[str, str], object]):
        self.search_pages = search_pages
        self.details = details

    async def get_json(self, url, **kwargs):
        if "/digital/api/search/searchterm/" in url:
            start = (kwargs.get("params") or {}).get("start", 0)
            return self.search_pages.get(start, _search_page([]))
        if "/digital/api/singleitem/collection/" in url:
            tail = url.split("/singleitem/collection/", 1)[1]
            alias, _, item_id = tail.partition("/id/")
            result = self.details.get((alias, item_id))
            if result is None:
                raise RuntimeError(f"404 {url}")
            return result
        raise AssertionError(f"unexpected url: {url}")


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(id="auc", name="AUC", protocol=Protocol.REST, base_url=AUC)


def _run(details, pages):
    return ContentDmConnector(_descriptor(), FakeHttp(pages, details))


def test_auc_registered_as_contentdm() -> None:
    assert CONNECTORS.get("auc") is ContentDmConnector


@pytest.mark.asyncio
async def test_auc_public_domain_image_is_asset() -> None:
    alias, item_id = "p15795coll2", "3790"
    fields = [
        _field("title", "Title", "[Mediterranean Battle of Abu Kir, 1 August 1798]"),
        _field("date", "Date", "1950"),
        _field("rights", "Rights", "This item is in the public domain."),
    ]
    details = {(alias, item_id): _detail(image_uri=_iiif_http(alias, item_id), fields=fields)}
    connector = _run(details, {0: _search_page([_search_item(alias, item_id)])})

    assets = await connector.search("egypt")

    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "auc"
    assert asset.license == "PDM-1.0"
    assert asset.title == "[Mediterranean Battle of Abu Kir, 1 August 1798]"
    assert asset.year == 1950
    # http imageUri upgraded to https, then bounded to the IIIF size variants
    assert asset.image_url == (
        f"{AUC}/iiif/2/{alias}:{item_id}/full/!1200,1200/0/default.jpg"
    )
    assert asset.thumbnail_url == (
        f"{AUC}/iiif/2/{alias}:{item_id}/full/!400,400/0/default.jpg"
    )
    assert asset.image_url.startswith("https://")
    assert asset.extra["alias"] == alias
    assert asset.extra["item_id"] == item_id
    assert asset.extra["content_type"] == "image/jp2"


@pytest.mark.asyncio
async def test_auc_copyrighted_photograph_is_rejected() -> None:
    alias, item_id = "p15795coll37", "1"
    fields = [
        _field("title", "Title", "AUC campus photograph"),
        _field("rights", "Rights", "Copyright the American University in Cairo."),
        _field("access", "Access", "Contact host for permission to use."),
    ]
    details = {(alias, item_id): _detail(image_uri=_iiif_http(alias, item_id), fields=fields)}
    connector = _run(details, {0: _search_page([_search_item(alias, item_id)])})

    assets = await connector.search("cairo")

    assert assets == []


@pytest.mark.asyncio
async def test_auc_non_image_item_is_rejected() -> None:
    alias, item_id = "p15795coll2", "2"
    fields = [_field("rights", "Rights", "This item is in the public domain.")]
    details = {
        (alias, item_id): _detail(content_type="application/octet-stream", fields=fields)
    }
    connector = _run(details, {0: _search_page([_search_item(alias, item_id)])})

    assets = await connector.search("egypt")

    assert assets == []
