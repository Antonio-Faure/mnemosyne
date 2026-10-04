"""arthistoricum.net IIIF source — descriptor wiring + manifest normalization.

`iiif.arthistoricum.net` serves IIIF Presentation v2 manifests per object
(/proxy/<collection>/<id>/manifest.json) with no enumerable Collection, so it
is onboarded as a *single-manifest* IIIF source through the generic
`src/mnemosyne/sources/iiif.py` connector. This test is fully offline: the
HTTP layer is faked.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.iiif import IIIFConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"
DESCRIPTOR = SOURCES_DIR / "arthistoricum.yaml"
MANIFEST_URL = (
    "https://iiif.arthistoricum.net/proxy/fotothek/df_ld_0022737/manifest.json"
)
IMAGE_SERVICE = (
    "https://images.iiif.arthistoricum.net/iiif/2/"
    "proxy%2F67%2FDE-2396_81799831_df_ld_0022737.jpg"
)

# Trimmed copy of the live v2 manifest (see the sample URL in the descriptor).
MANIFEST_V2 = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@id": MANIFEST_URL,
    "@type": "sc:Manifest",
    "label": "Menükarte für den 29. September 1884 im \"Königl. Belvedère\"",
    "metadata": [
        {"label": "Urheber", "value": "Richter, Regine"},
        {"label": "Datierung", "value": "2008.01 (Aufnahmedatum)"},
        {
            "label": "Schlagwörter",
            "value": "Fotografie; Vedute; Speisekarte; Menükarte",
        },
    ],
    "sequences": [
        {
            "canvases": [
                {
                    "images": [
                        {
                            "resource": {
                                "@id": f"{IMAGE_SERVICE}/full/full/0/default.jpg",
                                "service": {
                                    "@id": IMAGE_SERVICE,
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


class _FakeHttp:
    def __init__(self, routes):
        self.routes = routes

    async def get_json(self, url, **kwargs):
        return self.routes[url]


def _load() -> dict:
    return yaml.safe_load(DESCRIPTOR.read_text(encoding="utf-8"))


def test_descriptor_is_keyless_iiif() -> None:
    data = _load()
    assert data["id"] == "arthistoricum"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["base_url"] == "https://iiif.arthistoricum.net"
    assert data["license"]
    assert data["extra"]["manifest"] == MANIFEST_URL
    assert data["extra"]["collection_id"] == "df_ld_0022737"


def test_descriptor_uses_generic_iiif_connector() -> None:
    descriptor = SourceDescriptor(**_load())
    connector = build_connector(descriptor, _FakeHttp({}))
    assert isinstance(connector, IIIFConnector)
    assert descriptor.protocol is Protocol.IIIF


@pytest.mark.asyncio
async def test_search_normalizes_manifest_into_asset() -> None:
    descriptor = SourceDescriptor(**_load())
    http = _FakeHttp({MANIFEST_URL: MANIFEST_V2})
    connector = IIIFConnector(descriptor, http)

    assets = await connector.search("Menükarte", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "arthistoricum"
    assert asset.source_asset_id == MANIFEST_URL
    assert asset.title.startswith("Menükarte")
    # first canvas image is served by the IIIF Image API (v2 service)
    assert asset.image_url == f"{IMAGE_SERVICE}/full/full/0/default.jpg"
    assert asset.thumbnail_url == f"{IMAGE_SERVICE}/full/512,/0/default.jpg"
    assert asset.iiif_id == IMAGE_SERVICE
    assert asset.page_url == MANIFEST_URL
    assert asset.extra["manifest"] == MANIFEST_URL


@pytest.mark.asyncio
async def test_search_without_match_returns_nothing() -> None:
    descriptor = SourceDescriptor(**_load())
    http = _FakeHttp({MANIFEST_URL: MANIFEST_V2})
    connector = IIIFConnector(descriptor, http)

    assert await connector.search("zzz absent token", limit=10) == []
