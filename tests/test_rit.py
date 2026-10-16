"""Rochester Institute of Technology (RIT) Digital Collections — mocked end-to-end.

RIT runs its digital collections on the Luna image server, which exposes
*per-object* IIIF Presentation v2 manifests at
`/luna/servlet/iiif/m/<object-id>/manifest`. Probes for an aggregate IIIF
Collection manifest (`/iiif/collection/...`, `/iiif/collection/top`,
`/iiif/collection`) return the Luna HTML web UI (or 404), so no Collection entry
point exists. The generic `src/mnemosyne/sources/iiif.py` connector consumes a
manifest, so the descriptor points it at a single manifest via `extra.manifest`.
No bespoke connector is needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import SourceDescriptor
from mnemosyne.sources.iiif import IIIFConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"
DESCRIPTOR = SOURCES_DIR / "rit.yaml"

MANIFEST_URL = (
    "https://digitalcollections.rit.edu/luna/servlet/iiif/m/RIT~1~1~105~3287/manifest"
)
IMAGE_SERVICE = "https://digitalcollections.rit.edu/luna/servlet/iiif/RIT~1~1~105~3287"

# Shape mirrors the live Luna manifest (v2 `sc:Manifest`) for object
# RIT~1~1~105~3287 ("Bible", Cary Graphic Arts Collection).
MANIFEST = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@id": MANIFEST_URL,
    "@type": "sc:Manifest",
    "label": "Bible",
    "attribution": "RIT CARY GRAPHIC ARTS COLLECTION",
    "metadata": [
        {"label": "Date", "value": "1200"},
        {"label": "Collection", "value": "Cary Graphic Arts Collection"},
    ],
    "sequences": [
        {
            "@type": "sc:Sequence",
            "canvases": [
                {
                    "@type": "sc:Canvas",
                    "@id": f"{MANIFEST_URL}/canvas/1",
                    "label": "Bible",
                    "width": 1000,
                    "height": 1500,
                    "images": [
                        {
                            "@type": "oa:Annotation",
                            "motivation": "sc:painting",
                            "resource": {
                                "@type": "dctypes:Image",
                                "@id": f"{IMAGE_SERVICE}/full/full/0/default.jpg",
                                "format": "image/jpeg",
                                "width": 1000,
                                "height": 1500,
                                "service": {
                                    "@context": "http://iiif.io/api/image/2/context.json",
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
    assert data["id"] == "rit"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["base_url"] == "https://digitalcollections.rit.edu"
    assert data["extra"]["manifest"] == MANIFEST_URL
    assert data["extra"]["collection_id"] == "RIT~1~1~105~3287"
    # no aggregate Collection manifest was found on the host
    assert "collection" not in data["extra"]


@pytest.mark.asyncio
async def test_search_normalizes_v2_manifest():
    http = FakeHttp({MANIFEST_URL: MANIFEST})
    connector = IIIFConnector(_descriptor(), http)

    assets = await connector.search("", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "rit"
    assert asset.title == "Bible"
    assert asset.page_url == MANIFEST_URL
    assert asset.image_url == f"{IMAGE_SERVICE}/full/full/0/default.jpg"
    assert asset.thumbnail_url == f"{IMAGE_SERVICE}/full/512,/0/default.jpg"
    assert asset.iiif_id == IMAGE_SERVICE
    assert asset.year == 1200
    assert asset.license == "varies"


@pytest.mark.asyncio
async def test_search_filters_by_query():
    http = FakeHttp({MANIFEST_URL: MANIFEST})
    connector = IIIFConnector(_descriptor(), http)

    assert await connector.search("nonexistentterm", limit=10) == []
    assert len(await connector.search("bible", limit=10)) == 1
