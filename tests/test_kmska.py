"""KMSKA (Royal Museum of Fine Arts Antwerp) IIIF source — mocked end-to-end.

The host runs Imagehub (Vlaamse Kunstcollectie); its top-level IIIF Collection
(`iiif/2/collection/manifest.json`, "Top Level Collection for Imagehub")
enumerates v2 `sc:Manifest` entries whose images are served by the IIIF Image
API. The generic `src/mnemosyne/sources/iiif.py` connector handles both the
collection traversal (confirmed discovery via fetch_url) and the v2 manifest
normalization (including the v2 `{"@language": …, "@value": …}` labels), so no
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
COLLECTION_URL = "https://iiif.kmska.be/iiif/2/collection/manifest.json"
MANIFEST_URL = "https://iiif.kmska.be/iiif/2/10741/manifest.json"

# The live manifest's `sequences` block (canvas → image → service) sits beyond
# the fetch tool's ~3.6k-char truncation, so the exact Cantaloupe service id was
# not captured. This fixture mirrors that shape with a representative id; the
# connector simply appends the IIIF Image API request parameters to it.
IMAGE_SERVICE = "https://iiif.kmska.be/iiif/2/10741/canvas/1"

# Shape mirrors the live collection response (v2 `sc:Collection`).
COLLECTION = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@id": "https://iiif.kmska.be/iiif/2/collection/top",
    "@type": "sc:Collection",
    "label": "Top Level Collection for Imagehub",
    "viewingHint": "top",
    "manifests": [
        {
            "@id": MANIFEST_URL,
            "@type": "sc:Manifest",
            "label": [
                {"@language": "en", "@value": "Landscape"},
                {"@language": "nl", "@value": "Landschap"},
            ],
        },
    ],
}

# Shape mirrors the live 10741 manifest (v2 `sc:Manifest`, v2 `@value` labels).
MANIFEST = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@id": MANIFEST_URL,
    "@type": "sc:Manifest",
    "label": [
        {"@language": "en", "@value": "Landscape"},
        {"@language": "nl", "@value": "Landschap"},
    ],
    "metadata": [
        {
            "label": [
                {"@language": "en", "@value": "Title"},
                {"@language": "nl", "@value": "Titel"},
            ],
            "value": [
                {"@language": "en", "@value": "Landscape"},
                {"@language": "nl", "@value": "Landschap"},
            ],
        },
        {
            "label": [
                {"@language": "en", "@value": "Creator"},
                {"@language": "nl", "@value": "Vervaardiger"},
            ],
            "value": "Schilder: Ramah",
        },
        {
            "label": [
                {"@language": "en", "@value": "Inventory no."},
                {"@language": "nl", "@value": "Inventarisnummer"},
            ],
            "value": "3985",
        },
    ],
    "license": "https://creativecommons.org/publicdomain/mark/1.0/",
    "sequences": [
        {
            "canvases": [
                {
                    "images": [
                        {
                            "resource": {
                                "@id": f"{IMAGE_SERVICE}/full/full/0/default.jpg",
                                "service": {"@id": IMAGE_SERVICE},
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
    data = yaml.safe_load((SOURCES_DIR / "kmska.yaml").read_text(encoding="utf-8"))
    return SourceDescriptor(**data)


def test_descriptor_is_keyless_collection_iiif():
    data = yaml.safe_load((SOURCES_DIR / "kmska.yaml").read_text(encoding="utf-8"))
    assert data["id"] == "kmska"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["base_url"] == "https://iiif.kmska.be"
    assert data["extra"]["collection"] == COLLECTION_URL
    assert data["extra"]["collection_id"] == "top"
    assert data["license"]


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
    assert asset.source_id == "kmska"
    assert asset.title == "Landscape"
    assert asset.creator == "Schilder: Ramah"
    assert asset.license == "https://creativecommons.org/publicdomain/mark/1.0/"
    assert asset.image_url == f"{IMAGE_SERVICE}/full/full/0/default.jpg"
    assert asset.thumbnail_url == f"{IMAGE_SERVICE}/full/512,/0/default.jpg"


@pytest.mark.asyncio
async def test_search_filters_by_query():
    http = FakeHttp({COLLECTION_URL: COLLECTION, MANIFEST_URL: MANIFEST})
    connector = IIIFConnector(_descriptor(), http)

    assert await connector.search("nonexistentterm", limit=10) == []
    assert len(await connector.search("landscape", limit=10)) == 1


def test_protocol_enum_has_iiif():
    assert Protocol.IIIF.value == "iiif"
