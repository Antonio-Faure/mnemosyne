"""Musée français du Pétrole connector: wp-json media normalization (no network)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.musee_petrole_pechelbronn import (
    MuseePetrolePechelbronnConnector,
)

SAMPLE: list[dict[str, Any]] = [
    {
        "id": 1436,
        "date": "2026-03-15T10:00:00",
        "link": "https://www.musee-du-petrole.com/animations/05pechelbronn-cherot/#main",
        "title": {"rendered": "05pechelbronn-cherot"},
        "caption": {"rendered": ""},
        "alt_text": "",
        "media_type": "image",
        "mime_type": "image/jpeg",
        "source_url": (
            "https://www.musee-du-petrole.com/wp-content/uploads/"
            "2026/03/05pechelbronn-cherot.jpg"
        ),
        "media_details": {
            "width": 1323,
            "height": 880,
            "sizes": {
                "medium": {
                    "source_url": (
                        "https://www.musee-du-petrole.com/wp-content/uploads/"
                        "2026/03/05pechelbronn-cherot-300x200.jpg"
                    )
                }
            },
        },
        "post": 15,
    },
    {
        "id": 4285,
        "date": "2016-07-01T09:00:00",
        "link": "https://www.musee-du-petrole.com/?p=2067",
        "title": {"rendered": "Carreau-de-Mine-Clemenceau_Puits-1 &amp; co"},
        "caption": {"rendered": "<strong>Puits</strong>  années 1920"},
        "alt_text": "",
        "media_type": "image",
        "mime_type": "image/jpeg",
        "source_url": (
            "https://www.musee-du-petrole.com/wp-content/uploads/2016/07/puits1.jpg"
        ),
        "media_details": {"width": 2560, "height": 1932, "sizes": {}},
        "post": 2067,
    },
    {
        # non-image attachment: must be dropped on the client side
        "id": 9000,
        "title": {"rendered": "plan.pdf"},
        "caption": {"rendered": ""},
        "alt_text": "",
        "media_type": "file",
        "mime_type": "application/pdf",
        "source_url": (
            "https://www.musee-du-petrole.com/wp-content/uploads/plan.pdf"
        ),
        "media_details": {},
    },
    {
        # image without a source_url: dropped
        "id": 9001,
        "title": {"rendered": "orpheline"},
        "caption": {"rendered": ""},
        "alt_text": "",
        "media_type": "image",
        "mime_type": "image/png",
        "source_url": "",
        "media_details": {},
    },
]


class FakeHttp:
    """Records calls and returns a canned wp-json media payload."""

    def __init__(self, payload: Any):
        self.payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        return self.payload


def _descriptor(**overrides: Any) -> SourceDescriptor:
    base: dict[str, Any] = {
        "id": "musee_petrole_pechelbronn",
        "name": "Musée français du Pétrole — Merkwiller-Pechelbronn",
        "protocol": Protocol.REST,
        "base_url": "https://www.musee-du-petrole.com/wp-json/wp/v2",
        "auth": "none",
        "license": "all-rights-reserved",
        "rights": "© Musée français du Pétrole",
        "enabled": False,
    }
    base.update(overrides)
    return SourceDescriptor(**base)


async def test_search_normalizes_media_images():
    http = FakeHttp(SAMPLE)
    connector = MuseePetrolePechelbronnConnector(_descriptor(), http)

    assets = await connector.search("cherot", limit=10)

    # the PDF (media_type "file") and the image missing source_url are dropped
    assert [a.source_asset_id for a in assets] == ["1436", "4285"]

    first = assets[0]
    assert first.source_id == "musee_petrole_pechelbronn"
    assert first.title == "05pechelbronn-cherot"
    assert first.license == "all-rights-reserved"
    assert first.rights == "© Musée français du Pétrole"
    assert first.page_url == (
        "https://www.musee-du-petrole.com/animations/05pechelbronn-cherot/#main"
    )
    assert first.image_url.endswith("05pechelbronn-cherot.jpg")
    assert first.thumbnail_url.endswith("05pechelbronn-cherot-300x200.jpg")
    assert first.width == 1323 and first.height == 880
    assert first.year is None  # CMS upload date is never promoted to a year
    assert first.extra["wp_media_id"] == 1436
    assert first.extra["mime_type"] == "image/jpeg"
    assert first.extra["wp_upload_date"] == "2026-03-15T10:00:00"

    second = assets[1]
    # HTML tags stripped and entities unescaped in title/caption
    assert second.title == "Carreau-de-Mine-Clemenceau_Puits-1 & co"
    assert second.description == "Puits années 1920"
    # no medium size -> thumbnail falls back to the full source_url
    assert second.thumbnail_url == second.image_url


async def test_search_queries_the_media_endpoint_with_params():
    http = FakeHttp([])
    connector = MuseePetrolePechelbronnConnector(_descriptor(), http)

    assert await connector.search("derrick", limit=5) == []

    url, kwargs = http.calls[0]
    assert url == "https://www.musee-du-petrole.com/wp-json/wp/v2/media"
    params = kwargs["params"]
    assert params["search"] == "derrick"
    assert params["per_page"] == "5"
    assert params["page"] == "1"
    assert "media_details" in params["_fields"]


async def test_search_clamps_per_page_to_100():
    http = FakeHttp([])
    connector = MuseePetrolePechelbronnConnector(_descriptor(), http)
    await connector.search("puits", limit=500)
    _, kwargs = http.calls[0]
    assert kwargs["params"]["per_page"] == "100"


async def test_non_list_response_returns_empty():
    http = FakeHttp({"unexpected": "shape"})
    connector = MuseePetrolePechelbronnConnector(_descriptor(), http)
    assert await connector.search("x") == []


def test_descriptor_is_disabled_pending_authorization():
    """Restrictive licence: the source stays off until written authorization."""
    path = (
        Path(__file__).resolve().parents[1]
        / "config"
        / "sources"
        / "musee_petrole_pechelbronn.yaml"
    )
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert raw["id"] == "musee_petrole_pechelbronn"
    assert raw["protocol"] == "rest"
    assert raw["enabled"] is False
    assert raw["license"] == "all-rights-reserved"
    assert raw["base_url"].endswith("/wp-json/wp/v2")
    # the authorization request is on file (relayed by the browser agent)
    request = raw["extra"]["authorization_request"]
    assert request["sent"] and request["to"] and request["status"] == "pending"
