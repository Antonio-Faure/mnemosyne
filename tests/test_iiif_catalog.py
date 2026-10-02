"""IIIF collections onboarded to the catalog: descriptor wiring (offline).

These sources are *single-manifest* IIIF hosts (one object per URL), so each
descriptor points the generic `src/mnemosyne/sources/iiif.py` connector at its
manifest via `extra.manifest` and records the provider's own stable collection /
object identifier in `extra.collection_id`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.iiif import IIIFConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"

#: descriptor id -> canonical IIIF manifest URL (the 10 verified collections)
IIIF_SOURCES = {
    "artic": "https://api.artic.edu/api/v1/artworks/28560/manifest.json",
    "rijksmuseum": (
        "https://iiif.europeana.eu/presentation/90402/SK_A_3262/manifest"
    ),
    "vatican": "https://digi.vatlib.it/iiif/MSS_Barb.gr.252/manifest.json",
    "wellcome": "https://iiif.wellcomecollection.org/presentation/b18035723",
    "yale": "https://collections.library.yale.edu/manifests/2002046",
    "bsb": (
        "https://api.digitale-sammlungen.de/iiif/presentation/v2/"
        "bsb00083127/manifest"
    ),
    "cudl": "https://cudl.lib.cam.ac.uk/iiif/MS-ADD-03996",
    "ecodices": (
        "https://www.e-codices.unifr.ch/metadata/iiif/"
        "csg-0657/manifest.json"
    ),
    "vam": "https://iiif.vam.ac.uk/collections/O117445/manifest.json",
    "archive_org": (
        "https://iiif.archive.org/iiif/3/proceedings1922mcle/manifest.json"
    ),
}


class _FakeHttp:
    async def get_json(self, url, **kwargs):  # pragma: no cover - guard only
        raise AssertionError("descriptor test must not perform network I/O")


def _load(source_id: str) -> dict:
    path = SOURCES_DIR / f"{source_id}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("source_id,manifest_url", sorted(IIIF_SOURCES.items()))
def test_descriptor_is_keyless_iiif(source_id: str, manifest_url: str) -> None:
    data = _load(source_id)
    assert data["id"] == source_id
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["license"]
    assert data["extra"]["manifest"] == manifest_url
    # a stable collection / object identifier is recorded for provenance
    assert data["extra"]["collection_id"]


@pytest.mark.parametrize("source_id", sorted(IIIF_SOURCES))
def test_descriptor_uses_generic_iiif_connector(source_id: str) -> None:
    descriptor = SourceDescriptor(**_load(source_id))
    connector = build_connector(descriptor, _FakeHttp())
    assert isinstance(connector, IIIFConnector)
