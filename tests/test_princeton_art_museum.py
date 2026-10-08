"""Princeton University Art Museum (data.artmuseum.princeton.edu) IIIF source.

The host serves one IIIF Presentation v3 manifest per object at
/iiif/objects/<id> (sample object 24237). It declares an aggregate Collection at
/iiif/objects/collection (``partOf``), but that URL and the common
collection/search paths all return 404, and the host's keyless REST object API
has no usable list/search entry point either, so the source is onboarded as a
single manifest handled by the generic ``src/mnemosyne/sources/iiif.py``
connector (v3 ``items``/``body``). Images are served by the IIIF Image API on
media.artmuseum.princeton.edu. Fully offline.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.iiif import IIIFConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"
MANIFEST_URL = "https://data.artmuseum.princeton.edu/iiif/objects/24237"
SERVICE_ID = "https://media.artmuseum.princeton.edu/iiif/2/collection/y1952-40_SL"

LABEL = (
    "Studio of El Greco (Greek, 1541–1614, active in Spain), "
    "Saint Francis of Assisi. Oil on canvas; 62 x 51.5 cm."
)

# Shape mirrors the live Princeton manifest (v3 `Manifest`), trimmed.
MANIFEST = {
    "@context": "http://iiif.io/api/presentation/3/context.json",
    "id": MANIFEST_URL,
    "type": "Manifest",
    "label": {"en": [LABEL]},
    "metadata": [{"label": {"en": ["Description"]}, "value": {"en": [""]}}],
    "requiredStatement": {
        "label": {"en": ["Attribution"]},
        "value": {"en": ["Princeton University Art Museum"]},
    },
    "provider": [
        {
            "id": "https://artmuseum.princeton.edu/about",
            "type": "Agent",
            "label": {"en": ["Princeton University Art Museum"]},
        }
    ],
    "partOf": [
        {
            "id": "https://data.artmuseum.princeton.edu/iiif/objects/collection",
            "type": "Collection",
        }
    ],
    "items": [
        {
            "id": f"{MANIFEST_URL}/canvas/24237-canvas-7204",
            "type": "Canvas",
            "height": 1452,
            "width": 1199,
            "items": [
                {
                    "id": f"{MANIFEST_URL}/page/24237-anno-7204",
                    "type": "AnnotationPage",
                    "items": [
                        {
                            "id": f"{MANIFEST_URL}/annotation/24237-anno-7204",
                            "type": "Annotation",
                            "motivation": "painting",
                            "target": f"{MANIFEST_URL}/canvas/24237-canvas-7204",
                            "body": {
                                "id": (
                                    "https://media.artmuseum.princeton.edu/iiif/3/"
                                    "collection/y1952-40_SL/full/max/0/default.jpg"
                                ),
                                "type": "Image",
                                "format": "image/jpeg",
                                "height": 1452,
                                "width": 1199,
                                "service": [
                                    {
                                        "@id": SERVICE_ID,
                                        "@type": "ImageService2",
                                        "profile": "http://iiif.io/api/image/2/level2.json",
                                    },
                                    {
                                        "id": (
                                            "https://media.artmuseum.princeton.edu/"
                                            "iiif/3/collection/y1952-40_SL"
                                        ),
                                        "type": "ImageService3",
                                        "profile": "level2",
                                    },
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

    async def get_json(self, url, **kwargs):
        return self.routes[url]


def _descriptor() -> SourceDescriptor:
    data = yaml.safe_load(
        (SOURCES_DIR / "princeton_art_museum.yaml").read_text(encoding="utf-8")
    )
    return SourceDescriptor(**data)


def test_descriptor_is_keyless_single_manifest_iiif():
    data = yaml.safe_load(
        (SOURCES_DIR / "princeton_art_museum.yaml").read_text(encoding="utf-8")
    )
    assert data["id"] == "princeton_art_museum"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["base_url"] == "https://data.artmuseum.princeton.edu"
    assert data["extra"]["manifest"] == MANIFEST_URL
    assert data["extra"]["collection_id"] == "24237"


def test_descriptor_uses_generic_iiif_connector():
    connector = build_connector(_descriptor(), FakeHttp({}))
    assert isinstance(connector, IIIFConnector)


@pytest.mark.asyncio
async def test_search_normalizes_v3_manifest():
    http = FakeHttp({MANIFEST_URL: MANIFEST})
    connector = IIIFConnector(_descriptor(), http)

    assets = await connector.search("", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "princeton_art_museum"
    assert asset.title == LABEL
    # The manifest carries no dated metadata -> no machine-readable year.
    assert asset.year is None
    # No `rights`/`license` in the manifest -> the descriptor licence is carried.
    assert asset.license == "varies"
    assert asset.iiif_id == SERVICE_ID
    assert asset.image_url == f"{SERVICE_ID}/full/full/0/default.jpg"
    assert asset.thumbnail_url == f"{SERVICE_ID}/full/512,/0/default.jpg"


@pytest.mark.asyncio
async def test_search_filters_by_query():
    http = FakeHttp({MANIFEST_URL: MANIFEST})
    connector = IIIFConnector(_descriptor(), http)

    assert await connector.search("nonexistentterm", limit=10) == []
    assert len(await connector.search("greco", limit=10)) == 1


def test_protocol_enum_has_iiif():
    assert Protocol.IIIF.value == "iiif"
