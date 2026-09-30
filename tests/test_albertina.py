from pathlib import Path

import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.iiif import IIIFConnector

DESCRIPTOR = Path(__file__).resolve().parents[1] / "config" / "sources" / "albertina.yaml"


class _FakeHttp:
    async def get_json(self, url, **kwargs):  # pragma: no cover - guard only
        raise AssertionError("descriptor test must not perform network I/O")


def _data() -> dict:
    return yaml.safe_load(DESCRIPTOR.read_text(encoding="utf-8"))


def test_albertina_descriptor_is_keyless_iiif():
    data = _data()
    assert data["id"] == "albertina"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    # a IIIF entry point must be present
    assert "manifest" in data["extra"] or "collection" in data["extra"]


def test_albertina_uses_generic_iiif_connector():
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
