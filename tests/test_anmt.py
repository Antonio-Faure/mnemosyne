"""ANMT (Roubaix) Ligeo-Archives/Boscop IIIF connector — mocked, offline.

The manifest JSON shapes below mirror what the browser agent verified live
against `https://recherche-anmt.culture.gouv.fr` (one IIIF Presentation v2
manifest per ARK, canvases carrying a IIIF Image API v3 service, per-canvas
`ligeoRestrictedAccess`, reuse terms in `ligeoReUseProfil.content`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.anmt import AnmtConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"

NAAN = "60879"
BASE = "https://recherche-anmt.culture.gouv.fr"
SVC = f"{BASE}/iiif/2015_51_Num/FRANMT_2015_51"


def _manifest_url(ark: str) -> str:
    return f"{BASE}/ark:/{NAAN}/{ark}/manifest"


def _canvas(index: int, *, restricted: bool = False) -> dict:
    service = f"{SVC}_{index}.jpg"
    canvas = {
        "@id": f"{service}/canvas",
        "@type": "sc:Canvas",
        "label": f"Vue {index}",
        "width": 4000,
        "height": 3000,
        # the canvas thumbnail is a plain string on this platform
        "thumbnail": f"{service}/full/!200,200/0/default.jpg",
        "images": [
            {
                "@type": "oa:Annotation",
                "resource": {
                    "@id": f"{service}/full/full/0/default.jpg",
                    "@type": "dctypes:Image",
                    "service": {
                        "@id": service,
                        "profile": "http://iiif.io/api/image/3/level2.json",
                    },
                },
            }
        ],
    }
    if restricted:
        canvas["ligeoRestrictedAccess"] = True
    return canvas


def _manifest(
    ark: str,
    n_canvases: int,
    *,
    restricted: tuple[int, ...] = (),
    label: str = "Fonds",
    reuse: bool = True,
) -> dict:
    canvases = [_canvas(i, restricted=(i in restricted)) for i in range(1, n_canvases + 1)]
    manifest = {
        "@context": "http://iiif.io/api/presentation/2/context.json",
        "@id": _manifest_url(ark),
        "@type": "sc:Manifest",
        "label": label,
        "metadata": [
            {"label": "Cote", "value": ark},
            {"label": "Date", "value": "1912"},
        ],
        "sequences": [{"@type": "sc:Sequence", "canvases": canvases}],
    }
    if reuse:
        manifest["ligeoReUseProfil"] = {
            "content": (
                "<p>Réutilisation libre à des fins commerciales et non "
                "commerciales, gratuite, pour le monde entier, sans limitation "
                "de durée. Attribution : origine, cote, titre du fonds.</p>"
            )
        }
    return manifest


class _Response:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeHttp:
    """Routes manifest URLs to JSON and the search URL to an HTML page."""

    def __init__(self, manifests: dict | None = None, search_html: str | None = None):
        self.manifests = manifests or {}
        self.search_html = search_html
        self.get_json_calls: list[str] = []
        self.get_calls: list[str] = []

    async def get_json(self, url: str, **kwargs):
        self.get_json_calls.append(url)
        if url not in self.manifests:
            raise RuntimeError(f"no manifest route for {url}")
        return self.manifests[url]

    async def get(self, url: str, **kwargs):
        self.get_calls.append(url)
        return _Response(self.search_html or "")


def _descriptor(**overrides) -> SourceDescriptor:
    base = {
        "id": "anmt",
        "name": "Archives nationales du monde du travail (Roubaix)",
        "institution": "Archives nationales du monde du travail",
        "country": "FR",
        "protocol": Protocol.IIIF,
        "base_url": BASE,
        "auth": "none",
        "license": "Réutilisation libre (décision du 21 août 2017)",
        "rights": "ANMT — attribution requise",
        "seeds": [],
        "extra": {
            "ark_naan": NAAN,
            "manifest_pattern": f"{BASE}/ark:/{NAAN}/{{ark}}/manifest",
            "notice_pattern": f"{BASE}/ark:/{NAAN}/{{ark}}",
            "viewer_pattern": f"{BASE}/ark:/{NAAN}/{{ark}}/daogrp/0",
            "search_url": (
                f"{BASE}/archive/recherche/simple/n:19"
                "?RECH_S={query}&RECH_TYP=and&RECH_images=1"
            ),
            "attribution": "Archives nationales du monde du travail",
        },
    }
    base.update(overrides)
    return SourceDescriptor(**base)


# -- registry / descriptor ------------------------------------------------


def test_build_connector_returns_anmt() -> None:
    connector = build_connector(_descriptor(), FakeHttp())
    assert isinstance(connector, AnmtConnector)


def test_real_descriptor_builds_anmt_connector() -> None:
    raw = yaml.safe_load((SOURCES_DIR / "anmt.yaml").read_text(encoding="utf-8"))
    assert raw["id"] == "anmt"
    assert raw["protocol"] == "iiif"
    assert raw.get("enabled", True) is True
    assert raw["license"]
    assert raw["extra"]["ark_naan"] == NAAN
    assert raw["extra"]["manifest_pattern"].endswith("/manifest")
    assert raw["seeds"]
    assert isinstance(build_connector(SourceDescriptor(**raw), FakeHttp()), AnmtConnector)


# -- manifest parsing -----------------------------------------------------


@pytest.mark.asyncio
async def test_single_open_canvas_builds_one_record() -> None:
    ark = "110324.1083809"
    http = FakeHttp({_manifest_url(ark): _manifest(ark, 1, label="Ciments Berthelot, Grenoble.")})
    connector = AnmtConnector(_descriptor(seeds=[ark]), http)

    assets = await connector.search("", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "anmt"
    assert asset.title == "Ciments Berthelot, Grenoble."
    assert asset.source_asset_id == f"{ark}#0"
    assert asset.image_url == f"{SVC}_1.jpg/full/max/0/default.jpg"
    assert asset.image_url.endswith("/full/max/0/default.jpg")
    assert asset.thumbnail_url.endswith("/full/!200,200/0/default.jpg")
    assert asset.iiif_id == f"{SVC}_1.jpg"
    assert asset.page_url == f"{BASE}/ark:/{NAAN}/{ark}/daogrp/0"
    assert asset.extra["notice"] == f"{BASE}/ark:/{NAAN}/{ark}"
    assert asset.extra["attribution"] == "Archives nationales du monde du travail"
    assert asset.year == 1912


@pytest.mark.asyncio
async def test_license_parsed_from_reuse_profile() -> None:
    ark = "110324.1083809"
    http = FakeHttp({_manifest_url(ark): _manifest(ark, 1)})
    connector = AnmtConnector(_descriptor(seeds=[ark]), http)

    (asset,) = await connector.search("")
    assert asset.license == "Réutilisation libre (commerciale et non commerciale)"
    assert "Réutilisation libre" in asset.extra["reuse_profile"]


@pytest.mark.asyncio
async def test_license_falls_back_to_descriptor_when_no_profile() -> None:
    ark = "110324.1083809"
    http = FakeHttp({_manifest_url(ark): _manifest(ark, 1, reuse=False)})
    connector = AnmtConnector(_descriptor(seeds=[ark]), http)

    (asset,) = await connector.search("")
    assert asset.license == connector.descriptor.license


@pytest.mark.asyncio
async def test_250_canvases_are_flattened() -> None:
    ark = "375200.1894390"
    http = FakeHttp({_manifest_url(ark): _manifest(ark, 250, label="49751-50000.")})
    connector = AnmtConnector(_descriptor(seeds=[ark]), http)

    assets = await connector.search("", limit=1000)
    assert len(assets) == 250
    assert len({a.source_asset_id for a in assets}) == 250
    assert all(a.image_url.endswith("/full/max/0/default.jpg") for a in assets)


@pytest.mark.asyncio
async def test_two_canvases() -> None:
    ark = "196624.1123770"
    http = FakeHttp({_manifest_url(ark): _manifest(ark, 2, label="Photographies du personnel.")})
    connector = AnmtConnector(_descriptor(seeds=[ark]), http)
    assert len(await connector.search("")) == 2


@pytest.mark.asyncio
async def test_all_restricted_manifest_yields_no_record() -> None:
    ark = "81117.1084614"
    http = FakeHttp(
        {_manifest_url(ark): _manifest(ark, 7, restricted=tuple(range(1, 8)), label="Brochot SA.")}
    )
    connector = AnmtConnector(_descriptor(seeds=[ark]), http)
    assert await connector.search("") == []


@pytest.mark.asyncio
async def test_single_restricted_manifest_yields_no_record() -> None:
    ark = "146961.1483142"
    http = FakeHttp({_manifest_url(ark): _manifest(ark, 1, restricted=(1,))})
    connector = AnmtConnector(_descriptor(seeds=[ark]), http)
    assert await connector.search("") == []


@pytest.mark.asyncio
async def test_restricted_canvases_are_dropped() -> None:
    ark = "mix"
    http = FakeHttp({_manifest_url(ark): _manifest(ark, 4, restricted=(2, 4))})
    connector = AnmtConnector(_descriptor(seeds=[ark]), http)

    assets = await connector.search("")
    assert len(assets) == 2
    assert {a.source_asset_id for a in assets} == {f"{ark}#0", f"{ark}#2"}


# -- discovery / politeness ----------------------------------------------


@pytest.mark.asyncio
async def test_search_discovers_arks_from_html() -> None:
    ark_a, ark_b = "110324.1083809", "999.1"
    html = (
        f'<a href="/ark:/{NAAN}/{ark_a}">fonds A</a>'
        f'<a href="/ark:/{NAAN}/{ark_b}/daogrp/0">fonds B</a>'
    )
    http = FakeHttp(
        {
            _manifest_url(ark_a): _manifest(ark_a, 1, label="Fonds A"),
            _manifest_url(ark_b): _manifest(ark_b, 1, label="Fonds B"),
        },
        search_html=html,
    )
    connector = AnmtConnector(_descriptor(), http)

    assets = await connector.search("usine", limit=10)
    assert len(assets) == 2
    assert {a.extra["ark"] for a in assets} == {ark_a, ark_b}
    assert http.get_calls and "RECH_S=usine" in http.get_calls[0]


@pytest.mark.asyncio
async def test_search_falls_back_to_seeds_on_anubis_challenge() -> None:
    ark = "110324.1083809"
    challenge = (
        "<html><title>Making sure you're not a bot</title>"
        "<p>Anubis proof-of-work</p></html>"
    )
    http = FakeHttp({_manifest_url(ark): _manifest(ark, 1)}, search_html=challenge)
    connector = AnmtConnector(_descriptor(seeds=[ark]), http)

    assets = await connector.search("usine")
    assert len(assets) == 1
    assert assets[0].extra["ark"] == ark


@pytest.mark.asyncio
async def test_search_empty_discovery_returns_nothing() -> None:
    http = FakeHttp({}, search_html="<html><body>aucun résultat</body></html>")
    connector = AnmtConnector(_descriptor(seeds=["110324.1083809"]), http)

    assert await connector.search("mot-inexistant") == []


@pytest.mark.asyncio
async def test_manifest_failure_is_skipped() -> None:
    ark = "110324.1083809"
    connector = AnmtConnector(_descriptor(seeds=[ark]), FakeHttp({}))
    assert await connector.search("") == []
