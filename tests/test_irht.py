"""IRHT — Arca (api.irht.cnrs.fr) IIIF source — mocked end-to-end.

Arca, the IRHT-CNRS digital library, serves one IIIF Presentation v2 manifest
per manuscript at api.irht.cnrs.fr/ark:/63955/<ark>/manifest.json (images are
served by iiif.irht.cnrs.fr via the IIIF Image API). No IIIF Collection is
published, so the source is onboarded as a single manifest and handled by the
generic `src/mnemosyne/sources/iiif.py` connector (v2
`sequences`/`canvases`/`images`/`resource`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.iiif import IIIFConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"
MANIFEST_URL = "https://api.irht.cnrs.fr/ark:/63955/f2rxhh86uyhx/manifest.json"

# Shape mirrors the live Arca manifest (v2 `sc:Manifest`), trimmed.
MANIFEST = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@type": "sc:Manifest",
    "label": "France, Chantilly, fonds principal, 0086 (1178) (intégral)",
    "metadata": [
        {"label": "Cote", "value": "France, Chantilly, fonds principal, 0086 (1178)"},
        {"label": "Auteur, titre, oeuvre", "value": "Heures de la Tour et Taxis"},
        {"label": "Datation", "value": "16e s. (1516-1519)"},
        {"label": "Provider", "value": "Arca – IRHT-CNRS"},
    ],
    "license": "http://creativecommons.org/licenses/by-nc/3.0/deed.fr",
    "attribution": "Bibliothèque et archives du château de Chantilly",
    "within": "https://arca.irht.cnrs.fr/315556101/collection.json",
    "sequences": [
        {
            "canvases": [
                {
                    "images": [
                        {
                            "resource": {
                                "@id": "https://iiif.irht.cnrs.fr/iiif/ark:/63955/"
                                "vkqhxoool7i1/full/full/0/default.jpg",
                                "service": {
                                    "@id": "https://iiif.irht.cnrs.fr/iiif/"
                                    "ark:/63955/vkqhxoool7i1",
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
    data = yaml.safe_load((SOURCES_DIR / "irht.yaml").read_text(encoding="utf-8"))
    return SourceDescriptor(**data)


def test_descriptor_is_keyless_single_manifest_iiif():
    data = yaml.safe_load((SOURCES_DIR / "irht.yaml").read_text(encoding="utf-8"))
    assert data["id"] == "irht"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["base_url"] == "https://api.irht.cnrs.fr"
    assert data["extra"]["manifest"] == MANIFEST_URL
    assert data["extra"]["collection_id"] == "ark:/63955/f2rxhh86uyhx"


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
    assert asset.source_id == "irht"
    assert asset.title == "France, Chantilly, fonds principal, 0086 (1178) (intégral)"
    assert asset.creator is None
    assert asset.date_text == "16e s. (1516-1519)"
    assert asset.year == 1516
    assert asset.iiif_id == "https://iiif.irht.cnrs.fr/iiif/ark:/63955/vkqhxoool7i1"
    assert asset.image_url == (
        "https://iiif.irht.cnrs.fr/iiif/ark:/63955/vkqhxoool7i1/full/full/0/default.jpg"
    )
    assert asset.thumbnail_url == (
        "https://iiif.irht.cnrs.fr/iiif/ark:/63955/vkqhxoool7i1/full/512,/0/default.jpg"
    )
    # v2 `license` (CC BY-NC) is carried on the Asset, not just the descriptor.
    assert asset.license == "http://creativecommons.org/licenses/by-nc/3.0/deed.fr"


@pytest.mark.asyncio
async def test_search_filters_by_query():
    http = FakeHttp({MANIFEST_URL: MANIFEST})
    connector = IIIFConnector(_descriptor(), http)

    assert await connector.search("nonexistentterm", limit=10) == []
    assert len(await connector.search("chantilly", limit=10)) == 1


def test_protocol_enum_has_iiif():
    assert Protocol.IIIF.value == "iiif"
