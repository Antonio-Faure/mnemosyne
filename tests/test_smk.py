"""SMK (Statens Museum for Kunst) IIIF source — mocked end-to-end.

SMK serves one IIIF Presentation v3 manifest per object at
`api/v1/iiif/manifest?id=<OBJECT_NUMBER>` (the search API `api/v1/art/search/`
returns each item's `iiif_manifest` URL). There is no IIIF Collection manifest
(`api/v1/iiif/collection` → 404), so the host is onboarded as a single-manifest
IIIF source and the generic `src/mnemosyne/sources/iiif.py` connector handles it
(confirmed discovery via fetch_url), so no bespoke connector is needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.iiif import IIIFConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"
MANIFEST_URL = "https://api.smk.dk/api/v1/iiif/manifest?id=KKS5261"
SERVICE = "https://iip.smk.dk/iiif/jp2/qz20sx771_kks5261.tif.jp2"
THUMB = "https://iip-thumb.smk.dk/iiif/jp2/qz20sx771_kks5261.tif.jp2/full/!1024,/0/default.jpg"

# Shape mirrors the live KKS5261 manifest (v3 Presentation, keyless Image API v2).
MANIFEST = {
    "@context": "http://iiif.io/api/presentation/3/context.json",
    "id": MANIFEST_URL,
    "type": "Manifest",
    "label": {"da": ["Augustus og den tiburtinske sibylle"]},
    "rights": "https://creativecommons.org/publicdomain/mark/1.0/",
    "provider": [
        {
            "id": "https://www.smk.dk",
            "type": "Agent",
            "label": {"en": ["SMK – the national gallery of Denmark"]},
        }
    ],
    "metadata": [
        {
            "label": {"en": ["Title"]},
            "value": {"none": ["Augustus og den tiburtinske sibylle"]},
        },
        {"label": {"en": ["Object number"]}, "value": {"none": ["KKS5261"]}},
        {
            "label": {"en": ["Creator"]},
            "value": {"none": ["Trento, Antonio da", "Parmigianino"]},
        },
    ],
    "thumbnail": [
        {
            "id": THUMB,
            "type": "Image",
            "format": "image/jpeg",
            "service": [{"id": SERVICE, "type": "ImageService2", "profile": "level1"}],
        }
    ],
    "items": [
        {
            "id": "https://api.smk.dk/api/v1/iiif/canvas/KKS5261/0",
            "type": "Canvas",
            "height": 6287,
            "width": 4992,
            "items": [
                {
                    "id": "https://api.smk.dk/api/v1/iiif/canvas/KKS5261/0/page",
                    "type": "AnnotationPage",
                    "items": [
                        {
                            "id": "https://api.smk.dk/api/v1/iiif/canvas/KKS5261/0/annotation",
                            "type": "Annotation",
                            "motivation": "painting",
                            "body": {
                                "id": THUMB,
                                "type": "Image",
                                "format": "image/jpeg",
                                "service": [
                                    {
                                        "id": SERVICE,
                                        "type": "ImageService2",
                                        "profile": "level1",
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


def _descriptor() -> SourceDescriptor:
    data = yaml.safe_load((SOURCES_DIR / "smk.yaml").read_text(encoding="utf-8"))
    return SourceDescriptor(**data)


def test_descriptor_is_keyless_single_manifest_iiif():
    data = yaml.safe_load((SOURCES_DIR / "smk.yaml").read_text(encoding="utf-8"))
    assert data["id"] == "smk"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["base_url"] == "https://api.smk.dk"
    assert data["extra"]["manifest"] == MANIFEST_URL
    assert data["extra"]["collection_id"] == "KKS5261"
    assert data["license"]


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
    assert asset.source_id == "smk"
    assert asset.source_asset_id == MANIFEST_URL
    assert asset.title == "Augustus og den tiburtinske sibylle"
    assert asset.creator == "Trento, Antonio da"
    assert asset.page_url == MANIFEST_URL
    assert asset.image_url == f"{SERVICE}/full/full/0/default.jpg"
    assert asset.thumbnail_url == f"{SERVICE}/full/512,/0/default.jpg"
    assert asset.iiif_id == SERVICE
    assert asset.license == "https://creativecommons.org/publicdomain/mark/1.0/"


@pytest.mark.asyncio
async def test_search_filters_by_query():
    http = FakeHttp({MANIFEST_URL: MANIFEST})
    connector = IIIFConnector(_descriptor(), http)

    assert await connector.search("nonexistentterm", limit=10) == []
    assert len(await connector.search("sibylle", limit=10)) == 1


def test_protocol_enum_has_iiif():
    assert Protocol.IIIF.value == "iiif"
