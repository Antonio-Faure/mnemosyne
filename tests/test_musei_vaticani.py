from pathlib import Path

import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.iiif import IIIFConnector

DESCRIPTOR = Path(__file__).resolve().parents[1] / "config" / "sources" / "musei_vaticani.yaml"


class _FakeHttp:
    async def get_json(self, url, **kwargs):  # pragma: no cover - guard only
        raise AssertionError("descriptor test must not perform network I/O")


def _data() -> dict:
    return yaml.safe_load(DESCRIPTOR.read_text(encoding="utf-8"))


def test_musei_vaticani_descriptor_is_keyless_iiif():
    data = _data()
    assert data["id"] == "musei_vaticani"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["base_url"] == "https://catalogo.museivaticani.va"
    # a IIIF entry point must be present
    assert "manifest" in data["extra"] or "collection" in data["extra"]


def test_musei_vaticani_uses_generic_iiif_connector():
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


def test_musei_vaticani_manifest_normalizes_to_asset():
    import asyncio

    from mnemosyne.sources.iiif import IIIFConnector

    data = _data()
    manifest_url = data["extra"]["manifest"]

    manifest = {
        "@context": "http://iiif.io/api/presentation/2/context.json",
        "@id": manifest_url,
        "@type": "sc:Manifest",
        "label": "Gruppo di Mitra tauroctono, con testa non pertinente",
        "description": "Gruppo di Mitra tauroctono, con testa non pertinente",
        "metadata": [
            {"label": "Coverage", "value": ["seconda metà II sec. d.C."]},
            {"label": "Identifier", "value": ["MV.437.0.0"]},
        ],
        "sequences": [
            {
                "canvases": [
                    {
                        "images": [
                            {
                                "resource": {
                                    "@id": "https://catalogo.museivaticani.va/service.php/IIIF/3326",
                                    "@type": "dctypes:Image",
                                    "service": {
                                        "@id": (
                                            "https://catalogo.museivaticani.va"
                                            "/service.php/IIIF/3326"
                                        ),
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

    class _Http:
        async def get_json(self, url, **kwargs):
            assert url == manifest_url
            return manifest

    descriptor = SourceDescriptor(
        id=data["id"],
        name=data["name"],
        protocol=Protocol(data["protocol"]),
        base_url=data["base_url"],
        auth=data["auth"],
        extra=data["extra"],
    )
    connector = IIIFConnector(descriptor, _Http())
    assets = asyncio.run(connector.search("mitra", limit=5))
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "musei_vaticani"
    assert "Mitra" in asset.title
    assert asset.image_url == (
        "https://catalogo.museivaticani.va/service.php/IIIF/3326/full/full/0/default.jpg"
    )
    assert asset.iiif_id == "https://catalogo.museivaticani.va/service.php/IIIF/3326"
