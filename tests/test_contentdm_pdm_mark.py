"""Regression: CONTENTdm Public Domain Mark 1.0 must count as open (offline).

Bug found in the #146 audit: ``_OPEN_MARKERS`` recognised the CC0
``creativecommons.org/publicdomain/zero`` URL and the human text
``public domain`` but **not** the canonical Public Domain Mark 1.0 URL
``https://creativecommons.org/publicdomain/mark/1.0/`` — which has no space
between "public" and "domain". Penn State maps carry exactly that statement,
so they were silently dropped even though the descriptor advertises
``PDM-1.0`` as a supported licence.

These tests are fully offline: a tiny ``_FakeHttp`` serves canned JSON, so the
regression runs without touching any CONTENTdm host.
"""

from __future__ import annotations

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.contentdm import ContentDmConnector

PENN_STATE = "https://digital.libraries.psu.edu"


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="penn_state", name="penn_state", protocol=Protocol.REST, base_url=PENN_STATE
    )


def _field(key: str, label: str, value: str) -> dict:
    return {"key": key, "label": label, "value": value}


class _FakeHttp:
    """Serve one canned search page and one canned single-item detail."""

    def __init__(self, search_page: dict, detail: dict) -> None:
        self.search_page = search_page
        self.detail = detail

    async def get_json(self, url, **kwargs):
        if "/digital/api/search/searchterm/" in url:
            return self.search_page
        if "/digital/api/singleitem/collection/" in url:
            return self.detail
        raise AssertionError(f"unexpected url: {url}")


def _connector(rights_text: str) -> ContentDmConnector:
    alias, item_id = "maps1", "0"
    detail = {
        "contentType": "image/jp2",
        "imageUri": f"{PENN_STATE}/iiif/2/{alias}:{item_id}/full/full/0/default.jpg",
        "fields": [
            _field("title", "Title", "Map of Pennsylvania"),
            _field("rights", "Rights", rights_text),
        ],
    }
    search_page = {
        "totalResults": 1,
        "items": [{"collectionAlias": alias, "itemId": item_id}],
    }
    return ContentDmConnector(_descriptor(), _FakeHttp(search_page, detail))


@pytest.mark.asyncio
async def test_public_domain_mark_url_is_open():
    connector = _connector("https://creativecommons.org/publicdomain/mark/1.0/")
    assets = await connector.search("map")
    assert len(assets) == 1
    asset = assets[0]
    assert asset.license == "PDM-1.0"
    assert asset.extra["rights_uri"] == "https://creativecommons.org/publicdomain/mark/1.0/"


@pytest.mark.asyncio
async def test_public_domain_mark_text_is_open():
    connector = _connector("Public Domain Mark 1.0")
    assets = await connector.search("map")
    assert len(assets) == 1
    assert assets[0].license == "PDM-1.0"


@pytest.mark.asyncio
async def test_reserved_rights_still_rejected_despite_pdm_substring():
    # A record that explicitly reserves rights must stay rejected even when it
    # happens to mention the public-domain-mark vocabulary: BAD markers win.
    connector = _connector(
        "All rights reserved. See creativecommons.org/publicdomain/mark/1.0/ for reference."
    )
    assets = await connector.search("map")
    assert assets == []
