"""National Diet Library (NDL) IIIF source — mocked end-to-end.

`dl.ndl.go.jp` (NDL Digital Collections) serves per-object IIIF Presentation v2
manifests (`/api/iiif/<pid>/manifest.json`) whose images come from the IIIF
Image API (`/api/iiif/<pid>/<image-id>`, info.json confirmed, level1). The host
exposes no aggregate IIIF entry point — probes for collection/manifest.json,
manifest.json, collection.json, collection/collection.json,
collections/manifest.json and <pid>/collection.json all return 404 and no IIIF
search endpoint is published — so the descriptor points the generic
`src/mnemosyne/sources/iiif.py` connector at a single manifest via
`extra.manifest` (as for bsb/llgc/colenda). No bespoke connector is needed: the
generic connector walks the v2 `sequences/canvases/images/resource` shape and
normalizes the first canvas.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.iiif import IIIFConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"
MANIFEST_URL = "https://dl.ndl.go.jp/api/iiif/1169293/manifest.json"
IMAGE_SERVICE = "https://dl.ndl.go.jp/api/iiif/1169293/R0000001"

# Shape mirrors the live 1169293 manifest (v2 `sc:Manifest`, NDL Digital Collections).
MANIFEST = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@type": "sc:Manifest",
    "@id": MANIFEST_URL,
    "label": "最新中学百科宝典",
    "metadata": [
        {"label": "Persistent ID", "value": "info:ndljp/pid/1169293"},
        {"label": "Title", "value": "最新中学百科宝典"},
        {"label": "Creator", "value": "大日本国民中学会 編"},
        {"label": "Publisher", "value": "大日本国民中学会"},
        {"label": "Publication Date", "value": "1935.4"},
        {"label": "Publication Date (W3CDTF fortmat)", "value": "1935"},
        {"label": "Access Restrictions", "value": "PDM"},
        {"label": "URL", "value": "https://dl.ndl.go.jp/info:ndljp/pid/1169293"},
    ],
    "license": (
        "https://dl.ndl.go.jp/ja/help_iiif#"
        "api-%E3%81%AE%E5%88%A9%E7%94%A8%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6"
    ),
    "attribution": "国立国会図書館 National Diet Library, JAPAN",
    "sequences": [
        {
            "@type": "sc:Sequence",
            "canvases": [
                {
                    "@id": "https://dl.ndl.go.jp/api/iiif/1169293/canvas/1",
                    "@type": "sc:Canvas",
                    "images": [
                        {
                            "@type": "oa:Annotation",
                            "resource": {
                                "@id": f"{IMAGE_SERVICE}/full/full/0/default.jpg",
                                "@type": "dctypes:Image",
                                "service": {
                                    "@context": "http://iiif.io/api/image/2/context.json",
                                    "@id": IMAGE_SERVICE,
                                    "profile": "http://iiif.io/api/image/2/level1.json",
                                },
                            },
                        }
                    ],
                }
            ],
        }
    ],
}


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes

    async def get_json(self, url, **kwargs):
        return self.routes[url]


def _load() -> dict:
    return yaml.safe_load((SOURCES_DIR / "ndl.yaml").read_text(encoding="utf-8"))


def test_descriptor_is_keyless_iiif():
    data = _load()
    assert data["id"] == "ndl"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["base_url"] == "https://dl.ndl.go.jp"
    assert data["extra"]["manifest"] == MANIFEST_URL
    # a stable object identifier is recorded for provenance
    assert data["extra"]["collection_id"] == "1169293"
    assert data["license"]


def test_descriptor_uses_generic_iiif_connector():
    descriptor = SourceDescriptor(**_load())
    connector = build_connector(descriptor, FakeHttp({}))
    assert isinstance(connector, IIIFConnector)


@pytest.mark.asyncio
async def test_search_builds_asset_from_manifest():
    descriptor = SourceDescriptor(**_load())
    http = FakeHttp({MANIFEST_URL: MANIFEST})
    connector = build_connector(descriptor, http)

    assets = await connector.search("最新中学", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "ndl"
    assert asset.title == "最新中学百科宝典"
    assert asset.creator == "大日本国民中学会 編"
    assert asset.year == 1935
    assert asset.license == MANIFEST["license"]
    assert asset.image_url == f"{IMAGE_SERVICE}/full/full/0/default.jpg"
    assert asset.thumbnail_url == f"{IMAGE_SERVICE}/full/512,/0/default.jpg"
    assert asset.iiif_id == IMAGE_SERVICE


@pytest.mark.asyncio
async def test_search_filters_out_non_matching_query():
    descriptor = SourceDescriptor(**_load())
    http = FakeHttp({MANIFEST_URL: MANIFEST})
    connector = build_connector(descriptor, http)

    assert await connector.search("zzzznomatch", limit=10) == []
