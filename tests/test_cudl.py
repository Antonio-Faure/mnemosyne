"""CUDL (Cambridge Digital Library) IIIF source — mocked end-to-end.

The Cairo Genizah IIIF Collection (`iiif/collection/genizah`) enumerates v2
`sc:Manifest` entries whose images are served by the IIIF Image API. The generic
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
COLLECTION_URL = "https://cudl.lib.cam.ac.uk/iiif/collection/genizah"
MANIFEST_URL = "https://cudl.lib.cam.ac.uk/iiif/MS-TS-00016-00320"

# Shape mirrors the live collection response (v2 `sc:Collection`).
COLLECTION = {
    "@type": "sc:Collection",
    "label": "Cairo Genizah",
    "manifests": [
        {"@type": "sc:Manifest", "label": "MS-TS-00016-00320", "@id": MANIFEST_URL},
    ],
}

# Shape mirrors the live MS-TS-00016-00320 manifest (v2 `sc:Manifest`).
MANIFEST = {
    "@type": "sc:Manifest",
    "@id": MANIFEST_URL,
    "label": "Palimpsest; Talmud Yerušalmi; Greek Bible (Septuagint)",
    "attribution": "Provided by Cambridge University Library.",
    "metadata": [
        {"label": "Date of Creation", "value": "5th-6th century"},
        {"label": "Subject(s)", "value": "Cairo Genizah"},
        {"label": "Classmark", "value": "T-S 16.320"},
    ],
    "sequences": [
        {
            "canvases": [
                {
                    "images": [
                        {
                            "resource": {
                                "@id": "https://cudl.lib.cam.ac.uk/iiif/MS-TS-00016-00320/"
                                "canvas/1/full/full/0/default.jpg",
                                "service": {
                                    "@id": "https://cudl.lib.cam.ac.uk/iiif/"
                                    "MS-TS-00016-00320/canvas/1"
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

    async def get_json(self, url, **kwargs):
        return self.routes[url]


def _descriptor() -> SourceDescriptor:
    data = yaml.safe_load((SOURCES_DIR / "cudl.yaml").read_text(encoding="utf-8"))
    return SourceDescriptor(**data)


def test_descriptor_is_keyless_collection_iiif():
    data = yaml.safe_load((SOURCES_DIR / "cudl.yaml").read_text(encoding="utf-8"))
    assert data["id"] == "cudl"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["base_url"] == "https://cudl.lib.cam.ac.uk"
    assert data["extra"]["collection"] == COLLECTION_URL
    assert data["extra"]["collection_id"]


def test_descriptor_uses_generic_iiif_connector():
    connector = build_connector(_descriptor(), FakeHttp({}))
    assert isinstance(connector, IIIFConnector)


@pytest.mark.asyncio
async def test_search_walks_collection_and_normalizes_v2_manifest():
    http = FakeHttp({COLLECTION_URL: COLLECTION, MANIFEST_URL: MANIFEST})
    connector = IIIFConnector(_descriptor(), http)

    assets = await connector.search("", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "cudl"
    assert asset.title == "Palimpsest; Talmud Yerušalmi; Greek Bible (Septuagint)"
    assert asset.date_text == "5th-6th century"
    # "5th-6th century" carries no machine-readable year, so no year is set.
    assert asset.year is None
    assert asset.image_url == (
        "https://cudl.lib.cam.ac.uk/iiif/MS-TS-00016-00320/canvas/1/full/full/0/default.jpg"
    )
    assert asset.thumbnail_url == (
        "https://cudl.lib.cam.ac.uk/iiif/MS-TS-00016-00320/canvas/1/full/512,/0/default.jpg"
    )
    assert asset.license == "https://creativecommons.org/licenses/by-nc/4.0/"


@pytest.mark.asyncio
async def test_search_filters_by_query():
    http = FakeHttp({COLLECTION_URL: COLLECTION, MANIFEST_URL: MANIFEST})
    connector = IIIFConnector(_descriptor(), http)

    assert await connector.search("nonexistentterm", limit=10) == []
    assert len(await connector.search("palimpsest", limit=10)) == 1


def test_protocol_enum_has_iiif():
    assert Protocol.IIIF.value == "iiif"
