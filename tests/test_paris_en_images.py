"""Paris en Images (Paris Musées) connector: offline tests.

The connector is seeds-based (no public search API and no HTML scraping; the
platform exposes IIIF, cf. ``docs/SOURCES.md``): one curated ``<visuel_id>``
seed per object, resolved through its Presentation v2 manifest
``/iiif/<visuel_id>/manifest``. The full-resolution URL is only surfaced when the
object is open (CC0 / public domain); otherwise only the thumbnail + notice link
are returned.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.paris_en_images import ParisEnImagesConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"
DESCRIPTOR = SOURCES_DIR / "paris_en_images.yaml"
VISUEL = "320017427"
FULL = f"https://apicollections.parismusees.paris.fr/styles/4k/{VISUEL}.jpg"
SERVICE = f"https://apicollections.parismusees.paris.fr/iiif/image/{VISUEL}"
THUMB = f"https://apicollections.parismusees.paris.fr/styles/thumbnail/{VISUEL}.jpg"
CC0 = "https://creativecommons.org/publicdomain/zero/1.0/"


def _data() -> dict:
    return yaml.safe_load(DESCRIPTOR.read_text(encoding="utf-8"))


def _manifest_url(visuel: str = VISUEL) -> str:
    return _data()["extra"]["manifest_template"].format(visuel_id=visuel)


def _manifest(
    *,
    license_url: str | None = None,
    title: str = "Escalier du Tribunal de Commerce.",
) -> dict:
    resource = {
        "@id": FULL,
        "width": 4000,
        "height": 3000,
        "service": {"@id": SERVICE},
    }
    manifest: dict = {
        "@type": "sc:Manifest",
        "label": title,
        "metadata": [
            {"label": "Auteur", "value": ["Fichot, Michel Charles"]},
            {"label": "Date de production", "value": ["Entre 1817 et 1903"]},
            {
                "label": "Description iconographique",
                "value": ["<p>Escalier du tribunal de commerce, quai de la Corse.</p>"],
            },
            {"label": "Type d'objet", "value": ["Dessin", "Arts graphiques"]},
        ],
        "thumbnail": {"@id": THUMB},
        "sequences": [{"canvases": [{"images": [{"resource": resource}]}]}],
    }
    if license_url:
        manifest["license"] = license_url
    return manifest


class _FakeHttp:
    def __init__(self, routes: dict | None = None, error: Exception | None = None):
        self.routes = routes or {}
        self.error = error

    async def get_json(self, url, **kwargs):  # pragma: no cover - simple stub
        if self.error is not None:
            raise self.error
        if url in self.routes:
            return self.routes[url]
        raise AssertionError(f"unexpected network I/O: {url}")


def _descriptor(seeds: list[str], extra: dict | None = None) -> SourceDescriptor:
    data = _data()
    return SourceDescriptor(
        id=data["id"],
        name=data["name"],
        institution=data.get("institution"),
        protocol=Protocol(data["protocol"]),
        base_url=data["base_url"],
        auth=data["auth"],
        license=data["license"],
        seeds=seeds,
        extra=extra if extra is not None else data["extra"],
    )


def test_descriptor_is_keyless_iiif_with_seeds() -> None:
    data = _data()
    assert data["id"] == "paris_en_images"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["license"]
    assert data["extra"]["manifest_template"]
    assert data["seeds"], "a curated seed list is required (no search API)"


def test_build_connector_returns_paris_en_images() -> None:
    connector = build_connector(_descriptor(["320017427|open"]), _FakeHttp())
    assert isinstance(connector, ParisEnImagesConnector)


@pytest.mark.asyncio
async def test_cc0_seed_surfaces_full_resolution_with_credit() -> None:
    http = _FakeHttp({_manifest_url(): _manifest(license_url=CC0)})
    connector = ParisEnImagesConnector(_descriptor(["320017427|open"]), http)

    assets = await connector.search("tribunal de commerce")

    assert len(assets) == 1
    asset = assets[0]
    assert asset.image_url == FULL
    assert asset.thumbnail_url == THUMB
    assert "cc0" in (asset.license or "").lower()
    assert "tribunal" in asset.title.lower()
    # metadata HTML is stripped, never leaked into the canonical Asset
    assert "<p>" not in asset.description
    assert "tribunal de commerce" in asset.description.lower()


@pytest.mark.asyncio
async def test_restricted_item_keeps_thumbnail_only() -> None:
    # no licence hint and a manifest without an open licence => restricted
    http = _FakeHttp({_manifest_url(): _manifest()})
    connector = ParisEnImagesConnector(_descriptor(["320017427"]), http)

    assets = await connector.search("tribunal de commerce")

    assert len(assets) == 1
    asset = assets[0]
    assert asset.image_url is None
    assert asset.thumbnail_url == THUMB
    assert "notice" in (asset.rights or "").lower()


@pytest.mark.asyncio
async def test_open_licence_detected_from_manifest() -> None:
    http = _FakeHttp({_manifest_url(): _manifest(license_url=CC0)})
    connector = ParisEnImagesConnector(_descriptor(["320017427"]), http)

    assets = await connector.search("tribunal")

    assert assets and assets[0].image_url == FULL


@pytest.mark.asyncio
async def test_restricted_hint_overrides_open_manifest() -> None:
    http = _FakeHttp({_manifest_url(): _manifest(license_url=CC0)})
    connector = ParisEnImagesConnector(_descriptor(["320017427|restricted"]), http)

    assets = await connector.search("tribunal")

    assert assets and assets[0].image_url is None


@pytest.mark.asyncio
async def test_irrelevant_query_drops_seed() -> None:
    http = _FakeHttp({_manifest_url(): _manifest(license_url=CC0)})
    connector = ParisEnImagesConnector(_descriptor(["320017427|open"]), http)

    assets = await connector.search("usine de Javel 15e arrondissement")

    assert assets == []


@pytest.mark.asyncio
async def test_dead_seed_does_not_break_search() -> None:
    http = _FakeHttp(error=RuntimeError("404"))
    connector = ParisEnImagesConnector(_descriptor(["320017427|open"]), http)

    assert await connector.search("tribunal") == []
