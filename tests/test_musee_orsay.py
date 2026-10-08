"""Musée d'Orsay IIIF host onboarding: descriptor wiring (offline).

The host (https://iiif.musee-orsay.fr, the "Manifester" / Ephoto DAM IIIF app)
serves one Presentation v3 manifest per object and exposes no aggregate
Collection and no search endpoint, so the descriptor points the generic
`src/mnemosyne/sources/iiif.py` connector at a single manifest via
`extra.manifest` and records the host's own object identifier in
`extra.collection_id`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.iiif import IIIFConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"
DESCRIPTOR = SOURCES_DIR / "musee_orsay.yaml"
MANIFEST = "https://iiif.musee-orsay.fr/Manifester/IIIF/3/objects!701/manifest.json"


class _FakeHttp:
    def __init__(self, routes: dict | None = None):
        self.routes = routes or {}

    async def get_json(self, url, **kwargs):  # pragma: no cover - guard only
        if url in self.routes:
            return self.routes[url]
        raise AssertionError("descriptor test must not perform network I/O")


def _data() -> dict:
    return yaml.safe_load(DESCRIPTOR.read_text(encoding="utf-8"))


def test_musee_orsay_descriptor_is_keyless_iiif():
    data = _data()
    assert data["id"] == "musee_orsay"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["base_url"] == "https://iiif.musee-orsay.fr"
    assert data["license"]
    # single-manifest entry point (no aggregate Collection exists on the host)
    assert data["extra"]["manifest"] == MANIFEST
    assert data["extra"]["collection_id"] == "objects!701"


def test_musee_orsay_uses_generic_iiif_connector():
    data = _data()
    descriptor = SourceDescriptor(
        id=data["id"],
        name=data["name"],
        protocol=Protocol(data["protocol"]),
        base_url=data["base_url"],
        auth=data["auth"],
        extra=data["extra"],
    )
    connector = build_connector(descriptor, _FakeHttp())
    assert isinstance(connector, IIIFConnector)


@pytest.mark.asyncio
async def test_musee_orsay_manifest_normalizes_to_asset():
    """The descriptor's manifest URL feeds the generic connector (mocked v3)."""
    manifest = {
        "id": MANIFEST,
        "type": "Manifest",
        "label": {
            "fr": ["Toulouse-Lautrec, Henri de - Femme au boa noir - INV 20140"]
        },
        "metadata": [
            {
                "label": {"fr": ["Désignation"], "en": ["Title"]},
                "value": {"fr": ["Femme au boa noir"]},
            },
            {
                "label": {"fr": ["Date"], "en": ["Date"]},
                "value": {"fr": ["1892"]},
            },
        ],
        "items": [
            {
                "type": "Canvas",
                "items": [
                    {
                        "type": "AnnotationPage",
                        "items": [
                            {
                                "type": "Annotation",
                                "body": {
                                    "id": "https://iiif.musee-orsay.fr/img/701.jpg",
                                    "type": "Image",
                                    "service": [
                                        {
                                            "id": (
                                                "https://iiif.musee-orsay.fr/"
                                                "iiif/3/objects!701"
                                            ),
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
    data = _data()
    descriptor = SourceDescriptor(
        id=data["id"],
        name=data["name"],
        protocol=Protocol(data["protocol"]),
        base_url=data["base_url"],
        auth=data["auth"],
        extra=data["extra"],
    )
    connector = IIIFConnector(descriptor, _FakeHttp({MANIFEST: manifest}))

    assets = await connector.search("lautrec", limit=5)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "musee_orsay"
    assert "Toulouse-Lautrec" in asset.title
    assert asset.year == 1892
    assert asset.image_url == (
        "https://iiif.musee-orsay.fr/iiif/3/objects!701/full/full/0/default.jpg"
    )
    assert asset.thumbnail_url == (
        "https://iiif.musee-orsay.fr/iiif/3/objects!701/full/512,/0/default.jpg"
    )
