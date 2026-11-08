"""Musée français du Pétrole (Pechelbronn) WordPress-media connector — mocked, offline.

The shapes below mirror the museum's open, keyless ``wp-json/wp/v2/media`` JSON:
``mime_type`` is **not** filtered server-side, metadata is thin (titles derived
from file names, empty ``caption``/``alt_text``, no photographer, no original
date — the REST ``date`` is only the CMS upload timestamp), and licence is "all
rights reserved".

The descriptor is deliberately kept ``enabled: false``: there is no reusable
licence and the museum is closed (see ``docs/musee-petrole-pechelbronn.md``).
These tests never touch the network and assert that the connector normalizes the
provider shape correctly *and* never promotes the CMS upload date to
``Asset.year`` (which would mis-date a historical photograph as modern).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.musee_petrole_pechelbronn import MuseePetrolePechelbronnConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"
BASE = "https://www.musee-du-petrole.com/wp-json/wp/v2"
MEDIA_URL = f"{BASE}/media"


class FakeHttp:
    """Serves canned media pages; records calls; forbids any other traffic."""

    def __init__(self, pages: dict | None = None):
        self.pages = pages or {}
        self.get_json_calls: list[str] = []
        self.last_params: dict | None = None

    async def get_json(self, url: str, **kwargs):
        self.get_json_calls.append(url)
        self.last_params = kwargs.get("params")
        if url not in self.pages:
            raise AssertionError(f"unexpected request: {url}")
        return self.pages[url]


def _descriptor(**overrides) -> SourceDescriptor:
    base = {
        "id": "musee_petrole_pechelbronn",
        "name": "Musée français du Pétrole — Merkwiller-Pechelbronn (photothèque)",
        "institution": "Association des Amis du Musée du Pétrole",
        "country": "FR",
        "protocol": Protocol.REST,
        "base_url": BASE,
        "auth": "none",
        "license": "all-rights-reserved",
        "rights": "© Musée français du Pétrole",
        "seeds": ["pechelbronn"],
        "enabled": False,
        "extra": {},
    }
    base.update(overrides)
    return SourceDescriptor(**base)


def _media_item(
    media_id: int = 1436,
    *,
    mime: str = "image/jpeg",
    media_type: str = "image",
    title: str = "derrick-1920.jpg",
    caption: str = "",
    alt: str = "",
    date: str = "2020-01-01T10:00:00",
    link: str | None = None,
    sizes: dict | None = None,
    width: int = 1200,
    height: int = 800,
) -> dict:
    size_map = sizes or {
        "medium": {
            "source_url": f"https://www.musee-du-petrole.com/wp-content/uploads/{media_id}-300x200.jpg"
        }
    }
    return {
        "id": media_id,
        "date": date,
        "link": link
        if link is not None
        else f"https://www.musee-du-petrole.com/?attachment_id={media_id}",
        "title": {"rendered": title},
        "caption": {"rendered": caption},
        "alt_text": alt,
        "media_type": media_type,
        "mime_type": mime,
        "source_url": f"https://www.musee-du-petrole.com/wp-content/uploads/{media_id}.jpg",
        "media_details": {"width": width, "height": height, "sizes": size_map},
        "post": 12,
        "image_meta": {},
    }


# -- registry / descriptor ------------------------------------------------


def test_build_connector_returns_musee_petrole() -> None:
    connector = build_connector(_descriptor(), FakeHttp())
    assert isinstance(connector, MuseePetrolePechelbronnConnector)


def test_real_descriptor_is_disabled_and_rights_reserved() -> None:
    raw = yaml.safe_load(
        (SOURCES_DIR / "musee_petrole_pechelbronn.yaml").read_text(encoding="utf-8")
    )
    assert raw["id"] == "musee_petrole_pechelbronn"
    assert raw["protocol"] == "rest"
    # "all rights reserved" ⇒ must stay off until a written reusable licence lands
    assert raw.get("enabled", True) is False
    assert raw["license"] == "all-rights-reserved"
    assert isinstance(
        build_connector(SourceDescriptor(**raw), FakeHttp()),
        MuseePetrolePechelbronnConnector,
    )


# -- normalization --------------------------------------------------------


@pytest.mark.asyncio
async def test_image_item_is_normalized_to_asset() -> None:
    http = FakeHttp({MEDIA_URL: [_media_item()]})
    connector = MuseePetrolePechelbronnConnector(_descriptor(), http)

    assets = await connector.search("pechelbronn", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "musee_petrole_pechelbronn"
    assert asset.source_asset_id == "1436"
    assert asset.title == "derrick-1920.jpg"
    # licence / rights from the descriptor flow through to the asset boundary
    assert asset.license == "all-rights-reserved"
    assert asset.rights == "© Musée français du Pétrole"
    assert asset.image_url == (
        "https://www.musee-du-petrole.com/wp-content/uploads/1436.jpg"
    )
    assert asset.thumbnail_url.endswith("1436-300x200.jpg")
    assert asset.width == 1200 and asset.height == 800
    assert asset.page_url == "https://www.musee-du-petrole.com/?attachment_id=1436"
    # The CMS upload date must NOT become the historical year.
    assert asset.year is None
    assert asset.date_text is None
    assert asset.creator is None
    assert asset.extra["wp_upload_date"] == "2020-01-01T10:00:00"
    assert asset.extra["mime_type"] == "image/jpeg"
    assert asset.extra["wp_media_id"] == 1436


@pytest.mark.asyncio
async def test_non_image_items_are_dropped_client_side() -> None:
    items = [
        _media_item(1, mime="application/pdf", media_type="file"),
        _media_item(2, mime="video/mp4", media_type="video"),
        _media_item(3),  # the only real image
    ]
    http = FakeHttp({MEDIA_URL: items})
    connector = MuseePetrolePechelbronnConnector(_descriptor(), http)

    assets = await connector.search("derrick", limit=10)
    assert [a.source_asset_id for a in assets] == ["3"]


@pytest.mark.asyncio
async def test_missing_source_url_is_dropped() -> None:
    item = _media_item(9)
    item["source_url"] = ""
    http = FakeHttp({MEDIA_URL: [item]})
    connector = MuseePetrolePechelbronnConnector(_descriptor(), http)

    assert await connector.search("puits", limit=10) == []


@pytest.mark.asyncio
async def test_per_page_is_capped_at_100() -> None:
    http = FakeHttp({MEDIA_URL: []})
    connector = MuseePetrolePechelbronnConnector(_descriptor(), http)

    await connector.search("puits", limit=500)
    assert http.get_json_calls == [MEDIA_URL]
    assert http.last_params is not None
    assert http.last_params["per_page"] == "100"


@pytest.mark.asyncio
async def test_caption_preferred_over_alt_and_html_is_stripped() -> None:
    item = _media_item(
        caption="<p>Puits de <b>Pechelbronn</b></p>", alt="alt text"
    )
    http = FakeHttp({MEDIA_URL: [item]})
    connector = MuseePetrolePechelbronnConnector(_descriptor(), http)

    assets = await connector.search("", limit=5)
    assert assets[0].description == "Puits de Pechelbronn"


@pytest.mark.asyncio
async def test_empty_title_falls_back_to_media_id() -> None:
    item = _media_item(4285, title="")
    http = FakeHttp({MEDIA_URL: [item]})
    connector = MuseePetrolePechelbronnConnector(_descriptor(), http)

    assets = await connector.search("", limit=5)
    assert assets[0].title == "4285"


@pytest.mark.asyncio
async def test_non_list_payload_returns_no_assets() -> None:
    http = FakeHttp({MEDIA_URL: {"unexpected": "object"}})
    connector = MuseePetrolePechelbronnConnector(_descriptor(), http)

    assert await connector.search("", limit=5) == []
