import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources.iiif import IIIFConnector

COL = "https://host/c/collection"
M1 = "https://host/c/m1/manifest"
M2 = "https://host/c/m2/manifest"

COLLECTION = {
    "type": "Collection",
    "items": [
        {"id": M1, "type": "Manifest"},
        {"id": M2, "type": "Manifest"},
    ],
}

MANIFEST_V3 = {
    "id": M1,
    "type": "Manifest",
    "label": {"fr": ["Usine de Lacq en 1950"]},
    "metadata": [{"label": {"fr": ["Date"]}, "value": {"fr": ["1950"]}}],
    "rights": "http://creativecommons.org/publicdomain/mark/1.0/",
    "items": [
        {
            "type": "Canvas",
            "items": [
                {
                    "type": "AnnotationPage",
                    "items": [
                        {
                            "type": "Annotation",
                            "body": {
                                "id": "https://host/img/1.jpg",
                                "type": "Image",
                                "service": [
                                    {"id": "https://host/iiif/m1", "type": "ImageService3"}
                                ],
                            },
                        }
                    ],
                }
            ],
        }
    ],
}

MANIFEST_V2 = {
    "@id": M2,
    "@type": "sc:Manifest",
    "label": "Paysage industriel",
    "sequences": [
        {
            "canvases": [
                {
                    "images": [
                        {
                            "resource": {
                                "@id": "https://host/img/2.jpg",
                                "service": {"@id": "https://host/iiif/m2"},
                            }
                        }
                    ]
                }
            ]
        }
    ],
}


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes

    async def get_json(self, url, **kwargs):
        return self.routes[url]


def _descriptor(extra) -> SourceDescriptor:
    return SourceDescriptor(
        id="discovered_host",
        name="Host",
        protocol=Protocol.IIIF,
        base_url="https://host/",
        auth="none",
        extra=extra,
    )


def test_build_connector_falls_back_to_protocol():
    connector = build_connector(_descriptor({"collection": COL}), FakeHttp({}))
    assert isinstance(connector, IIIFConnector)


@pytest.mark.asyncio
async def test_search_filters_by_query_and_builds_assets():
    http = FakeHttp({COL: COLLECTION, M1: MANIFEST_V3, M2: MANIFEST_V2})
    connector = IIIFConnector(_descriptor({"collection": COL}), http)

    assets = await connector.search("usine", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.title == "Usine de Lacq en 1950"
    assert asset.year == 1950
    assert asset.image_url == "https://host/iiif/m1/full/full/0/default.jpg"
    assert asset.thumbnail_url == "https://host/iiif/m1/full/512,/0/default.jpg"
    assert asset.page_url == M1
    assert asset.license.startswith("http://creativecommons.org")


@pytest.mark.asyncio
async def test_search_without_query_returns_all():
    http = FakeHttp({COL: COLLECTION, M1: MANIFEST_V3, M2: MANIFEST_V2})
    connector = IIIFConnector(_descriptor({"collection": COL}), http)
    assets = await connector.search("", limit=10)
    assert len(assets) == 2


@pytest.mark.asyncio
async def test_single_manifest_entry_point():
    http = FakeHttp({M1: MANIFEST_V3})
    connector = IIIFConnector(_descriptor({"manifest": M1}), http)
    assets = await connector.search("")
    assert len(assets) == 1
    assert assets[0].source_asset_id == M1


@pytest.mark.asyncio
async def test_no_entry_point_returns_empty():
    connector = IIIFConnector(_descriptor({}), FakeHttp({}))
    assert await connector.search("x") == []
