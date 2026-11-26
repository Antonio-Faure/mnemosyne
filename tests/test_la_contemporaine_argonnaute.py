"""La Contemporaine / L'Argonnaute (Nanterre) — JSON API connector, offline.

The JSON shapes below mirror what was verified live against
``https://argonnaute.parisnanterre.fr/visualizer/api`` (one ``media[0]`` with a
``record`` block and a ``location{original, thumb, iiif:null}``; ``iiif`` is
always null — there is no IIIF, and there is no search endpoint, only
per-document lookups by ``arkName`` + ``uuid``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.la_contemporaine_argonnaute import (
    LaContemporaineArgonnauteConnector,
)

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"
BASE = "https://argonnaute.parisnanterre.fr"

# verified live fixtures
ARK_A = "4l6m9krbngfv"
UUID_A = "36b0a7b5-c8a7-4b1d-9ae4-6a685f4eac3d"
ARK_B = "1qxwblpsgtjh"
UUID_B = "4ab60e31-3cea-4730-a5cd-5472776ac18c"


def _api_url(ark: str, uuid: str) -> str:
    return f"{BASE}/visualizer/api?arkName={ark}&uuid={uuid}"


def _doc(
    ark: str,
    uuid: str,
    *,
    title: list[str] | None = None,
    reference_code: list[str] | None = None,
    description: str = "",
    date_from: str | None = None,
    date_to: str | None = None,
    keywords: list[str] | None = None,
    media_type: str = "image",
) -> dict:
    return {
        "counts": {"media": 1, "group": 1},
        "media": [
            {
                "url": f"{BASE}/ark:/14707/{ark}/{uuid}",
                "record": {
                    "arkId": {"arkName": ark, "naan": 14707},
                    "url": f"{BASE}/ark:/14707/{ark}",
                    "title": title or [],
                    "referenceCode": reference_code or [],
                    "description": description,
                    "period": {
                        "boundaries": [date_from, date_to],
                        "certainty": None,
                    },
                    "locationKeywords": keywords or [],
                },
                "uuid": uuid,
                "location": {
                    "original": f"{BASE}/images/{uuid}.jpg",
                    "thumb": f"{BASE}/images/{uuid}_thumbnail.jpg",
                    "iiif": None,
                },
                "type": media_type,
                "format": "jpg",
                "title": None,
            }
        ],
        "app": {
            "toolbar": {"isIIIFEnabled": False, "isDownloadEnabled": True},
            "licenses": {"visualizer": {"enabled": True}},
        },
    }


def _doc_a() -> dict:
    return _doc(
        ARK_A,
        UUID_A,
        title=["La grève des Bateliers à Conflans"],
        reference_code=["PH C4 03 (16)", "Phot 13821"],
        description="Type d'inscription : Visa de censure.",
        date_from="1936-01-01",
        date_to="1936-12-31",
        keywords=["Paris (France)"],
    )


def _doc_b() -> dict:
    return _doc(
        ARK_B,
        UUID_B,
        title=[
            "Paris. Usine Citroën. Quai de Javel. L'infirmerie. "
            "Infirmière pansant un ouvrier blessé"
        ],
        reference_code=["VAL 364/022"],
        description="Source ou opérateur : Don Citroën",
        date_from="1915-03-01",
        date_to="1915-03-31",
        keywords=["Paris (France)"],
    )


class FakeHttp:
    """Routes ``/visualizer/api`` URLs to canned JSON; nothing else allowed."""

    def __init__(self, routes: dict | None = None):
        self.routes = routes or {}
        self.get_json_calls: list[str] = []

    async def get_json(self, url: str, **kwargs):
        self.get_json_calls.append(url)
        if url not in self.routes:
            raise RuntimeError(f"no route for {url}")
        return self.routes[url]

    async def get_bytes(self, url: str, **kwargs):  # pragma: no cover - not expected
        raise AssertionError(f"connector must not download images: {url}")


def _seed(ark: str, uuid: str) -> str:
    return f"{BASE}/ark:/14707/{ark}/{uuid}"


def _descriptor(**overrides) -> SourceDescriptor:
    base = {
        "id": "la_contemporaine_argonnaute",
        "name": "La Contemporaine — L'Argonnaute (bibliothèque numérique)",
        "institution": "La Contemporaine (ex-BDIC), Nanterre",
        "country": "FR",
        "protocol": Protocol.REST,
        "base_url": BASE,
        "auth": "none",
        "license": "Licence Ouverte / Open Licence (domaine public) — sinon tous droits réservés",
        "rights": "La Contemporaine / L'Argonnaute — voir la notice",
        "seeds": [],
        "extra": {
            "api_path": "/visualizer/api",
            "ark_naan": "14707",
            "attribution": "La Contemporaine / L'Argonnaute",
        },
    }
    base.update(overrides)
    return SourceDescriptor(**base)


# -- registry / descriptor ------------------------------------------------


def test_build_connector_returns_la_contemporaine() -> None:
    connector = build_connector(_descriptor(), FakeHttp())
    assert isinstance(connector, LaContemporaineArgonnauteConnector)


def test_real_descriptor_builds_connector() -> None:
    raw = yaml.safe_load(
        (SOURCES_DIR / "la_contemporaine_argonnaute.yaml").read_text(encoding="utf-8")
    )
    assert raw["id"] == "la_contemporaine_argonnaute"
    assert raw["protocol"] == "rest"  # NOT iiif, NOT html
    assert raw["auth"] == "none"
    assert raw.get("enabled", True) is True
    assert raw["license"]
    assert raw["extra"]["api_path"] == "/visualizer/api"
    assert raw["extra"]["ark_naan"] == "14707"
    # no HTML scraping: no consent needed because programmatic JSON API is used
    assert raw["seeds"], "seeds must not be empty"
    assert "scraping_consent" not in (raw.get("extra") or {})
    connector = build_connector(SourceDescriptor(**raw), FakeHttp())
    assert isinstance(connector, LaContemporaineArgonnauteConnector)


# -- per-document parsing -------------------------------------------------


@pytest.mark.asyncio
async def test_single_seed_builds_one_asset() -> None:
    http = FakeHttp({_api_url(ARK_A, UUID_A): _doc_a()})
    connector = LaContemporaineArgonnauteConnector(_descriptor(seeds=[_seed(ARK_A, UUID_A)]), http)

    assets = await connector.search("", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "la_contemporaine_argonnaute"
    assert asset.source_asset_id == UUID_A
    assert asset.title == "La grève des Bateliers à Conflans"
    assert asset.image_url == f"{BASE}/images/{UUID_A}.jpg"
    assert asset.thumbnail_url == f"{BASE}/images/{UUID_A}_thumbnail.jpg"
    assert asset.page_url == f"{BASE}/ark:/14707/{ARK_A}"
    assert asset.year == 1936
    assert asset.date_text == "1936-01-01/1936-12-31"
    assert asset.license == _descriptor().license
    assert "La Contemporaine" in (asset.rights or "")
    assert "Paris (France)" in asset.tags
    assert asset.extra["reference_code"] == "PH C4 03 (16) ; Phot 13821"
    assert asset.extra["ark"] == ARK_A
    # the API only — never an image download
    assert http.get_json_calls == [_api_url(ARK_A, UUID_A)]


@pytest.mark.asyncio
async def test_citroen_1915_fixture() -> None:
    http = FakeHttp({_api_url(ARK_B, UUID_B): _doc_b()})
    connector = LaContemporaineArgonnauteConnector(_descriptor(seeds=[_seed(ARK_B, UUID_B)]), http)

    assets = await connector.search("Citroën Javel", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert "Citroën" in asset.title and "Javel" in asset.title
    assert asset.year == 1915
    assert asset.extra["reference_code"] == "VAL 364/022"


@pytest.mark.asyncio
async def test_query_relevance_orders_citroen_first() -> None:
    http = FakeHttp(
        {
            _api_url(ARK_A, UUID_A): _doc_a(),
            _api_url(ARK_B, UUID_B): _doc_b(),
        }
    )
    connector = LaContemporaineArgonnauteConnector(
        _descriptor(seeds=[_seed(ARK_A, UUID_A), _seed(ARK_B, UUID_B)]), http
    )
    assets = await connector.search("ouvrier Citroën Javel", limit=10)
    assert assets[0].source_asset_id == UUID_B  # Citroën Javel matches
    assert {a.source_asset_id for a in assets} == {UUID_A, UUID_B}


# -- robustness -----------------------------------------------------------


@pytest.mark.asyncio
async def test_http_failure_is_skipped() -> None:
    # the only seed raises -> search degrades to an empty list, never raises
    http = FakeHttp({})
    connector = LaContemporaineArgonnauteConnector(
        _descriptor(seeds=[_seed(ARK_A, UUID_A)]), http
    )
    assert await connector.search("grève", limit=10) == []


@pytest.mark.asyncio
async def test_empty_media_is_ignored() -> None:
    http = FakeHttp({_api_url(ARK_A, UUID_A): {"media": []}})
    connector = LaContemporaineArgonnauteConnector(_descriptor(seeds=[_seed(ARK_A, UUID_A)]), http)
    assert await connector.search("grève", limit=10) == []


@pytest.mark.asyncio
async def test_non_image_media_is_ignored() -> None:
    http = FakeHttp({_api_url(ARK_A, UUID_A): _doc(ARK_A, UUID_A, media_type="video")})
    connector = LaContemporaineArgonnauteConnector(_descriptor(seeds=[_seed(ARK_A, UUID_A)]), http)
    assert await connector.search("grève", limit=10) == []


@pytest.mark.asyncio
async def test_limit_is_respected() -> None:
    http = FakeHttp(
        {
            _api_url(ARK_A, UUID_A): _doc_a(),
            _api_url(ARK_B, UUID_B): _doc_b(),
        }
    )
    connector = LaContemporaineArgonnauteConnector(
        _descriptor(seeds=[_seed(ARK_A, UUID_A), _seed(ARK_B, UUID_B)]), http
    )
    assert len(await connector.search("", limit=1)) == 1


@pytest.mark.asyncio
async def test_invalid_seed_is_ignored() -> None:
    connector = LaContemporaineArgonnauteConnector(
        _descriptor(seeds=["not a valid ark", "4l6m9krbngfv:" + UUID_A]), FakeHttp(
            {_api_url("4l6m9krbngfv", UUID_A): _doc_a()}
        )
    )
    assets = await connector.search("grève", limit=10)
    assert len(assets) == 1
