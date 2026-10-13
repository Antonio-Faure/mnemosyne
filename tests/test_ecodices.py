"""e-codices (Virtual Manuscript Library of Switzerland) IIIF source — mocked.

The St. Gallen, Stiftsbibliothek IIIF Collection
(`metadata/iiif/collection/csg.json`) enumerates v2 `sc:Manifest` entries whose
images are served by the IIIF Image API. The generic
`src/mnemosyne/sources/iiif.py` connector handles both the collection traversal
(confirmed via fetch_url) and the v2 manifest normalization, so no bespoke
connector is needed. Rights: CC BY-NC (non-commercial) → descriptor disabled.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.iiif import IIIFConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"
COLLECTION_URL = "https://www.e-codices.unifr.ch/metadata/iiif/collection/csg.json"
MANIFEST_URL = "https://e-codices.ch/metadata/iiif/csg-0857/manifest.json"
SERVICE_URL = "https://www.e-codices.unifr.ch/iiif/csg-0857/1"

# Shape mirrors the live collection response (v2 `sc:Collection`).
COLLECTION = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@id": COLLECTION_URL,
    "@type": "sc:Collection",
    "label": "St. Gallen, Stiftsbibliothek",
    "manifests": [
        {
            "@id": MANIFEST_URL,
            "@type": "sc:Manifest",
            "label": "St. Gallen, Stiftsbibliothek, Cod. Sang. 857",
        },
    ],
}

# Shape mirrors the live csg-0857 manifest (v2 `sc:Manifest`).
MANIFEST = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@id": MANIFEST_URL,
    "@type": "sc:Manifest",
    "label": "St. Gallen, Stiftsbibliothek, Cod. Sang. 857",
    "metadata": [
        {"label": "Shelfmark", "value": "Cod. Sang. 857"},
        {
            "label": "Date of Origin (English)",
            "value": "third quarter of the 13th century, probably around 1260",
        },
    ],
    "sequences": [
        {
            "canvases": [
                {
                    "images": [
                        {
                            "resource": {
                                "@id": SERVICE_URL + "/full/full/0/default.jpg",
                                "service": {"@id": SERVICE_URL},
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
    data = yaml.safe_load((SOURCES_DIR / "ecodices.yaml").read_text(encoding="utf-8"))
    return SourceDescriptor(**data)


def test_descriptor_is_keyless_collection_iiif():
    data = yaml.safe_load((SOURCES_DIR / "ecodices.yaml").read_text(encoding="utf-8"))
    assert data["id"] == "ecodices"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["base_url"] == "https://www.e-codices.unifr.ch"
    assert data["extra"]["collection"] == COLLECTION_URL
    assert data["extra"]["collection_id"]


def test_descriptor_is_disabled_for_noncommercial_license():
    data = yaml.safe_load((SOURCES_DIR / "ecodices.yaml").read_text(encoding="utf-8"))
    assert data["enabled"] is False
    assert "by-nc" in data["license"]


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
    assert asset.source_id == "ecodices"
    assert asset.title == "St. Gallen, Stiftsbibliothek, Cod. Sang. 857"
    assert asset.image_url == SERVICE_URL + "/full/full/0/default.jpg"
    assert asset.thumbnail_url == SERVICE_URL + "/full/512,/0/default.jpg"
    assert asset.license == "https://creativecommons.org/licenses/by-nc/4.0/"
    assert asset.iiif_id == SERVICE_URL


@pytest.mark.asyncio
async def test_search_filters_by_query():
    http = FakeHttp({COLLECTION_URL: COLLECTION, MANIFEST_URL: MANIFEST})
    connector = IIIFConnector(_descriptor(), http)

    assert await connector.search("nonexistentterm", limit=10) == []
    assert len(await connector.search("Stiftsbibliothek", limit=10)) == 1


def test_protocol_enum_has_iiif():
    assert Protocol.IIIF.value == "iiif"
