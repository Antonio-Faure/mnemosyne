"""Lehigh Preserve (Lehigh University Libraries) IIIF source — mocked.

preserve.lehigh.edu is an Islandora 2 / Drupal repository backed by Cantaloupe.
It serves IIIF Presentation v2 manifests per node: /node/<nid>/manifest for a
single page and /node/<nid>/book-manifest aggregating every page of a paged
("book") object. Node 450566 is the book object; its plain /manifest is empty,
so the /book-manifest is the entry point handled by the generic
`src/mnemosyne/sources/iiif.py` connector.

The manifest shape below mirrors the live page manifests (fetched via
fetch_url): v2 `sc:Manifest` -> `sequences`/`canvases`/`images`/`resource`,
where each image `service` is a v3 Image API endpoint (`/iiif/3/<url-encoded
source>`) that only carries the v3 `@context` — so the connector must emit the
v3 size keyword `max` (the v2 `full` keyword returns HTTP 400).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import SourceDescriptor
from mnemosyne.sources.iiif import IIIFConnector, _service_size

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"
MANIFEST_URL = "https://preserve.lehigh.edu/node/450566/book-manifest"

# The live image service ids are URL-encoded source paths under /iiif/3/.
SERVICE_1 = (
    "https://preserve.lehigh.edu/iiif/3/"
    "https%3A%2F%2Fpreserve.lehigh.edu%2Fsystem%2Ffiles%2Fderivatives%2F"
    "service%2Fnode%2F450565%2F450565-service-file.tiff"
)
SERVICE_2 = (
    "https://preserve.lehigh.edu/iiif/3/"
    "https%3A%2F%2Fpreserve.lehigh.edu%2Fsystem%2Ffiles%2Fderivatives%2F"
    "service%2Fnode%2F450567%2F450567-service-file.tiff"
)


def _canvas(nid: str, canvas_id: str, service: str, height: int, width: int) -> dict:
    return {
        "@id": f"https://preserve.lehigh.edu/node/{nid}/canvas/{canvas_id}",
        "@type": "sc:Canvas",
        "label": f"{nid}-service-file.tiff",
        "height": height,
        "width": width,
        "images": [
            {
                "@id": f"https://preserve.lehigh.edu/node/{nid}/annotation/{canvas_id}",
                "@type": "oa:Annotation",
                "motivation": "sc:painting",
                "resource": {
                    "@id": f"{service}/full/max/0/default.jpg",
                    "@type": "dctypes:Image",
                    "format": "image/jpeg",
                    "height": height,
                    "width": width,
                    "service": {
                        "@id": service,
                        "@context": "http://iiif.io/api/image/3/context.json",
                        "profile": "level2",
                    },
                },
                "on": f"https://preserve.lehigh.edu/node/{nid}/canvas/{canvas_id}",
            }
        ],
    }


# Shape mirrors the live Lehigh "book" manifest (v2 `sc:Manifest`).
MANIFEST = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@id": MANIFEST_URL,
    "@type": "sc:Manifest",
    "label": "Binding fragment, possibly a gloss",
    "sequences": [
        {
            "@id": "https://preserve.lehigh.edu/node/450566/sequence/normal",
            "@type": "sc:Sequence",
            "canvases": [
                _canvas("450565", "2712258", SERVICE_1, 5107, 2231),
                _canvas("450567", "2712274", SERVICE_2, 1431, 4099),
            ],
        }
    ],
}


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes

    async def get_json(self, url, **kwargs):
        return self.routes[url]


def _data() -> dict:
    return yaml.safe_load((SOURCES_DIR / "lehigh.yaml").read_text(encoding="utf-8"))


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(**_data())


def test_descriptor_is_keyless_single_manifest_iiif():
    data = _data()
    assert data["id"] == "lehigh"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["base_url"] == "https://preserve.lehigh.edu"
    assert data["extra"]["manifest"] == MANIFEST_URL
    assert data["extra"]["collection_id"] == "450566"
    # no aggregate IIIF Collection was found -> single-manifest entry point
    assert "collection" not in data["extra"]


def test_service_size_detects_v3_via_context():
    v3 = {"@id": "x", "@context": "http://iiif.io/api/image/3/context.json", "profile": "level2"}
    assert _service_size(v3) == "max"
    v2 = {"@id": "x", "@context": "http://iiif.io/api/image/2/context.json"}
    assert _service_size(v2) == "full"


@pytest.mark.asyncio
async def test_search_normalizes_v2_manifest_with_v3_image_service():
    http = FakeHttp({MANIFEST_URL: MANIFEST})
    connector = IIIFConnector(_descriptor(), http)

    assets = await connector.search("", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "lehigh"
    assert asset.title == "Binding fragment, possibly a gloss"
    # first canvas image; v3 service -> "max" (the v2 "full" keyword 400s here)
    assert asset.image_url == f"{SERVICE_1}/full/max/0/default.jpg"
    assert asset.thumbnail_url == f"{SERVICE_1}/full/512,/0/default.jpg"
    assert asset.iiif_id == SERVICE_1
    # no descriptive metadata / rights on the manifest -> descriptor fallbacks
    assert asset.license == "varies"
    assert asset.page_url == MANIFEST_URL


@pytest.mark.asyncio
async def test_search_filters_by_query():
    http = FakeHttp({MANIFEST_URL: MANIFEST})
    connector = IIIFConnector(_descriptor(), http)

    assert await connector.search("nonexistentterm", limit=10) == []
    assert len(await connector.search("binding", limit=10)) == 1
