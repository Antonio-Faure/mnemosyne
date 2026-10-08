"""Belvedere (Sammlung Online) IIIF source — mocked end-to-end.

The host is an eMuseum instance that serves *per-object* IIIF Presentation v2
manifests at `/apis/iiif/presentation/v2/1-objects-<id>/manifest` (the
`/mirador/objects/<id>` viewer page references it). No aggregate Collection
manifest exists (probes return 400/404), so the descriptor points the generic
`src/mnemosyne/sources/iiif.py` connector at a single manifest via
`extra.manifest`. No bespoke connector is needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.iiif import IIIFConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"
DESCRIPTOR = SOURCES_DIR / "belvedere.yaml"

MANIFEST_URL = (
    "https://sammlung.belvedere.at/apis/iiif/presentation/v2/1-objects-91683/manifest"
)
IMAGE_SERVICE = "https://sammlung.belvedere.at/apis/iiif/image/v2/132224"

# Shape mirrors the live manifest (v2 `sc:Manifest`) for object 91683.
MANIFEST = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@id": MANIFEST_URL,
    "@type": "sc:Manifest",
    "label": "Envol",
    "attribution": "© Bildrecht, Wien 2026",
    "sequences": [
        {
            "@type": "sc:Sequence",
            "canvases": [
                {
                    "@type": "sc:Canvas",
                    "label": (
                        "Louise Janin, Envol, 1955, Öl auf Leinwand, 38 × 46 cm, "
                        "Belvedere, Wien, Inv.-Nr. Lg 1951"
                    ),
                    "width": 1123,
                    "height": 929,
                    "images": [
                        {
                            "@type": "oa:Annotation",
                            "motivation": "sc:painting",
                            "resource": {
                                "@type": "dctypes:Image",
                                "@id": f"{IMAGE_SERVICE}/full/full/0/default.jpg",
                                "format": "image/jpeg",
                                "width": 1123,
                                "height": 929,
                                "service": {
                                    "@id": IMAGE_SERVICE,
                                    "profile": "http://iiif.io/api/image/2/level2.json",
                                },
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
    return yaml.safe_load(DESCRIPTOR.read_text(encoding="utf-8"))


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(**_data())


def test_descriptor_is_keyless_single_manifest_iiif():
    data = _data()
    assert data["id"] == "belvedere"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["base_url"] == "https://sammlung.belvedere.at"
    assert data["extra"]["manifest"] == MANIFEST_URL
    # no aggregate Collection manifest was found on the host
    assert "collection" not in data["extra"]


def test_descriptor_uses_generic_iiif_connector():
    connector = build_connector(_descriptor(), FakeHttp({}))
    assert isinstance(connector, IIIFConnector)
    assert _descriptor().protocol is Protocol.IIIF


@pytest.mark.asyncio
async def test_search_normalizes_v2_manifest():
    http = FakeHttp({MANIFEST_URL: MANIFEST})
    connector = IIIFConnector(_descriptor(), http)

    assets = await connector.search("", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "belvedere"
    assert asset.title == "Envol"
    assert asset.image_url == f"{IMAGE_SERVICE}/full/full/0/default.jpg"
    assert asset.thumbnail_url == f"{IMAGE_SERVICE}/full/512,/0/default.jpg"
    assert asset.iiif_id == IMAGE_SERVICE
    assert asset.license == "varies"


@pytest.mark.asyncio
async def test_search_filters_by_query():
    http = FakeHttp({MANIFEST_URL: MANIFEST})
    connector = IIIFConnector(_descriptor(), http)

    assert await connector.search("nonexistentterm", limit=10) == []
    assert len(await connector.search("envol", limit=10)) == 1
