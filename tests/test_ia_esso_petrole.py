"""ESSO France corpus on the Internet Archive: discovery + IIIF (offline)."""

from __future__ import annotations

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.ia_esso_petrole import IaEssoPetroleConnector

BASE = "https://archive.org/advancedsearch.php"
IDENT = "usine-parentis-1955"
MANIFEST_URL = f"https://iiif.archive.org/iiif/{IDENT}/manifest.json"
SERVICE = f"https://iiif.archive.org/image/iiif/3/{IDENT}%2Fpage%2F0000.jp2"

DOCS = {
    "response": {
        "docs": [
            {
                "identifier": IDENT,
                "title": "Histoire De Parentis ESSO 1955",
                "description": ["Forages et puits à Parentis-en-Born"],
                "date": "1955-05-02T00:00:00Z",
            }
        ]
    }
}

MANIFEST = {
    "id": MANIFEST_URL,
    "type": "Manifest",
    "items": [
        {
            "type": "Canvas",
            "items": [
                {
                    "type": "AnnotationPage",
                    "items": [
                        {
                            "type": "Annotation",
                            "body": {
                                "id": f"{SERVICE}/full/max/0/default.jpg",
                                "type": "Image",
                                "service": [
                                    {
                                        "id": SERVICE,
                                        "type": "ImageService3",
                                        "profile": "level2",
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
    ],
}


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def get_json(self, url, **kwargs):
        self.calls.append((url, kwargs))
        try:
            return self.routes[url]
        except KeyError:
            raise RuntimeError(f"unexpected url {url}") from None


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="ia_esso_petrole",
        name="ESSO France (Internet Archive)",
        protocol=Protocol.IIIF,
        base_url=BASE,
        auth="none",
        license="unknown",
        rights="link only",
        extra={
            "search_query": 'title:"ESSO REVUE"',
            "manifest_template": (
                "https://iiif.archive.org/iiif/{identifier}/manifest.json"
            ),
            "rows": 80,
        },
    )


@pytest.mark.asyncio
async def test_search_builds_iiif_asset_from_manifest():
    http = FakeHttp({BASE: DOCS, MANIFEST_URL: MANIFEST})
    connector = IaEssoPetroleConnector(_descriptor(), http)

    assets = await connector.search("Parentis pétrole", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "ia_esso_petrole"
    assert asset.source_asset_id == IDENT
    assert asset.title == "Histoire De Parentis ESSO 1955"
    assert asset.year == 1955
    assert asset.iiif_id == SERVICE
    assert asset.image_url == f"{SERVICE}/full/!400,400/0/default.jpg"
    assert asset.thumbnail_url == f"{SERVICE}/full/!200,200/0/default.jpg"
    assert asset.page_url == f"https://archive.org/details/{IDENT}"
    assert asset.extra["ia_identifier"] == IDENT
    assert asset.extra["iiif_manifest"] == MANIFEST_URL

    # discovery hits advanced search with the corpus query + JSON output
    query_url, query_kwargs = http.calls[0]
    assert query_url == BASE
    assert query_kwargs["params"]["q"] == 'title:"ESSO REVUE"'
    assert query_kwargs["params"]["output"] == "json"


@pytest.mark.asyncio
async def test_search_falls_back_to_thumbnail_when_manifest_missing():
    http = FakeHttp({BASE: DOCS})  # no manifest route -> get_json raises
    connector = IaEssoPetroleConnector(_descriptor(), http)

    assets = await connector.search("Parentis", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.image_url == f"https://archive.org/services/img/{IDENT}"
    assert asset.extra["ia_identifier"] == IDENT


@pytest.mark.asyncio
async def test_search_returns_empty_when_no_docs():
    http = FakeHttp({BASE: {"response": {"docs": []}}})
    connector = IaEssoPetroleConnector(_descriptor(), http)
    assert await connector.search("rien", limit=10) == []


@pytest.mark.asyncio
async def test_limit_zero_short_circuits():
    http = FakeHttp({})  # must not be called
    connector = IaEssoPetroleConnector(_descriptor(), http)
    assert await connector.search("Parentis", limit=0) == []
    assert http.calls == []
