"""Colenda (Penn Libraries) IIIF source — mocked end-to-end.

Colenda (https://colenda.library.upenn.edu) serves IIIF Presentation v2 manifests
per item from the Penn Libraries digital repository. The host exposes no aggregate
IIIF Collection manifest, so the source is a single-manifest entry point handled
by the generic `src/mnemosyne/sources/iiif.py` connector.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.iiif import IIIFConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"
MANIFEST_URL = "https://colenda.library.upenn.edu/items/ark:/81431/p37659w10/manifest"

# Shape mirrors the live Colenda manifest (v2 `sc:Manifest`).
MANIFEST = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@id": "https://digitalrepository.library.upenn.edu/iiif/2/items/"
    "685c77ef-26e2-45ea-8240-27112e773076/manifest",
    "@type": "sc:Manifest",
    "label": "[Holy Land travel manuscript]",
    "attribution": "Provided by the University of Pennsylvania Libraries.",
    "metadata": [
        {"label": "Title", "value": ["[Holy Land travel manuscript]"]},
        {"label": "Date", "value": ["169X"]},
        {"label": "Rights", "value": ["http://rightsstatements.org/vocab/NoC-US/1.0/"]},
    ],
    "thumbnail": {
        "@id": "https://iiif-images.library.upenn.edu/iiif/2/asset-uuid/"
        "full/!600,600/0/default.jpg",
        "service": {
            "@context": "http://iiif.io/api/image/2/context.json",
            "@id": "https://iiif-images.library.upenn.edu/iiif/2/asset-uuid",
        },
    },
    "sequences": [
        {
            "canvases": [
                {
                    "images": [
                        {
                            "resource": {
                                "@id": "https://iiif-images.library.upenn.edu/iiif/2/"
                                "asset-uuid/full/full/0/default.jpg",
                                "service": {
                                    "@id": "https://iiif-images.library.upenn.edu/"
                                    "iiif/2/asset-uuid"
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


def _data() -> dict:
    return yaml.safe_load((SOURCES_DIR / "colenda.yaml").read_text(encoding="utf-8"))


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(**_data())


def test_descriptor_is_keyless_single_manifest_iiif():
    data = _data()
    assert data["id"] == "colenda"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["base_url"] == "https://colenda.library.upenn.edu"
    assert data["extra"]["manifest"] == MANIFEST_URL
    # no aggregate IIIF Collection was found -> single-manifest entry point
    assert "collection" not in data["extra"]


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
    assert asset.source_id == "colenda"
    assert asset.title == "[Holy Land travel manuscript]"
    assert asset.date_text == "169X"
    assert asset.year is None  # "169X" carries no machine-readable year
    assert asset.image_url == (
        "https://iiif-images.library.upenn.edu/iiif/2/asset-uuid/full/full/0/default.jpg"
    )
    assert asset.thumbnail_url == (
        "https://iiif-images.library.upenn.edu/iiif/2/asset-uuid/full/512,/0/default.jpg"
    )
    # Colenda records rights as v2 metadata ("Rights"), not as a top-level IIIF
    # `license`, so the descriptor licence ("varies") is carried on the Asset.
    assert asset.license == "varies"
    assert asset.page_url == MANIFEST["@id"]


@pytest.mark.asyncio
async def test_search_filters_by_query():
    http = FakeHttp({MANIFEST_URL: MANIFEST})
    connector = IIIFConnector(_descriptor(), http)

    assert await connector.search("nonexistentterm", limit=10) == []
    assert len(await connector.search("holy land", limit=10)) == 1
