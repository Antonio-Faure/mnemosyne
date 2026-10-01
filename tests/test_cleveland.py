"""Offline tests for the Cleveland Museum of Art Open Access connector."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mnemosyne.models import SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.cleveland import ClevelandConnector

DESCRIPTOR = Path(__file__).resolve().parents[1] / "config" / "sources" / "cleveland.yaml"

_SAMPLE: dict[str, Any] = {
    "data": [
        {
            "id": 148401,
            "accession_number": "1994.174",
            "title": "Maîtres de l'Affiche",
            "creation_date": "1896",
            "technique": "color lithograph",
            "creators": [{"description": "Jules Chéret (French, 1836-1932)"}],
            "copyright": None,
            "url": "https://www.clevelandart.org/art/1994.174",
            "images": {
                "web": {
                    "url": "https://openaccess-cdn.clevelandart.org/1994.174/1994.174_web.jpg"
                }
            },
        }
    ]
}


class _FakeHttp:
    """Captures calls and returns a canned payload; never touches the network."""

    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        return self._payload


def _raw() -> dict[str, Any]:
    return yaml.safe_load(DESCRIPTOR.read_text(encoding="utf-8"))


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(**_raw())


def test_cleveland_descriptor_is_keyless_rest():
    raw = _raw()
    assert raw["id"] == "cleveland"
    assert raw["protocol"] == "rest"
    assert raw["auth"] == "none"
    assert "openaccess-api.clevelandart.org" in raw["base_url"]


def test_cleveland_uses_registered_connector():
    assert isinstance(build_connector(_descriptor(), _FakeHttp({})), ClevelandConnector)


@pytest.mark.asyncio
async def test_cleveland_search_normalizes_assets():
    http = _FakeHttp(_SAMPLE)
    connector = ClevelandConnector(_descriptor(), http)

    assets = await connector.search("affiche", limit=5)

    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "cleveland"
    assert asset.source_asset_id == "148401"
    assert asset.title == "Maîtres de l'Affiche"
    assert asset.creator == "Jules Chéret (French, 1836-1932)"
    assert asset.year == 1896
    assert asset.license == "CC0-1.0"
    assert asset.page_url == "https://www.clevelandart.org/art/1994.174"
    assert asset.image_url.endswith("1994.174_web.jpg")
    assert asset.extra["cleveland_id"] == 148401
    # offline: only the fake client was used
    assert http.calls
