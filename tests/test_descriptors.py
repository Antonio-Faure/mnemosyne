"""One parametrized pass over `config/sources/*.yaml`.

Replaces the per-source clones of "the descriptor loads and builds its
connector" (18 copies, see git history): a new descriptor is covered the moment
it lands, and the file name must match the declared id.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import SourceDescriptor
from mnemosyne.sources import CONNECTORS, build_connector
from mnemosyne.sources.iiif import IIIFConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"
DESCRIPTOR_PATHS = sorted(SOURCES_DIR.glob("*.yaml"))


class _FakeHttp:
    async def get_json(self, url, **kwargs):  # pragma: no cover - guard only
        raise AssertionError("descriptor test must not perform network I/O")


def _raw(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@pytest.mark.parametrize("path", DESCRIPTOR_PATHS, ids=lambda p: p.stem)
def test_descriptor_loads_and_matches_its_file_name(path: Path) -> None:
    descriptor = SourceDescriptor(**_raw(path))
    assert descriptor.id == path.stem


@pytest.mark.parametrize("path", DESCRIPTOR_PATHS, ids=lambda p: p.stem)
def test_descriptor_builds_its_connector(path: Path) -> None:
    descriptor = SourceDescriptor(**_raw(path))
    connector = build_connector(descriptor, _FakeHttp())
    expected = CONNECTORS.get(descriptor.id)
    if expected is not None:
        assert isinstance(connector, expected)
    else:
        assert isinstance(connector, IIIFConnector)


@pytest.mark.parametrize("path", DESCRIPTOR_PATHS, ids=lambda p: p.stem)
def test_iiif_entry_points_record_their_collection_id(path: Path) -> None:
    """Single-manifest hosts must carry the provider's stable object id."""
    raw = _raw(path)
    extra = raw.get("extra") or {}
    if raw.get("protocol") != "iiif" or not (extra.get("manifest") or extra.get("collection")):
        return
    assert extra.get("collection_id"), f"{path.stem}: extra.collection_id missing"
