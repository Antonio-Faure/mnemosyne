"""MAI Saint-Étienne connector: descriptor, normalization, images, pagination.

All tests are offline (a fake HTTP client returns canned Hydra envelopes).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import yaml

from mnemosyne.models import SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.mai_saint_etienne import MAISaintEtienneConnector, cloudfront_url

DESCRIPTOR = (
    Path(__file__).resolve().parents[1] / "config" / "sources" / "mai_saint_etienne.yaml"
)

NOTICE: dict[str, Any] = {
    "id": "657c2a8c9dd1ae27485c36a3",
    "nativeId": "2009.1.42",
    "slug": "metier-a-ruban-manufrance",
    "url": (
        "https://collections.musee-art-industrie.saint-etienne.fr/fr/"
        "notices/657c2a8c9dd1ae27485c36a3"
    ),
    "isEnabled": True,
    "isArchived": False,
    "hasImage": True,
    "client": "st-etienne01",
    "profile": "mai04opacweb",
    "noticeCollections": ["rubans", "la-mecanique-de-l-art"],
    "titles": {
        "title": "Métier à ruban Manufrance",
        "subTitle": "Atelier de rubanerie",
        "text": "Métier à tisser les rubans.",
        "native_title": "Métier à ruban Manufrance",
    },
    "mediaFiles": [
        {"type": "image", "name": "vue1", "fileName": "abc123.jpg", "position": 0},
        {"type": "image", "name": "vue2", "fileName": "def456.jpg", "position": 1},
        {"type": "video", "name": "clip", "fileName": "clip.mp4", "position": 2},
    ],
    "zones": [
        {
            "code": "identification",
            "label": "Identification",
            "occurZones": [
                {
                    "fields": [
                        {"code": "NumeroInventaire", "content": "2009.1.42"},
                        {"code": "DesignationDuBien", "content": "Métier à ruban"},
                        {"code": "PersonneChamp", "content": "Manufrance"},
                        {"code": "EpoqueDatation", "content": "vers 1910"},
                        {"code": "Domaine", "content": "Rubanerie"},
                        {"code": "Matiere", "content": "fonte, bois"},
                        {"code": "Technique", "content": "assemblage"},
                        {"code": "Proprietaire", "content": "Musée d'Art et d'Industrie"},
                        {"code": "SujetTheme", "content": "rubanerie"},
                        {"code": "SujetTheme", "content": "Manufrance"},
                        {
                            "code": "DescriptionAnalytique",
                            "content": "Métier à tisser les rubans à lames multiples.",
                        },
                    ]
                }
            ],
        }
    ],
}

ENVELOPE: dict[str, Any] = {
    "hydra:totalItems": 1,
    "hydra:view": {"first": "/api/v2/notices/search?page=1", "next": None},
    "hydra:member": [NOTICE],
}

CF_HOST = "https://d2lkryo36aywim.cloudfront.net"
SEARCH_URL = (
    "https://collections.musee-art-industrie.saint-etienne.fr/api/v2/notices/search"
)


class FakeHttp:
    """Returns canned payloads in order, recording every call."""

    def __init__(self, *payloads: Any):
        self.payloads = list(payloads)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        if self.payloads:
            return self.payloads.pop(0)
        return {"hydra:member": []}


class _GuardedHttp:
    async def get_json(self, url, **kwargs):  # pragma: no cover - guard only
        raise AssertionError("descriptor test must not perform network I/O")


def _raw() -> dict[str, Any]:
    return yaml.safe_load(DESCRIPTOR.read_text(encoding="utf-8"))


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(**_raw())


def _decode_token(url: str) -> dict[str, Any]:
    token = url.rsplit("/", 1)[-1]
    return json.loads(base64.b64decode(token).decode("utf-8"))


# --- (a) parse a search envelope into an item ------------------------------------


async def test_search_parses_envelope_into_asset():
    http = FakeHttp(ENVELOPE)
    connector = MAISaintEtienneConnector(_descriptor(), http)

    assets = await connector.search("ruban", limit=10)

    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "mai_saint_etienne"
    assert asset.source_asset_id == "657c2a8c9dd1ae27485c36a3"
    assert asset.title == "Métier à ruban Manufrance"
    assert asset.creator == "Manufrance"
    assert asset.date_text == "vers 1910"
    assert asset.year == 1910
    assert asset.description == "Métier à tisser les rubans à lames multiples."
    assert asset.page_url.endswith("657c2a8c9dd1ae27485c36a3")
    assert asset.license == _raw()["license"]

    assert asset.extra["native_id"] == "2009.1.42"
    assert asset.extra["slug"] == "metier-a-ruban-manufrance"
    assert asset.extra["subtitle"] == "Atelier de rubanerie"
    assert asset.extra["inventory_number"] == "2009.1.42"
    assert asset.extra["domain"] == "Rubanerie"
    assert asset.extra["material"] == "fonte, bois"
    assert asset.extra["technique"] == "assemblage"
    assert asset.extra["owner"] == "Musée d'Art et d'Industrie"
    assert asset.extra["has_image"] is True
    assert asset.extra["collections"] == ["rubans", "la-mecanique-de-l-art"]
    assert "rubanerie" in asset.tags
    assert "Manufrance" in asset.tags

    # one CloudFront URL per image media file (the video entry is dropped)
    images = asset.extra["images"]
    assert len(images) == 2
    assert asset.image_url == images[0]
    assert asset.thumbnail_url == images[0]
    for url in images:
        assert url.startswith(CF_HOST + "/")
        payload = _decode_token(url)
        assert payload["bucket"] == "opac-prod-media"
        assert payload["key"].startswith("st-etienne01/mai04opacweb/")

    url, kwargs = http.calls[0]
    assert url == SEARCH_URL
    assert kwargs["params"]["onlineFilter"] == "online"
    assert kwargs["params"]["onlyImage"] == "true"
    assert kwargs["params"]["items_per_page"] == "100"
    assert kwargs["params"]["page"] == "1"
    assert kwargs["params"]["query"] == "ruban"


# --- (b) CloudFront URL builder --------------------------------------------------


def test_cloudfront_url_encodes_expected_payload():
    url = cloudfront_url(
        CF_HOST,
        "opac-prod-media",
        "st-etienne01/mai04opacweb/abc123.jpg",
        1200,
    )
    assert url.startswith(CF_HOST + "/")
    assert _decode_token(url) == {
        "bucket": "opac-prod-media",
        "key": "st-etienne01/mai04opacweb/abc123.jpg",
        "edits": {"resize": {"width": 1200, "height": 1200, "fit": "inside"}},
    }


def test_cloudfront_url_width_is_configurable():
    url = cloudfront_url("https://host.example", "bucket", "client/profile/f.jpg", 300)
    payload = _decode_token(url)
    assert payload["edits"]["resize"]["width"] == 300
    assert payload["edits"]["resize"]["height"] == 300
    assert payload["edits"]["resize"]["fit"] == "inside"


# --- (c) licence → disabled / non-commercial -------------------------------------


def test_descriptor_is_disabled_and_non_commercial():
    raw = _raw()
    assert raw["enabled"] is False
    assert raw["extra"]["license"]["nc"] is True
    assert raw["extra"]["license"]["reusable"] is False

    descriptor = _descriptor()
    assert descriptor.enabled is False
    connector = build_connector(descriptor, _GuardedHttp())
    assert isinstance(connector, MAISaintEtienneConnector)


# --- (d) pagination stops on empty page / when the total is reached --------------


async def test_search_stops_when_total_reached():
    page = {
        "hydra:totalItems": 2,
        "hydra:member": [NOTICE, {**NOTICE, "id": "b"}],
    }
    http = FakeHttp(page)
    connector = MAISaintEtienneConnector(_descriptor(), http)

    assets = await connector.search("", limit=1000)

    assert len(assets) == 2
    assert len(http.calls) == 1  # total reached → no second request


async def test_search_stops_on_empty_page():
    page1 = {
        "hydra:totalItems": 5,
        "hydra:member": [NOTICE, {**NOTICE, "id": "b"}],
    }
    page2 = {"hydra:totalItems": 5, "hydra:member": []}
    http = FakeHttp(page1, page2)
    connector = MAISaintEtienneConnector(_descriptor(), http)

    assets = await connector.search("", limit=1000)

    assert len(assets) == 2
    assert len(http.calls) == 2  # empty page → stop
    assert http.calls[1][1]["params"]["page"] == "2"
