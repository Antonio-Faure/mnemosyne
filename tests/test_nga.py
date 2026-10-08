from pathlib import Path

import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.iiif import IIIFConnector

DESCRIPTOR = Path(__file__).resolve().parents[1] / "config" / "sources" / "nga.yaml"

MANIFEST = "https://www.nga.gov/api/v1/iiif/presentation/manifest.json?cultObj:id=395"


class _FakeHttp:
    async def get_json(self, url, **kwargs):  # pragma: no cover - guard only
        raise AssertionError("descriptor test must not perform network I/O")


def _data() -> dict:
    return yaml.safe_load(DESCRIPTOR.read_text(encoding="utf-8"))


def test_nga_descriptor_is_keyless_iiif():
    data = _data()
    assert data["id"] == "nga"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["license"]
    # a IIIF entry point must be present (single manifest: no aggregate Collection)
    assert data["extra"]["manifest"] == MANIFEST
    # a stable object identifier is recorded for provenance
    assert data["extra"]["collection_id"]


def test_nga_uses_generic_iiif_connector():
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
