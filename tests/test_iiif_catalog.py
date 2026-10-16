"""IIIF collections onboarded to the catalog: descriptor wiring (offline).

These sources are *single-manifest* IIIF hosts (one object per URL), so each
descriptor points the generic `src/mnemosyne/sources/iiif.py` connector at its
manifest via `extra.manifest` and records the provider's own stable collection /
object identifier in `extra.collection_id`.

Collection-based IIIF hosts (`extra.collection`) are onboarded separately and
covered by their own tests: CUDL by `tests/test_cudl.py` and e-codices by
`tests/test_ecodices.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"

#: descriptor id -> canonical IIIF manifest URL (single-manifest collections)
IIIF_SOURCES = {
    "artic": "https://api.artic.edu/api/v1/artworks/28560/manifest.json",
    "rijksmuseum": (
        "https://iiif.europeana.eu/presentation/90402/SK_A_3262/manifest"
    ),
    "rit": (
        "https://digitalcollections.rit.edu/luna/servlet/iiif/"
        "m/RIT~1~1~105~3287/manifest"
    ),
    "vatican": "https://digi.vatlib.it/iiif/MSS_Barb.gr.252/manifest.json",
    "wellcome": "https://iiif.wellcomecollection.org/presentation/b18035723",
    "yale": "https://collections.library.yale.edu/manifests/2002046",
    "yale_lux": "https://manifests.collections.yale.edu/yuag/obj/108688",
    "bsb": (
        "https://api.digitale-sammlungen.de/iiif/presentation/v2/"
        "bsb00083127/manifest"
    ),
    "vam": "https://iiif.vam.ac.uk/collections/O117445/manifest.json",
    "ndl": "https://dl.ndl.go.jp/api/iiif/1169293/manifest.json",
}


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


def test_restricted_licenses_are_not_enabled():
    """Non-commercial / restrictive sources stay off until the policy allows them."""
    for source_id in (
        "belvedere",
        "cudl",
        "ecodices",
        "irht",
        "mai_saint_etienne",
        "musee_orsay",
        "musei_vaticani",
        "vam",
        "vatican",
        "wellcome",
    ):
        raw = yaml.safe_load((SOURCES_DIR / f"{source_id}.yaml").read_text(encoding="utf-8"))
        assert raw.get("enabled") is False, f"{source_id} must be disabled"
        if raw.get("protocol") == "iiif":
            # an entry point is still recorded, so enabling it is a one-line change
            extra = raw.get("extra", {})
            assert extra.get("manifest") or extra.get("collection")
