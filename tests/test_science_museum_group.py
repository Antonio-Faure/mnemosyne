"""Science Museum Group connector: JSON:API search + IIIF manifest (no network)."""

from __future__ import annotations

from typing import Any

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.science_museum_group import ScienceMuseumGroupConnector

SEARCH: dict[str, Any] = {
    "data": [
        {
            "type": "objects",
            "id": "co6908",
            "attributes": {"summary_title": "Electrolysis jar"},
        },
        {"type": "people", "id": "cp123", "attributes": {}},  # not an object
        {
            "type": "objects",
            "id": "co9999",
            "attributes": {"summary_title": "Objet sans image"},
        },
        {"type": "objects", "id": "coerr", "attributes": {}},
        {
            "type": "objects",
            "id": "co1234567",
            "attributes": {"summary_title": "Citroen Traction Avant"},
        },
    ],
    "meta": {"count": 5},
}

MANIFEST_CO6908: dict[str, Any] = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@id": "https://collection.sciencemuseumgroup.org.uk/iiif/objects/co6908/manifest",
    "@type": "sc:Manifest",
    "label": "Electrolysis jar",
    "description": "Electrolysis jar",
    "attribution": "Science Museum Group",
    "metadata": [{"label": "Identifier", "value": "1982-1257"}],
    "thumbnail": {
        "@id": (
            "https://coimages.sciencemuseumgroup.org.uk/336/262/"
            "large_thumbnail_smg00175437.jpg"
        )
    },
    "sequences": [
        {
            "canvases": [
                {
                    "@id": "https://collection.sciencemuseumgroup.org.uk/iiif/"
                    "objects/co6908/canvas/0",
                    "height": 1416,
                    "width": 1536,
                    "images": [
                        {
                            "resource": {
                                "@id": (
                                    "https://zoom.sciencemuseumgroup.org.uk/iiif/3/"
                                    "336%2F262%2FElectrolysis_jar.ptif/full/max/0/"
                                    "default.jpg"
                                ),
                                "@type": "dctypes:Image",
                                "format": "image/jpeg",
                                "service": {
                                    "@id": (
                                        "https://zoom.sciencemuseumgroup.org.uk/"
                                        "iiif/3/336%2F262%2FElectrolysis_jar.ptif"
                                    ),
                                    "@context": "http://iiif.io/api/image/2/context.json",
                                    "profile": "http://iiif.io/api/image/2/level1.json",
                                },
                                "height": 1416,
                                "width": 1536,
                            }
                        }
                    ],
                }
            ]
        }
    ],
}

MANIFEST_TRACTION: dict[str, Any] = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@id": "https://collection.sciencemuseumgroup.org.uk/iiif/objects/co1234567/manifest",
    "@type": "sc:Manifest",
    "label": "Citroen Traction Avant motor car",
    "description": "Daily Herald press photograph of a Citroen Traction Avant.",
    "attribution": "Science Museum Group",
    "metadata": [
        {"label": "Identifier", "value": "1990-5036/12345"},
        {"label": "Date", "value": "1938"},
        {"label": "Maker", "value": "Daily Herald"},
    ],
    "sequences": [
        {
            "canvases": [
                {
                    "height": 2000,
                    "width": 3000,
                    "images": [
                        {
                            "resource": {
                                "@id": (
                                    "https://zoom.sciencemuseumgroup.org.uk/iiif/3/"
                                    "999%2F888%2Ftraction.ptif/full/max/0/default.jpg"
                                ),
                                "service": {
                                    "@id": (
                                        "https://zoom.sciencemuseumgroup.org.uk/"
                                        "iiif/3/999%2F888%2Ftraction.ptif"
                                    )
                                },
                                "height": 2000,
                                "width": 3000,
                            }
                        }
                    ],
                }
            ]
        }
    ],
}

MANIFESTS: dict[str, Any] = {
    "co6908": MANIFEST_CO6908,
    "co9999": {"sequences": []},  # no canvas -> skipped
    "coerr": ValueError("not json"),  # malformed -> skipped
    "co1234567": MANIFEST_TRACTION,
}


class FakeHttp:
    """Serves a canned search document and per-id manifests; records calls."""

    def __init__(self, search_payload: Any, manifests: dict[str, Any]):
        self.search_payload = search_payload
        self.manifests = manifests
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        if url.endswith("/search"):
            return self.search_payload
        for object_id, payload in self.manifests.items():
            if url.endswith(f"/iiif/objects/{object_id}"):
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise AssertionError(f"unexpected GET {url}")


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="science_museum_group",
        name="Science Museum Group Collection",
        protocol=Protocol.REST,
        base_url="https://collection.sciencemuseumgroup.org.uk",
        license="varies",
        rights="per item",
        seeds=["Citroen Traction Avant"],
    )


async def test_search_enriches_objects_from_their_manifest():
    http = FakeHttp(SEARCH, MANIFESTS)
    connector = ScienceMuseumGroupConnector(_descriptor(), http)

    assets = await connector.search("citroen traction avant", limit=10)

    # non-object (people) filtered, image-less and broken manifests skipped
    assert [a.source_asset_id for a in assets] == ["co6908", "co1234567"]

    first = assets[0]
    assert first.source_id == "science_museum_group"
    assert first.title == "Electrolysis jar"
    assert first.image_url == (
        "https://zoom.sciencemuseumgroup.org.uk/iiif/3/"
        "336%2F262%2FElectrolysis_jar.ptif/full/max/0/default.jpg"
    )
    assert first.iiif_id.endswith("Electrolysis_jar.ptif")
    assert first.thumbnail_url.endswith("large_thumbnail_smg00175437.jpg")
    assert first.width == 1536 and first.height == 1416
    assert first.page_url.endswith("/objects/co6908")
    assert first.rights == "Science Museum Group"
    assert first.extra["accession"] == "1982-1257"
    assert first.year is None  # no date on this record

    second = assets[1]
    assert second.title == "Citroen Traction Avant motor car"
    assert second.date_text == "1938"
    assert second.year == 1938
    assert second.creator == "Daily Herald"
    assert second.thumbnail_url == (
        "https://zoom.sciencemuseumgroup.org.uk/iiif/3/"
        "999%2F888%2Ftraction.ptif/full/400,/0/default.jpg"
    )
    assert second.extra["accession"] == "1990-5036/12345"


async def test_search_targets_search_endpoint_and_reads_manifest():
    http = FakeHttp(SEARCH, MANIFESTS)
    connector = ScienceMuseumGroupConnector(_descriptor(), http)

    await connector.search("citroen traction avant", limit=10)

    url, kwargs = http.calls[0]
    assert url == "https://collection.sciencemuseumgroup.org.uk/search"
    assert kwargs["params"]["q"] == "citroen traction avant"
    manifest_urls = [u for u, _ in http.calls if "/iiif/objects/" in u]
    assert (
        "https://collection.sciencemuseumgroup.org.uk/iiif/objects/co6908"
        in manifest_urls
    )


async def test_search_skips_objects_without_image():
    http = FakeHttp(
        {"data": [{"type": "objects", "id": "co9999"}]},
        MANIFESTS,
    )
    connector = ScienceMuseumGroupConnector(_descriptor(), http)

    assert await connector.search("anything") == []


async def test_search_zero_limit_makes_no_request():
    http = FakeHttp(SEARCH, MANIFESTS)
    connector = ScienceMuseumGroupConnector(_descriptor(), http)

    assert await connector.search("x", limit=0) == []
    assert http.calls == []
