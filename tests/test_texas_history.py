"""The Portal to Texas History (UNT) IIIF connector — mocked, offline.

The JSON shapes below mirror what the browser agent verified live against
`https://texashistory.unt.edu` (one IIIF Presentation v2 manifest per ARK,
dotted ``metadata`` labels such as ``title``/``date.creation``/``resourceType``/
``rights.*``, ``related.@id``/``thumbnail.@id``, an IIIF Image API service per
canvas). The keyword search is Altcha-gated, so the connector is seeds-only.
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
SVC = "https://texashistory.unt.edu/iiif/ark:/67531/metapth221870/m1/1"


def _manifest_url(ark: str) -> str:
    return f"{BASE}/ark:/{NAAN}/{ark}/manifest/"


def _canvas(index: int, *, service: str | None = SVC) -> dict:
    canvas = {
        "@type": "sc:Canvas",
        "label": str(index),
        "width": 3000,
        "height": 2000,
    }
    if service is not None:
        canvas["images"] = [
            {
                "@type": "oa:Annotation",
                "resource": {
                    "@id": f"{service}/full/max/0/default.jpg",
                    "@type": "dctypes:Image",
                    "service": {
                        "@id": service,
                        "profile": "http://iiif.io/api/image/2/level2.json",
                    },
                },
            }
        ]
    return canvas


def _manifest(
    ark: str,
    *,
    title: str = "Oil Well Fire, Port Arthur",
    date: str = "1902",
    right_license: str | None = None,
    access: str | None = None,
    n_canvases: int = 1,
    related: bool = True,
    thumbnail: bool = True,
) -> dict:
    metadata = [
        {"label": "title", "value": title},
        {"label": "date.creation", "value": date},
        {"label": "resourceType", "value": "image_photo"},
        {"label": "rights", "value": "Public Domain"},
    ]
    if right_license is not None:
        metadata.append({"label": "rights.license", "value": right_license})
    if access is not None:
        metadata.append({"label": "rights.access", "value": access})
    manifest = {
        "@context": "http://iiif.io/api/presentation/2/context.json",
        "@id": _manifest_url(ark),
        "@type": "sc:Manifest",
        "label": title,
        "metadata": metadata,
        "sequences": [
            {"@type": "sc:Sequence", "canvases": [_canvas(i + 1) for i in range(n_canvases)]}
        ],
        "attribution": "The Portal to Texas History, UNT Libraries",
    }
    if related:
        manifest["related"] = {"@id": f"{BASE}/ark:/{NAAN}/{ark}/"}
    if thumbnail:
        manifest["thumbnail"] = {"@id": f"{SVC}/full/!200,200/0/default.jpg"}
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
        "name": "The Portal to Texas History (UNT Libraries)",
        "institution": "University of North Texas Libraries",
        "country": "US",
        "protocol": Protocol.IIIF,
        "base_url": BASE,
        "auth": "none",
        "license": "Public Domain / per-item rights",
        "rights": "The Portal to Texas History, UNT Libraries",
        "seeds": [],
        "extra": {
            "ark_naan": NAAN,
            "manifest_pattern": f"{BASE}/ark:/{NAAN}/{{ark}}/manifest/",
            "notice_pattern": f"{BASE}/ark:/{NAAN}/{{ark}}/",
            "attribution": "The Portal to Texas History, UNT Libraries",
            "image_size": "!1200,1200",
            "thumbnail_size": "!400,400",
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
    assert raw["seeds"]
    assert isinstance(
        build_connector(SourceDescriptor(**raw), FakeHttp()), TexasHistoryConnector
    )


# -- manifest parsing -----------------------------------------------------


@pytest.mark.asyncio
async def test_single_item_builds_one_record() -> None:
    ark = "metapth221870"
    http = FakeHttp({_manifest_url(ark): _manifest(ark)})
    connector = TexasHistoryConnector(_descriptor(seeds=[ark]), http)

    assets = await connector.search("", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "texas_history"
    assert asset.source_asset_id == ark
    assert asset.title == "Oil Well Fire, Port Arthur"
    assert asset.date_text == "1902"
    assert asset.year == 1902
    assert asset.image_url == f"{SVC}/full/!1200,1200/0/default.jpg"
    assert asset.thumbnail_url == f"{SVC}/full/!200,200/0/default.jpg"
    assert asset.iiif_id == SVC
    assert asset.page_url == f"{BASE}/ark:/{NAAN}/{ark}/"
    assert asset.width == 3000 and asset.height == 2000
    assert asset.extra["ark"] == ark
    assert asset.extra["notice"] == f"{BASE}/ark:/{NAAN}/{ark}/"
    assert asset.extra["resource_type"] == "image_photo"
    assert "image_photo" in asset.tags


@pytest.mark.asyncio
async def test_first_displayable_canvas_used_for_multi_page_item() -> None:
    ark = "metapth41398"
    http = FakeHttp({_manifest_url(ark): _manifest(ark, n_canvases=3)})
    connector = TexasHistoryConnector(_descriptor(seeds=[ark]), http)

    (asset,) = await connector.search("")
    # one record per item, built from the first canvas's service
    assert asset.source_asset_id == ark
    assert asset.iiif_id == SVC


@pytest.mark.asyncio
async def test_license_parsed_from_rights_license() -> None:
    ark = "metapth41398"
    manifest = _manifest(ark, right_license="CC BY 4.0")
    http = FakeHttp({_manifest_url(ark): manifest})
    connector = TexasHistoryConnector(_descriptor(seeds=[ark]), http)

    (asset,) = await connector.search("")
    assert asset.license == "CC BY 4.0"


@pytest.mark.asyncio
async def test_license_falls_back_to_descriptor() -> None:
    ark = "metapth202335"
    http = FakeHttp({_manifest_url(ark): _manifest(ark)})
    connector = TexasHistoryConnector(_descriptor(seeds=[ark]), http)

    (asset,) = await connector.search("")
    assert asset.license == connector.descriptor.license


@pytest.mark.asyncio
async def test_rights_falls_back_to_attribution() -> None:
    ark = "metapth202335"
    manifest = _manifest(ark)
    manifest["metadata"] = [m for m in manifest["metadata"] if m["label"] != "rights"]
    http = FakeHttp({_manifest_url(ark): manifest})
    connector = TexasHistoryConnector(_descriptor(seeds=[ark]), http)

    (asset,) = await connector.search("")
    assert asset.rights == "The Portal to Texas History, UNT Libraries"


@pytest.mark.asyncio
async def test_thumbnail_and_page_url_fall_back_when_absent() -> None:
    ark = "metapth50108"
    http = FakeHttp({_manifest_url(ark): _manifest(ark, related=False, thumbnail=False)})
    connector = TexasHistoryConnector(_descriptor(seeds=[ark]), http)

    (asset,) = await connector.search("")
    assert asset.page_url == f"{BASE}/ark:/{NAAN}/{ark}/"
    assert asset.thumbnail_url == f"{SVC}/full/!400,400/0/default.jpg"


@pytest.mark.asyncio
async def test_restricted_item_is_skipped() -> None:
    ark = "metapth999999"
    http = FakeHttp({_manifest_url(ark): _manifest(ark, access="restricted")})
    connector = TexasHistoryConnector(_descriptor(seeds=[ark]), http)
    assert await connector.search("") == []


@pytest.mark.asyncio
async def test_item_without_canvas_image_yields_no_record() -> None:
    ark = "metapth888888"
    manifest = _manifest(ark)
    manifest["sequences"][0]["canvases"] = [_canvas(1, service=None)]
    http = FakeHttp({_manifest_url(ark): manifest})
    connector = TexasHistoryConnector(_descriptor(seeds=[ark]), http)
    assert await connector.search("") == []


# -- seeds / politeness ---------------------------------------------------


@pytest.mark.asyncio
async def test_search_uses_only_seeds_and_never_html() -> None:
    """No Altcha circumvention: only the curated ARKs, through IIIF."""
    ark = "metapth221870"
    http = FakeHttp({_manifest_url(ark): _manifest(ark)})
    connector = TexasHistoryConnector(_descriptor(seeds=[ark]), http)

    assets = await connector.search("incendie puits", limit=10)
    assert len(assets) == 1
    assert http.get_json_calls == [_manifest_url(ark)]


@pytest.mark.asyncio
async def test_search_without_seeds_returns_nothing() -> None:
    connector = TexasHistoryConnector(_descriptor(seeds=[]), FakeHttp({}))
    assert await connector.search("anything") == []


@pytest.mark.asyncio
async def test_manifest_failure_is_skipped() -> None:
    ark = "metapth000000"
    connector = TexasHistoryConnector(_descriptor(seeds=[ark]), FakeHttp({}))
    assert await connector.search("") == []


@pytest.mark.asyncio
async def test_seeds_are_deduplicated_and_capped_at_limit() -> None:
    a, b = "metapth111111", "metapth222222"
    http = FakeHttp({_manifest_url(a): _manifest(a), _manifest_url(b): _manifest(b)})
    connector = TexasHistoryConnector(_descriptor(seeds=[a, a, b]), http)

    assets = await connector.search("", limit=1)
    assert len(assets) == 1
    # dedup: the repeated seed is fetched only once, and the cap stops early
    assert http.get_json_calls == [_manifest_url(a)]
