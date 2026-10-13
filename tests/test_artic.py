"""Art Institute of Chicago (AIC) IIIF source — mocked end-to-end.

The host exposes *per-object* IIIF Presentation v2 manifests through its public,
keyless API at `api/v1/artworks/<id>/manifest.json` (images are served by the
IIIF Image API at `www.artic.edu/iiif/2/<uuid>`). It also has a keyless REST
search endpoint (`api/v1/artworks/search?q=…`) that returns artwork ids, but no
aggregate IIIF Collection manifest exists: probes for
`artworks/collection/manifest.json` and `artworks/manifest.json` return 400 and
`api/v1/collection/manifest.json` returns 404. Since the generic
`src/mnemosyne/sources/iiif.py` connector consumes a manifest (not a REST
search), the descriptor points it at a single manifest via `extra.manifest`.
No bespoke connector is needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.iiif import IIIFConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"
DESCRIPTOR = SOURCES_DIR / "artic.yaml"

MANIFEST_URL = "https://api.artic.edu/api/v1/artworks/28560/manifest.json"
IMAGE_SERVICE = "https://www.artic.edu/iiif/2/6644829f-f292-c5c4-a73c-0356a6fdbf0d"

# Shape mirrors the live manifest (v2 `sc:Manifest`) for object 28560
# ("The Bedroom", Vincent van Gogh, 1889), served by api.artic.edu.
MANIFEST = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@id": MANIFEST_URL,
    "@type": "sc:Manifest",
    "label": "The Bedroom",
    "description": [
        {
            "value": (
                "Perhaps the most famous depiction of a bedroom in Western art "
                "history, this vibrant painting documents Vincent van Gogh's "
                "sleeping quarters in his beloved \u201cYellow House\u201d in "
                "Arles, France."
            ),
            "language": "en",
        }
    ],
    "metadata": [
        {"label": "Artist / Maker", "value": "Vincent van Gogh (Dutch, 1853\u20131890)"},
        {"label": "Medium", "value": "Oil on canvas"},
        {"label": "Object Number", "value": "1926.417"},
    ],
    "attribution": "Digital image courtesy of the Art Institute of Chicago.",
    "within": "https://www.artic.edu/collection",
    "sequences": [
        {
            "@type": "sc:Sequence",
            "canvases": [
                {
                    "@type": "sc:Canvas",
                    "@id": IMAGE_SERVICE,
                    "label": "The Bedroom, 1889. Vincent van Gogh (Dutch, 1853\u20131890)",
                    "width": 843,
                    "height": 660,
                    "images": [
                        {
                            "@type": "oa:Annotation",
                            "motivation": "sc:painting",
                            "resource": {
                                "@type": "dctypes:Image",
                                "@id": f"{IMAGE_SERVICE}/full/843,/0/default.jpg",
                                "format": "image/jpeg",
                                "width": 843,
                                "height": 660,
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
    assert data["id"] == "artic"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["base_url"] == "https://api.artic.edu"
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
    assert asset.source_id == "artic"
    assert asset.title == "The Bedroom"
    assert asset.page_url == MANIFEST_URL
    assert asset.image_url == f"{IMAGE_SERVICE}/full/full/0/default.jpg"
    assert asset.thumbnail_url == f"{IMAGE_SERVICE}/full/512,/0/default.jpg"
    assert asset.iiif_id == IMAGE_SERVICE
    assert asset.license == "Public Domain (CC0-1.0)"


@pytest.mark.asyncio
async def test_search_filters_by_query():
    http = FakeHttp({MANIFEST_URL: MANIFEST})
    connector = IIIFConnector(_descriptor(), http)

    assert await connector.search("nonexistentterm", limit=10) == []
    assert len(await connector.search("bedroom", limit=10)) == 1
