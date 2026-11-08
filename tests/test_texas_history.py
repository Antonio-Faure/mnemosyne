"""The Portal to Texas History (UNT) IIIF connector — mocked, offline.

The manifest JSON shapes below mirror the live IIIF Presentation v2 manifests
served at ``https://texashistory.unt.edu/ark:/67531/{ark}/manifest/``: a
``{label, value}`` metadata list with dotted UNTL labels, a dict ``thumbnail``,
and an Image API v2 level2 ``service`` under ``.../iiif/ark:/67531/{ark}/m1/1``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.texas_history import TexasHistoryConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"

NAAN = "67531"
BASE = "https://texashistory.unt.edu"


def _manifest_url(ark: str) -> str:
    return f"{BASE}/ark:/{NAAN}/{ark}/manifest/"


def _service(ark: str) -> str:
    return f"{BASE}/iiif/ark:/{NAAN}/{ark}/m1/1"


def _canvas(ark: str, index: int = 1, *, service: bool = True) -> dict:
    resource = {
        "@id": f"{BASE}/iiif/ark:/{NAAN}/{ark}/m1/{index}/full/max/0/default.jpg",
        "@type": "dctypes:Image",
        "format": "image/jpeg",
    }
    if service:
        resource["service"] = {
            "@id": _service(ark),
            "profile": "http://iiif.io/api/image/2/level2.json",
        }
    return {
        "@id": f"{BASE}/ark:/{NAAN}/{ark}/m1/{index}/canvas/",
        "@type": "sc:Canvas",
        "label": f"Image {index}",
        "width": 1500,
        "height": 1210,
        "images": [
            {
                "@id": f"{BASE}/ark:/{NAAN}/{ark}/m1/{index}/image/",
                "@type": "oa:Annotation",
                "motivation": "sc:painting",
                "resource": resource,
            }
        ],
    }


def _manifest(
    ark: str,
    *,
    label: str = "Interior of Midwest Equipment Company",
    title: str | None = None,
    date: str | None = "1930",
    creator: str | None = None,
    rights: str | None = None,
    access: str | None = None,
    license_code: str | None = None,
    resource_type: str = "image_photo",
    subjects: tuple[str, ...] = ("Business, Economics and Finance - Oil and Gas",),
    n_canvases: int = 1,
    thumbnail: bool = True,
    attribution: str = "Permian Basin Petroleum Museum - The Portal to Texas History",
) -> dict:
    metadata: list[dict] = [{"label": "title", "value": title or label}]
    if creator:
        metadata.append({"label": "creator", "value": creator})
    if date:
        metadata.append({"label": "date.creation", "value": date})
    for subject in subjects:
        metadata.append({"label": "subject.UNTL-BS", "value": subject})
    if access:
        metadata.append({"label": "rights.access", "value": access})
    if license_code:
        metadata.append({"label": "rights.license", "value": license_code})
    if rights:
        metadata.append({"label": "rights", "value": rights})
    metadata.append({"label": "collection", "value": "SG09"})
    metadata.append({"label": "institution", "value": "PBPM"})
    metadata.append({"label": "resourceType", "value": resource_type})

    manifest = {
        "@id": _manifest_url(ark),
        "@context": "http://iiif.io/api/presentation/2/context.json",
        "@type": "sc:Manifest",
        "label": label,
        "metadata": metadata,
        "related": {"@id": f"{BASE}/ark:/{NAAN}/{ark}/", "format": "text/html"},
        "attribution": attribution,
        "sequences": [
            {
                "@id": f"{BASE}/ark:/{NAAN}/{ark}/m1/sequence/",
                "@type": "sc:Sequence",
                "canvases": [_canvas(ark, i + 1) for i in range(n_canvases)],
            }
        ],
    }
    if thumbnail:
        manifest["thumbnail"] = {
            "@id": f"{BASE}/ark:/{NAAN}/{ark}/thumbnail/",
            "@type": "dctypes:Image",
            "width": 111,
            "height": 90,
            "format": "image/jpeg",
        }
    return manifest


class FakeHttp:
    """Routes manifest URLs to canned JSON; nothing else may be requested."""

    def __init__(self, manifests: dict | None = None):
        self.manifests = manifests or {}
        self.get_json_calls: list[str] = []

    async def get_json(self, url: str, **kwargs):
        self.get_json_calls.append(url)
        if url not in self.manifests:
            raise RuntimeError(f"no manifest route for {url}")
        return self.manifests[url]


def _descriptor(**overrides) -> SourceDescriptor:
    base = {
        "id": "texas_history",
        "name": "The Portal to Texas History (UNT)",
        "institution": "University of North Texas Libraries",
        "country": "US",
        "protocol": Protocol.IIIF,
        "base_url": BASE,
        "auth": "none",
        "license": "Conditions d'utilisation du Portal to Texas History",
        "rights": "Attribution requise",
        "seeds": [],
        "extra": {
            "ark_naan": NAAN,
            "manifest_pattern": f"{BASE}/ark:/{NAAN}/{{ark}}/manifest/",
            "notice_pattern": f"{BASE}/ark:/{NAAN}/{{ark}}/",
            "attribution": "The Portal to Texas History (UNT Libraries)",
        },
    }
    base.update(overrides)
    return SourceDescriptor(**base)


# -- registry / descriptor ------------------------------------------------


def test_build_connector_returns_texas_history() -> None:
    connector = build_connector(_descriptor(), FakeHttp())
    assert isinstance(connector, TexasHistoryConnector)


def test_real_descriptor_builds_texas_history_connector() -> None:
    raw = yaml.safe_load((SOURCES_DIR / "texas_history.yaml").read_text(encoding="utf-8"))
    assert raw["id"] == "texas_history"
    assert raw["protocol"] == "iiif"
    assert raw.get("enabled", True) is True
    assert raw["license"]
    assert raw["extra"]["ark_naan"] == NAAN
    assert raw["extra"]["manifest_pattern"].endswith("/manifest/")
    # no HTML search: off-policy without written consent (seeds + IIIF only)
    assert "search_url" not in raw["extra"]
    assert "crawl_delay" not in raw["extra"]
    assert raw["seeds"]
    assert isinstance(build_connector(SourceDescriptor(**raw), FakeHttp()), TexasHistoryConnector)


# -- manifest parsing -----------------------------------------------------


@pytest.mark.asyncio
async def test_single_photo_builds_one_record() -> None:
    ark = "metapth50195"
    http = FakeHttp(
        {_manifest_url(ark): _manifest(ark, label="Interior of Midwest Equipment Company")}
    )
    connector = TexasHistoryConnector(_descriptor(seeds=[ark]), http)

    assets = await connector.search("", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "texas_history"
    assert asset.title == "Interior of Midwest Equipment Company"
    assert asset.source_asset_id == ark
    assert asset.image_url == f"{_service(ark)}/full/!1200,1200/0/default.jpg"
    assert asset.image_url.endswith("/full/!1200,1200/0/default.jpg")
    assert asset.thumbnail_url == f"{BASE}/ark:/{NAAN}/{ark}/thumbnail/"
    assert asset.iiif_id == _service(ark)
    assert asset.page_url == f"{BASE}/ark:/{NAAN}/{ark}/"
    assert asset.year == 1930
    assert asset.tags == ["Business, Economics and Finance - Oil and Gas"]
    assert asset.extra["ark"] == ark
    assert asset.extra["collection"] == "SG09"
    assert asset.extra["institution"] == "PBPM"
    assert asset.extra["resource_type"] == "image_photo"


@pytest.mark.asyncio
async def test_creator_and_date_are_parsed() -> None:
    ark = "metapth50185"
    http = FakeHttp(
        {
            _manifest_url(ark): _manifest(
                ark, label="Group Portrait", creator="Jack Nolan", date="1924"
            )
        }
    )
    connector = TexasHistoryConnector(_descriptor(seeds=[ark]), http)

    (asset,) = await connector.search("")
    assert asset.title == "Group Portrait"
    assert asset.creator == "Jack Nolan"
    assert asset.date_text == "1924"
    assert asset.year == 1924


@pytest.mark.asyncio
async def test_license_public_domain_from_rights() -> None:
    ark = "metapth1736805"
    http = FakeHttp({_manifest_url(ark): _manifest(ark, rights="pd")})
    connector = TexasHistoryConnector(_descriptor(seeds=[ark]), http)

    (asset,) = await connector.search("")
    assert asset.license == "Public Domain"


@pytest.mark.asyncio
async def test_license_mapped_from_rights_license() -> None:
    ark = "metapth41337"
    http = FakeHttp(
        {_manifest_url(ark): _manifest(ark, access="public", license_code="by-nc-nd")}
    )
    connector = TexasHistoryConnector(_descriptor(seeds=[ark]), http)

    (asset,) = await connector.search("")
    assert asset.license == "CC BY-NC-ND (Attribution Non-commercial NoDerivatives)"


@pytest.mark.asyncio
async def test_license_falls_back_to_descriptor() -> None:
    ark = "metapth50195"
    http = FakeHttp({_manifest_url(ark): _manifest(ark)})
    connector = TexasHistoryConnector(_descriptor(seeds=[ark]), http)

    (asset,) = await connector.search("")
    assert asset.license == connector.descriptor.license


@pytest.mark.asyncio
async def test_restricted_access_is_skipped() -> None:
    ark = "metapth999999"
    http = FakeHttp({_manifest_url(ark): _manifest(ark, access="restricted")})
    connector = TexasHistoryConnector(_descriptor(seeds=[ark]), http)
    assert await connector.search("") == []


@pytest.mark.asyncio
async def test_multi_canvas_item_yields_single_record() -> None:
    ark = "metapth41337"
    http = FakeHttp({_manifest_url(ark): _manifest(ark, n_canvases=5, label="A Book")})
    connector = TexasHistoryConnector(_descriptor(seeds=[ark]), http)

    assets = await connector.search("", limit=1000)
    assert len(assets) == 1
    assert assets[0].source_asset_id == ark


@pytest.mark.asyncio
async def test_service_is_derived_from_resource_when_absent() -> None:
    ark = "metapth50196"
    manifest = _manifest(ark)
    manifest["sequences"][0]["canvases"][0]["images"][0]["resource"].pop("service")
    http = FakeHttp({_manifest_url(ark): manifest})
    connector = TexasHistoryConnector(_descriptor(seeds=[ark]), http)

    (asset,) = await connector.search("")
    assert asset.iiif_id == _service(ark)
    assert asset.image_url.endswith("/full/!1200,1200/0/default.jpg")


# -- seeds / politeness ----------------------------------------------


@pytest.mark.asyncio
async def test_search_uses_only_seeds_and_never_html() -> None:
    """No keyword/HTML search (Altcha-gated): only the curated ARKs, via IIIF."""
    ark = "metapth50195"
    http = FakeHttp({_manifest_url(ark): _manifest(ark)})
    connector = TexasHistoryConnector(_descriptor(seeds=[ark]), http)

    assets = await connector.search("Myron Kinley oil well fire", limit=10)
    assert len(assets) == 1
    assert assets[0].extra["ark"] == ark
    assert http.get_json_calls == [_manifest_url(ark)]


@pytest.mark.asyncio
async def test_search_is_deduplicated_and_capped() -> None:
    arks = ["metapth1", "metapth2", "metapth3"]
    http = FakeHttp({_manifest_url(a): _manifest(a) for a in arks})
    connector = TexasHistoryConnector(_descriptor(seeds=arks + arks), http)

    assets = await connector.search("", limit=2)
    assert len(assets) == 2
    assert http.get_json_calls == [_manifest_url("metapth1"), _manifest_url("metapth2")]


@pytest.mark.asyncio
async def test_search_without_seeds_returns_nothing() -> None:
    connector = TexasHistoryConnector(_descriptor(seeds=[]), FakeHttp({}))
    assert await connector.search("mot-inexistant") == []


@pytest.mark.asyncio
async def test_manifest_failure_is_skipped() -> None:
    ark = "metapth50195"
    connector = TexasHistoryConnector(_descriptor(seeds=[ark]), FakeHttp({}))
    assert await connector.search("") == []
