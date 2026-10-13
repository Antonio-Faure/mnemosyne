"""BSB (Bayerische Staatsbibliothek) IIIF collection source — mocked end-to-end.

The host's enumerable entry point is the top-level IIIF Collection manifest
(`iiif/presentation/v2/collection/top`) which lists v2 `sc:Manifest` entries
whose images are served by the IIIF Image API. The generic
`src/mnemosyne/sources/iiif.py` connector handles both the collection traversal
(confirmed discovery via fetch_url) and the v2 manifest normalization, so no
bespoke connector is needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.iiif import IIIFConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"
DESCRIPTOR = SOURCES_DIR / "bsb_collection.yaml"
COLLECTION_URL = (
    "https://api.digitale-sammlungen.de/iiif/presentation/v2/collection/top"
)
M1 = "https://api.digitale-sammlungen.de/iiif/presentation/v2/bsb12188487/manifest"
M2 = "https://api.digitale-sammlungen.de/iiif/presentation/v2/bsb10598831/manifest"
NEXT_URL = COLLECTION_URL + "/AoIIP4AAACtic2IxMjE4NzIzMg=="

# Shape mirrors the live collection response (v2 `sc:Collection`, paginated).
COLLECTION = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@type": "sc:Collection",
    "@id": COLLECTION_URL,
    "label": "Collection 'top'",
    "total": 3212019,
    "next": NEXT_URL,
    "manifests": [
        {"@type": "sc:Manifest", "@id": M1, "label": "Die Glori der Lutherischen Kirch"},
    ],
}

# The `next` page of the collection (second manifest lives there).
PAGE_2 = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@type": "sc:Collection",
    "@id": NEXT_URL,
    "manifests": [
        {
            "@type": "sc:Manifest",
            "@id": M2,
            "label": "Kornmüller, Utto: Lexikon der kirchlichen Tonkunst",
        },
    ],
}

# Shape mirrors the live bsb10598831 manifest (v2 `sc:Manifest`).
MANIFEST_2 = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@type": "sc:Manifest",
    "@id": M2,
    "label": "Kornmüller, Utto: Lexikon der kirchlichen Tonkunst",
    "metadata": [{"label": "Date", "value": "1870"}],
    "sequences": [
        {
            "canvases": [
                {
                    "images": [
                        {
                            "resource": {
                                "@id": "https://api.digitale-sammlungen.de/iiif/image/v2/"
                                "bsb10598831_00001/full/full/0/default.jpg",
                                "service": {
                                    "@id": "https://api.digitale-sammlungen.de/iiif/"
                                    "image/v2/bsb10598831_00001"
                                },
                            }
                        }
                    ]
                }
            ]
        }
    ],
}

# A second v2 manifest with no date metadata (title-only filtering).
MANIFEST_1 = {
    "@type": "sc:Manifest",
    "@id": M1,
    "label": "Die Glori der Lutherischen Kirch",
    "sequences": [
        {
            "canvases": [
                {
                    "images": [
                        {
                            "resource": {
                                "@id": "https://api.digitale-sammlungen.de/iiif/image/v2/"
                                "bsb12188487_00001/full/full/0/default.jpg",
                                "service": {
                                    "@id": "https://api.digitale-sammlungen.de/iiif/"
                                    "image/v2/bsb12188487_00001"
                                },
                            }
                        }
                    ]
                }
            ]
        }
    ],
}


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes
        self.calls: list[str] = []

    async def get_json(self, url, **kwargs):
        self.calls.append(url)
        return self.routes[url]


def _routes() -> dict:
    return {COLLECTION_URL: COLLECTION, NEXT_URL: PAGE_2, M1: MANIFEST_1, M2: MANIFEST_2}


def _raw() -> dict:
    return yaml.safe_load(DESCRIPTOR.read_text(encoding="utf-8"))


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(**_raw())


def test_descriptor_is_keyless_collection_iiif():
    data = _raw()
    assert data["id"] == "bsb_collection"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["base_url"] == "https://api.digitale-sammlungen.de"
    assert data["extra"]["collection"] == COLLECTION_URL
    assert data["extra"]["collection_id"] == "top"


def test_descriptor_uses_generic_iiif_connector():
    connector = build_connector(_descriptor(), FakeHttp({}))
    assert isinstance(connector, IIIFConnector)


def test_protocol_enum_has_iiif():
    assert Protocol.IIIF.value == "iiif"


@pytest.mark.asyncio
async def test_search_walks_collection_and_normalizes_v2_manifest():
    http = FakeHttp(_routes())
    connector = IIIFConnector(_descriptor(), http)

    assets = await connector.search("lexikon", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "bsb_collection"
    assert asset.title == "Kornmüller, Utto: Lexikon der kirchlichen Tonkunst"
    assert asset.year == 1870
    assert asset.image_url == (
        "https://api.digitale-sammlungen.de/iiif/image/v2/bsb10598831_00001"
        "/full/full/0/default.jpg"
    )
    assert asset.thumbnail_url == (
        "https://api.digitale-sammlungen.de/iiif/image/v2/bsb10598831_00001"
        "/full/512,/0/default.jpg"
    )


@pytest.mark.asyncio
async def test_search_without_query_returns_all_manifests():
    http = FakeHttp(_routes())
    connector = IIIFConnector(_descriptor(), http)

    assets = await connector.search("", limit=10)
    assert len(assets) == 2
    # the second manifest only exists on the `next` page: pagination was walked
    assert NEXT_URL in http.calls


@pytest.mark.asyncio
async def test_search_filters_by_query():
    http = FakeHttp(_routes())
    connector = IIIFConnector(_descriptor(), http)

    assert await connector.search("nonexistentterm", limit=10) == []
