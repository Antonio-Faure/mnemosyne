"""Harvard Art Museums (iiif.harvardartmuseums.org) IIIF source — mocked.

Harvard Art Museums serve one IIIF Presentation v2 manifest per object at
iiif.harvardartmuseums.org/manifests/object/<id> (sample object 228298). The
host publishes no aggregate IIIF Collection manifest (the root and the common
collection/manifests paths return 404) and the search API
(api.harvardartmuseums.org) is a separate host requiring an apikey, so the
source is onboarded as a single manifest and handled by the generic
`src/mnemosyne/sources/iiif.py` connector (v2
`sequences`/`canvases`/`images`/`resource`). Images are served by the IIIF Image
API on nrs.harvard.edu. Fully offline.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.iiif import IIIFConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"
MANIFEST_URL = "https://iiif.harvardartmuseums.org/manifests/object/228298"
SERVICE_ID = "https://nrs.harvard.edu/urn-3:HUAM:DDC255073"

# Shape mirrors the live Harvard Art Museums manifest (v2 `sc:Manifest`), trimmed.
MANIFEST = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@id": MANIFEST_URL,
    "@type": "sc:Manifest",
    "label": "Portrait of an Apostle (Saint Philip)",
    "metadata": [
        {"label": "Date", "value": "16th-17th century"},
        {"label": "Classification", "value": "Paintings"},
        {
            "label": "Credit Line",
            "value": "Harvard Art Museums/Fogg Museum, Bequest of Edwin H. Abbot",
        },
        {"label": "Object Number", "value": "1966.31"},
        {
            "label": "People",
            "value": [
                "Artist: Attributed to Domenico Theotocopoli, called El Greco, "
                "Spanish, 1541 - 1614"
            ],
        },
        {"label": "Medium", "value": "Oil on canvas"},
    ],
    "sequences": [
        {
            "canvases": [
                {
                    "images": [
                        {
                            "resource": {
                                "@id": f"{SERVICE_ID}/full/full/0/default.jpg",
                                "service": {
                                    "@id": SERVICE_ID,
                                    "profile": "http://iiif.io/api/image/2/level2.json",
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
    data = yaml.safe_load(
        (SOURCES_DIR / "harvard_art_museums.yaml").read_text(encoding="utf-8")
    )
    return SourceDescriptor(**data)


def test_descriptor_is_keyless_single_manifest_iiif():
    data = yaml.safe_load(
        (SOURCES_DIR / "harvard_art_museums.yaml").read_text(encoding="utf-8")
    )
    assert data["id"] == "harvard_art_museums"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["base_url"] == "https://iiif.harvardartmuseums.org"
    assert data["extra"]["manifest"] == MANIFEST_URL
    assert data["extra"]["collection_id"] == "228298"


def test_descriptor_uses_generic_iiif_connector():
    connector = build_connector(_descriptor(), FakeHttp({}))
    assert isinstance(connector, IIIFConnector)


@pytest.mark.asyncio
async def test_search_normalizes_v2_manifest():
    http = FakeHttp({MANIFEST_URL: MANIFEST})
    connector = IIIFConnector(_descriptor(), http)

    assets = await connector.search("", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "harvard_art_museums"
    assert asset.title == "Portrait of an Apostle (Saint Philip)"
    assert asset.date_text == "16th-17th century"
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
    assert len(await connector.search("apostle", limit=10)) == 1


def test_protocol_enum_has_iiif():
    assert Protocol.IIIF.value == "iiif"
