"""Paris Musées (apicollections.parismusees.paris.fr) IIIF source — mocked.

The Paris Musées collections (musées de la Ville de Paris) serve one IIIF
Presentation v2 manifest per notice at
apicollections.parismusees.paris.fr/iiif/<id>/manifest. No IIIF Collection is
published and the search API (GraphQL /graphql) requires a token, so the source
is onboarded as a single manifest and handled by the generic
`src/mnemosyne/sources/iiif.py` connector (v2
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
MANIFEST_URL = "https://apicollections.parismusees.paris.fr/iiif/320025034/manifest"

# Shape mirrors the live Paris Musées manifest (v2 `sc:Manifest`), trimmed.
MANIFEST = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@type": "sc:Manifest",
    "label": "Portrait de jeune femme",
    "metadata": [
        {"label": "Titre", "value": "Portrait de jeune femme"},
        {"label": "Auteur", "value": "Anonyme"},
        {"label": "Datation", "value": "19e siècle"},
        {"label": "description", "value": "<p>Huile sur toile encadrée.</p>\n"},
    ],
    "sequences": [
        {
            "canvases": [
                {
                    "images": [
                        {
                            "resource": {
                                "@id": "https://apicollections.parismusees.paris.fr/"
                                "iiif/320025034/full/full/0/default.jpg",
                                "service": {
                                    "@id": "https://apicollections.parismusees.paris.fr/"
                                    "iiif/320025034",
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
    data = yaml.safe_load((SOURCES_DIR / "paris_musees.yaml").read_text(encoding="utf-8"))
    return SourceDescriptor(**data)


def test_descriptor_is_keyless_single_manifest_iiif():
    data = yaml.safe_load((SOURCES_DIR / "paris_musees.yaml").read_text(encoding="utf-8"))
    assert data["id"] == "paris_musees"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["base_url"] == "https://apicollections.parismusees.paris.fr"
    assert data["extra"]["manifest"] == MANIFEST_URL
    assert data["extra"]["collection_id"] == "320025034"


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
    assert asset.source_id == "paris_musees"
    assert asset.title == "Portrait de jeune femme"
    assert asset.description == "<p>Huile sur toile encadrée.</p>"
    assert asset.date_text == "19e siècle"
    # No `rights`/`license` in the manifest -> the descriptor licence is carried.
    assert asset.license == "varies"
    assert asset.iiif_id == "https://apicollections.parismusees.paris.fr/iiif/320025034"
    assert asset.image_url == (
        "https://apicollections.parismusees.paris.fr/iiif/320025034/full/full/0/default.jpg"
    )
    assert asset.thumbnail_url == (
        "https://apicollections.parismusees.paris.fr/iiif/320025034/full/512,/0/default.jpg"
    )


@pytest.mark.asyncio
async def test_search_filters_by_query():
    http = FakeHttp({MANIFEST_URL: MANIFEST})
    connector = IIIFConnector(_descriptor(), http)

    assert await connector.search("nonexistentterm", limit=10) == []
    assert len(await connector.search("portrait", limit=10)) == 1


def test_protocol_enum_has_iiif():
    assert Protocol.IIIF.value == "iiif"
