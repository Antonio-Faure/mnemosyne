"""National Library of Wales (LLGC) IIIF source — mocked end-to-end.

The DAMS at `damsssl.llgc.org.uk` serves per-object IIIF Presentation v2
manifests (`/iiif/2.0/<id>/manifest.json`) whose images come from the IIIF
Image API (`/iiif/2.0/image/<id>`, info.json confirmed). The host exposes no
aggregate IIIF entry point — probes for `collection.json`, `collections` and
`collection/<id>` all return 404 and no search endpoint is published — so the
descriptor points the generic `src/mnemosyne/sources/iiif.py` connector at a
single manifest via `extra.manifest` (as for albertina). No bespoke connector
is needed: the generic connector walks the v2
`sequences/canvases/images/resource` shape and normalizes the first canvas.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.iiif import IIIFConnector

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"
MANIFEST_URL = "https://damsssl.llgc.org.uk/iiif/2.0/4672201/manifest.json"
IMAGE_SERVICE = "https://damsssl.llgc.org.uk/iiif/2.0/image/4672201"

# Shape mirrors the live 4672201 manifest (v2 `sc:Manifest`, NLW/LLGC).
MANIFEST = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@type": "sc:Manifest",
    "@id": MANIFEST_URL,
    "label": (
        "Lieutenant General Sir William Fenwick Williams of Kars, Bart., K.C.B "
        "Commander of Her Majesty's Forces"
    ),
    "license": "http://creativecommons.org/publicdomain/mark/1.0/",
    "attribution": "Llyfrgell Genedlaethol Cymru – The National Library of Wales",
    "metadata": [
        {
            "label": [
                {"@value": "Title", "@language": "en"},
                {"@value": "Teitl", "@language": "cy-GB"},
            ],
            "value": "Lieutenant General Sir William Fenwick Williams of Kars",
        },
        {
            "label": [
                {"@value": "Author", "@language": "en"},
                {"@value": "Awdur", "@language": "cy-GB"},
            ],
            "value": "Graham, A. W.",
        },
        {
            "label": [
                {"@value": "Date", "@language": "en"},
                {"@value": "Dyddiad", "@language": "cy-GB"},
            ],
            "value": "1861",
        },
    ],
    "sequences": [
        {
            "@id": "https://damsssl.llgc.org.uk/iiif/2.0/4672201/sequence/Physical.json",
            "@type": "sc:Sequence",
            "canvases": [
                {
                    "@id": "https://damsssl.llgc.org.uk/iiif/2.0/4672201/canvas/1",
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
    return yaml.safe_load((SOURCES_DIR / "llgc.yaml").read_text(encoding="utf-8"))


def test_descriptor_is_keyless_iiif():
    data = _load()
    assert data["id"] == "llgc"
    assert data["protocol"] == "iiif"
    assert data["auth"] == "none"
    assert data["base_url"] == "https://damsssl.llgc.org.uk"
    assert data["extra"]["manifest"] == MANIFEST_URL
    # a stable object identifier is recorded for provenance
    assert data["extra"]["collection_id"]


def test_descriptor_uses_generic_iiif_connector():
    descriptor = SourceDescriptor(**_load())
    connector = build_connector(descriptor, FakeHttp({}))
    assert isinstance(connector, IIIFConnector)


@pytest.mark.asyncio
async def test_search_builds_asset_from_manifest():
    descriptor = SourceDescriptor(**_load())
    http = FakeHttp({MANIFEST_URL: MANIFEST})
    connector = build_connector(descriptor, http)

    assets = await connector.search("Kars", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "llgc"
    assert asset.title.startswith("Lieutenant General Sir William Fenwick Williams")
    assert asset.creator == "Graham, A. W."
    assert asset.year == 1861
    assert asset.license == "http://creativecommons.org/publicdomain/mark/1.0/"
    assert asset.image_url == f"{IMAGE_SERVICE}/full/full/0/default.jpg"
    assert asset.thumbnail_url == f"{IMAGE_SERVICE}/full/512,/0/default.jpg"


@pytest.mark.asyncio
async def test_search_filters_out_non_matching_query():
    descriptor = SourceDescriptor(**_load())
    http = FakeHttp({MANIFEST_URL: MANIFEST})
    connector = build_connector(descriptor, http)

    assert await connector.search("zzzznomatch", limit=10) == []
