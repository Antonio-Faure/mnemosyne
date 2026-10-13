"""Wellesley College Digital Repository — IIIF source (mocked, offline).

Wellesley College's institutional repository (https://repository.wellesley.edu,
an Islandora/Drupal stack) serves IIIF Presentation manifests per node at
``/node/<nid>/manifest``. The host exposes no aggregate IIIF Collection
manifest, so the source is a single-manifest entry point handled by the generic
``src/mnemosyne/sources/iiif.py`` connector.

NOTE (access): the whole host currently sits behind an origin-side Cloudflare
Turnstile challenge — every content path (including the manifest) answers HTTP
200 with the challenge HTML to non-JavaScript clients, so the connector cannot
fetch at runtime. The descriptor records the entry point so the source can be
harvested as soon as the block is lifted. These tests stay fully offline.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.iiif import IIIFConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"
MANIFEST_URL = "https://repository.wellesley.edu/node/33362/manifest"
IMAGE_SERVICE = "https://repository.wellesley.edu/iiif/2/33362%2F00001"

# Shape mirrors an Islandora IIIF Presentation v3 manifest.
MANIFEST = {
    "@context": "http://iiif.io/api/presentation/3/context.json",
    "id": MANIFEST_URL,
    "type": "Manifest",
    "label": {"en": ["[Manuscript leaf]"]},
    "metadata": [
        {"label": {"en": ["Title"]}, "value": {"en": ["[Manuscript leaf]"]}},
        {"label": {"en": ["Date"]}, "value": {"en": ["15th century"]}},
    ],
    "rights": "http://rightsstatements.org/vocab/NoC-US/1.0/",
    "thumbnail": [
        {
            "id": f"{IMAGE_SERVICE}/full/512,/0/default.jpg",
            "type": "Image",
            "service": [
                {"id": IMAGE_SERVICE, "type": "ImageService3", "profile": "level2"}
            ],
        }
    ],
    "items": [
        {
            "id": "https://repository.wellesley.edu/node/33362/canvas/1",
            "type": "Canvas",
            "items": [
                {
                    "id": "https://repository.wellesley.edu/node/33362/canvas/1/page",
                    "type": "AnnotationPage",
                    "items": [
                        {
                            "id": "https://repository.wellesley.edu/node/33362/canvas/1/annotation",
                            "type": "Annotation",
                            "body": {
                                "id": f"{IMAGE_SERVICE}/full/full/0/default.jpg",
                                "type": "Image",
                                "service": [
                                    {
                                        "id": IMAGE_SERVICE,
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

    async def get_json(self, url, **kwargs):
        return self.routes[url]


def _data() -> dict:
    return yaml.safe_load((SOURCES_DIR / "wellesley.yaml").read_text(encoding="utf-8"))


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(**_data())


def test_descriptor_is_keyless_single_manifest_iiif():
    data = _data()
    assert data["id"] == "wellesley"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["base_url"] == "https://repository.wellesley.edu"
    assert data["license"]
    assert data["extra"]["manifest"] == MANIFEST_URL
    assert data["extra"]["collection_id"] == "33362"
    # no aggregate IIIF Collection was reachable -> single-manifest entry point
    assert "collection" not in data["extra"]


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
    assert asset.source_id == "wellesley"
    assert asset.title == "[Manuscript leaf]"
    assert asset.date_text == "15th century"
    assert asset.year is None  # no machine-readable year in the label
    assert asset.image_url == f"{IMAGE_SERVICE}/full/max/0/default.jpg"
    assert asset.thumbnail_url == f"{IMAGE_SERVICE}/full/512,/0/default.jpg"
    # a top-level IIIF `rights` is carried onto the Asset
    assert asset.license == "http://rightsstatements.org/vocab/NoC-US/1.0/"
    assert asset.page_url == MANIFEST_URL


@pytest.mark.asyncio
async def test_search_filters_by_query():
    http = FakeHttp({MANIFEST_URL: MANIFEST})
    connector = IIIFConnector(_descriptor(), http)

    assert await connector.search("nonexistentterm", limit=10) == []
    assert len(await connector.search("manuscript", limit=10)) == 1
