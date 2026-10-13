"""Wikidata: entity search + P18 image via SPARQL into canonical assets (offline)."""

from __future__ import annotations

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.wikidata import WikidataConnector

BINDING = {
    "item": {"value": "http://www.wikidata.org/entity/Q1"},
    "itemLabel": {"value": "Usine de Lacq"},
    "image": {"value": "http://commons.wikimedia.org/wiki/Special:FilePath/Lacq.jpg"},
}


class FakeHttp:
    def __init__(self, search: dict, sparql: dict) -> None:
        self.search = search
        self.sparql = sparql
        self.calls: list[tuple[str, dict]] = []

    async def get_json(self, url, **kwargs):
        self.calls.append((url, kwargs))
        params = kwargs.get("params") or {}
        if params.get("action") == "wbsearchentities":
            return self.search
        return self.sparql


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="wikidata",
        name="Wikidata",
        protocol=Protocol.SPARQL,
        base_url="https://www.wikidata.org/",
        auth="none",
        license="CC0",
    )


@pytest.mark.asyncio
async def test_search_resolves_entities_then_fetches_the_p18_image():
    http = FakeHttp(
        {"search": [{"id": "Q1"}]},
        {"results": {"bindings": [BINDING, {"item": {"value": "Q2"}}]}},  # no image
    )
    connector = WikidataConnector(_descriptor(), http)

    assets = await connector.search("usine de Lacq", limit=5)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.title == "Usine de Lacq"
    assert asset.image_url == (
        "https://commons.wikimedia.org/wiki/Special:FilePath/Lacq.jpg"  # http -> https
    )
    assert asset.thumbnail_url.endswith("?width=512")
    assert asset.page_url == "http://www.wikidata.org/entity/Q1"
    assert asset.extra["qid"] == "Q1"
    assert asset.extra["image_file"] == "Lacq.jpg"

    assert len(http.calls) == 2
    assert http.calls[0][1]["params"]["search"] == "usine de Lacq"
    assert "wd:Q1" in http.calls[1][1]["params"]["query"]


@pytest.mark.asyncio
async def test_search_without_entities_returns_empty():
    connector = WikidataConnector(_descriptor(), FakeHttp({"search": []}, {}))
    assert await connector.search("inconnu") == []
