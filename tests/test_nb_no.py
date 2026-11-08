"""National Library of Norway catalog search → open IIIF assets (offline)."""

from __future__ import annotations

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.nb_no import NbNoConnector

BASE = "https://api.nb.no/catalog/v1"
IMAGE = "https://www.nb.no/services/image/resolver/URN:NBN:no-nb_{nb}/full/full/0/native.jpg"


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="nb_no",
        name="National Library of Norway — Nasjonalbiblioteket",
        protocol=Protocol.REST,
        base_url=BASE,
        auth="none",
        license="PDM-1.0",
    )


def _manifest_url(nb_id: str) -> str:
    return f"{BASE}/iiif/{nb_id}/manifest"


def _image(nb_id: str, index: int = 0) -> str:
    return IMAGE.format(nb=nb_id) if index == 0 else IMAGE.format(nb=f"{nb_id}_{index}")


def _item(
    nb_id: str = "abc123",
    *,
    public: bool = True,
    digital: bool = True,
    viewability: str = "ALL",
    license: str = "publicdomain",
    title: str | None = "Dampskip.",
    creators: tuple[str, ...] = ("Mittet & Co. AS",),
    issued: str | None = "1900",
    publisher: str | None = "Norsk folkemuseum",
    media_types: tuple[str, ...] = ("bilder",),
    with_manifest: bool = True,
) -> dict:
    links: dict = {}
    if with_manifest:
        links["presentation"] = {"href": _manifest_url(nb_id)}
    return {
        "id": nb_id,
        "_links": links,
        "accessInfo": {
            "isDigital": digital,
            "isPublicDomain": public,
            "license": license,
            "viewability": viewability,
        },
        "metadata": {
            "title": title,
            "creators": list(creators),
            "mediaTypes": list(media_types),
            "languages": [{"code": "nob"}],
            "originInfo": {"issued": issued, "publisher": publisher},
            "subject": {"geographics": ["Norge"]},
        },
    }


def _manifest(
    image_urls: list[str],
    *,
    thumbnail: object = None,
    without_canvases: bool = False,
) -> dict:
    canvases = [
        {
            "@type": "sc:Canvas",
            "width": 7627,
            "height": 5657,
            "images": [{"resource": {"@id": url, "format": "image/jpeg"}}],
        }
        for url in image_urls
    ]
    manifest: dict = {
        "@type": "sc:Manifest",
        "sequences": [] if without_canvases else [{"canvases": canvases}],
    }
    if thumbnail is not None:
        manifest["thumbnail"] = thumbnail
    return manifest


def _page(number: int, items: list[dict], total_pages: int = 1) -> dict:
    return {
        "page": {
            "number": number,
            "size": 20,
            "totalElements": len(items),
            "totalPages": total_pages,
        },
        "_embedded": {"items": items},
    }


class FakeHttp:
    def __init__(self, pages: dict | None = None, manifests: dict | None = None) -> None:
        self.pages = pages or {}
        self.manifests = manifests or {}
        self.calls: list[tuple[str, dict]] = []

    async def get_json(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/items"):
            page = int((kwargs.get("params") or {}).get("page", 0))
            return self.pages.get(page, _page(page, []))
        return self.manifests.get(url, {})

    def manifest_calls(self) -> list[str]:
        return [url for url, _ in self.calls if not url.endswith("/items")]

    def requested_pages(self) -> list[int]:
        return sorted(
            int((kwargs.get("params") or {}).get("page", 0))
            for url, kwargs in self.calls
            if url.endswith("/items")
        )


@pytest.mark.asyncio
async def test_public_domain_item_maps_to_asset():
    img = _image("id1")
    http = FakeHttp(
        pages={0: _page(0, [_item(nb_id="id1")])},
        manifests={
            _manifest_url("id1"): _manifest(
                [img], thumbnail={"@id": "https://www.nb.no/thumb/id1.jpg"}
            )
        },
    )
    connector = NbNoConnector(_descriptor(), http)

    assets = await connector.search("dampskip", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.title == "Dampskip."
    assert asset.creator == "Mittet & Co. AS"
    assert asset.date_text == "1900"
    assert asset.year == 1900
    assert asset.license == "PDM-1.0"
    assert asset.rights == "Public domain — National Library of Norway"
    assert asset.page_url == "https://www.nb.no/items/id1"
    assert asset.image_url == img
    assert asset.thumbnail_url == "https://www.nb.no/thumb/id1.jpg"
    assert asset.extra["nb_id"] == "id1"
    assert asset.extra["mediatype"] == "bilder"
    assert asset.extra["language"] == "nob"
    assert asset.extra["publisher"] == "Norsk folkemuseum"
    assert asset.extra["nb_license"] == "publicdomain"
    assert asset.extra["viewability"] == "ALL"

    params = http.calls[0][1]["params"]
    assert params["q"] == "dampskip"
    assert params["page"] == "0"
    assert int(params["size"]) == 50  # min(max(10*5, 20), 100)


@pytest.mark.asyncio
async def test_copyrighted_item_is_ignored():
    http = FakeHttp(pages={0: _page(0, [_item(nb_id="copy", public=False)])})
    connector = NbNoConnector(_descriptor(), http)
    assert await connector.search("x", limit=10) == []
    assert http.manifest_calls() == []


@pytest.mark.asyncio
async def test_non_digital_item_is_ignored():
    http = FakeHttp(pages={0: _page(0, [_item(nb_id="nodig", digital=False)])})
    connector = NbNoConnector(_descriptor(), http)
    assert await connector.search("x", limit=10) == []
    assert http.manifest_calls() == []


@pytest.mark.asyncio
async def test_manifest_without_canvas_is_ignored():
    http = FakeHttp(
        pages={0: _page(0, [_item(nb_id="empty")])},
        manifests={_manifest_url("empty"): _manifest([], without_canvases=True)},
    )
    connector = NbNoConnector(_descriptor(), http)
    assert await connector.search("x", limit=10) == []
    # the manifest *was* fetched, it just had no canvas
    assert http.manifest_calls() == [_manifest_url("empty")]


@pytest.mark.asyncio
async def test_thumbnail_defaults_to_image():
    img = _image("nothumb")
    http = FakeHttp(
        pages={0: _page(0, [_item(nb_id="nothumb")])},
        manifests={_manifest_url("nothumb"): _manifest([img])},
    )
    connector = NbNoConnector(_descriptor(), http)
    asset = (await connector.search("x", limit=5))[0]
    assert asset.image_url == img
    assert asset.thumbnail_url == img


@pytest.mark.asyncio
async def test_first_canvas_of_multicanvas_book():
    first, second = _image("book", 0), _image("book", 1)
    http = FakeHttp(
        pages={0: _page(0, [_item(nb_id="book")])},
        manifests={_manifest_url("book"): _manifest([first, second])},
    )
    connector = NbNoConnector(_descriptor(), http)
    asset = (await connector.search("bok", limit=5))[0]
    assert asset.image_url == first  # first page only


@pytest.mark.asyncio
async def test_empty_response_returns_empty():
    connector = NbNoConnector(_descriptor(), FakeHttp(pages={0: _page(0, [])}))
    assert await connector.search("x") == []


@pytest.mark.asyncio
async def test_limit_is_respected_and_stops_fetching():
    items = [_item(nb_id=f"id{i}") for i in range(3)]
    manifests = {_manifest_url(f"id{i}"): _manifest([_image(f"id{i}")]) for i in range(3)}
    http = FakeHttp(pages={0: _page(0, items)}, manifests=manifests)
    connector = NbNoConnector(_descriptor(), http)

    assets = await connector.search("x", limit=1)
    assert len(assets) == 1
    # stopped after the first asset: only one manifest was fetched
    assert len(http.manifest_calls()) == 1


@pytest.mark.asyncio
async def test_pagination_continues_from_page_0_to_1():
    http = FakeHttp(
        pages={
            0: _page(0, [_item(nb_id="closed", public=False)], total_pages=2),
            1: _page(1, [_item(nb_id="open")], total_pages=2),
        },
        manifests={_manifest_url("open"): _manifest([_image("open")])},
    )
    connector = NbNoConnector(_descriptor(), http)

    assets = await connector.search("x", limit=5)
    assert [a.source_asset_id for a in assets] == ["open"]
    assert http.requested_pages() == [0, 1]


@pytest.mark.asyncio
async def test_mapping_joins_first_three_creators_and_cc0_license():
    item = _item(
        nb_id="cc0",
        license="cc0",
        creators=("A", "B", "C", "D"),
        issued="1950",
    )
    http = FakeHttp(
        pages={0: _page(0, [item])},
        manifests={_manifest_url("cc0"): _manifest([_image("cc0")])},
    )
    connector = NbNoConnector(_descriptor(), http)
    asset = (await connector.search("x", limit=5))[0]
    assert asset.creator == "A, B, C"  # first three joined
    assert asset.date_text == "1950"
    assert asset.year == 1950
    assert asset.license == "CC0-1.0"


@pytest.mark.asyncio
async def test_title_defaults_to_id_when_missing():
    item = _item(nb_id="notitle", title="")
    http = FakeHttp(
        pages={0: _page(0, [item])},
        manifests={_manifest_url("notitle"): _manifest([_image("notitle")])},
    )
    connector = NbNoConnector(_descriptor(), http)
    asset = (await connector.search("x", limit=5))[0]
    assert asset.title == "National Library of Norway notitle"


@pytest.mark.asyncio
async def test_no_manifest_request_for_closed_item():
    http = FakeHttp(pages={0: _page(0, [_item(nb_id="closed2", digital=False)])})
    connector = NbNoConnector(_descriptor(), http)
    await connector.search("x", limit=5)
    assert http.manifest_calls() == []
