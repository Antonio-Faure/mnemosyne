"""Hammer Museum (UCLA) — single-manifest IIIF onboarding (offline).

The host serves one IIIF Presentation v3 manifest per object and exposes no
aggregate Collection manifest, so the descriptor points the generic
`src/mnemosyne/sources/iiif.py` connector at a single manifest via
`extra.manifest`. Everything here is offline: the connector is fed a fake HTTP
client returning the real (trimmed) manifest shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.iiif import IIIFConnector

DESCRIPTOR = Path(__file__).resolve().parents[1] / "config" / "sources" / "hammer.yaml"

MANIFEST = "https://collections.hammer.ucla.edu/api/iiif/presentation/v3/AH.90.17.json"


class _NoNetwork:
    async def get_json(self, url, **kwargs):  # pragma: no cover - guard only
        raise AssertionError("descriptor test must not perform network I/O")


def _data() -> dict:
    return yaml.safe_load(DESCRIPTOR.read_text(encoding="utf-8"))


def test_hammer_descriptor_is_keyless_iiif():
    data = _data()
    assert data["id"] == "hammer"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["license"]
    # a single-manifest IIIF entry point (no aggregate Collection manifest)
    assert data["extra"]["manifest"] == MANIFEST
    # a stable object identifier is recorded for provenance
    assert data["extra"]["collection_id"] == "AH.90.17"


def test_hammer_uses_generic_iiif_connector():
    descriptor = SourceDescriptor(**_data())
    connector = build_connector(descriptor, _NoNetwork())
    assert isinstance(connector, IIIFConnector)


# --- normalization of the real Hammer v3 manifest -----------------------------

HAMMER_MANIFEST = {
    "@context": "http://iiif.io/api/presentation/3/context.json",
    "type": "Manifest",
    "id": MANIFEST,
    "rights": "http://creativecommons.org/publicdomain/zero/1.0/",
    "label": {"en": ["Distant View of Mantes Cathedral"]},
    "provider": [
        {
            "id": "https://collections.hammer.ucla.edu",
            "type": "Agent",
            "label": {"en": ["Hammer Museum"]},
        }
    ],
    "metadata": [
        {"label": {"en": ["Accession number"]}, "value": {"en": ["AH.90.17"]}},
        {"label": {"en": ["Artist"]}, "value": {"en": ["Jean-Baptiste-Camille Corot"]}},
        {"label": {"en": ["Date"]}, "value": {"en": ["1859-1860"]}},
    ],
    "items": [
        {
            "id": "https://hammer-online-collection-images.cogapp.cloud/iiif/3/"
            "AH.90.17-159247.ptif/canvas/p1",
            "type": "Canvas",
            "items": [
                {
                    "type": "AnnotationPage",
                    "items": [
                        {
                            "type": "Annotation",
                            "body": {
                                "id": "https://hammer-online-collection-images.cogapp.cloud/"
                                "iiif/3/AH.90.17-159247.ptif/info.json",
                                "type": "Image",
                                "service": [
                                    {
                                        "id": "https://hammer-online-collection-images."
                                        "cogapp.cloud/iiif/3/AH.90.17-159247.ptif",
                                        "type": "ImageService3",
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


class _FakeHttp:
    def __init__(self, routes: dict) -> None:
        self.routes = routes

    async def get_json(self, url, **kwargs):
        return self.routes[url]


@pytest.mark.asyncio
async def test_search_builds_asset_from_real_manifest():
    http = _FakeHttp({MANIFEST: HAMMER_MANIFEST})
    connector = IIIFConnector(SourceDescriptor(**_data()), http)

    assets = await connector.search("Corot", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "hammer"
    assert asset.title == "Distant View of Mantes Cathedral"
    assert asset.creator == "Jean-Baptiste-Camille Corot"
    assert asset.year == 1859
    assert asset.image_url == (
        "https://hammer-online-collection-images.cogapp.cloud/iiif/3/"
        "AH.90.17-159247.ptif/full/full/0/default.jpg"
    )
    assert asset.license == "http://creativecommons.org/publicdomain/zero/1.0/"


@pytest.mark.asyncio
async def test_search_filters_out_non_matching_query():
    http = _FakeHttp({MANIFEST: HAMMER_MANIFEST})
    connector = IIIFConnector(SourceDescriptor(**_data()), http)
    assert await connector.search("zzz-not-present", limit=10) == []
