"""Japan Search (ジャパンサーチ) jps-cross search: JSON parsing into canonical assets (offline)."""

from __future__ import annotations

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.japan_search import JapanSearchConnector

BASE = "https://jpsearch.go.jp/api"


class _Response:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def json(self) -> object:
        return self._payload


class FakeHttp:
    """Return queued payloads in order, recording every call."""

    def __init__(self, pages: list[object]) -> None:
        self._pages = list(pages)
        self.calls: list[tuple[str, dict]] = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        payload = self._pages.pop(0) if self._pages else {"hit": 0, "list": []}
        return _Response(payload)


def _common(**overrides) -> dict:
    base = {
        "id": "jp-1",
        "title": "Titre japonais",
        "titleEn": "English title",
        "contributor": ["Auteur A", "Auteur B", "Auteur C", "Auteur D"],
        "description": "Une description",
        "descriptionEn": "An English description",
        "temporal": ["1850", "1860"],
        "contentsType": "image",
        "contentsAccess": "internet",
        "contentsRightsType": "pdm",
        "contentsUrl": ["https://example.org/img.jpg"],
        "thumbnailUrl": ["https://example.org/thumb.jpg"],
        "linkUrl": "https://example.org/item",
        "providerUrl": "https://example.org/provider",
        "database": "国立国会図書館",
        "provider": "NDL",
        "ownerOrg": "National Diet Library",
    }
    base.update(overrides)
    return base


def _page(commons: list[dict], hit: int | None = None) -> dict:
    records = [{"id": c.get("id"), "common": c} for c in commons]
    return {"hit": hit if hit is not None else len(records), "from": 0, "list": records}


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="japan_search",
        name="Japan Search — ジャパンサーチ",
        protocol=Protocol.REST,
        base_url=BASE,
        auth="none",
        license="PDM-1.0 / CC0-1.0 / CC-BY-4.0",
    )


def _connector(pages: list[object]) -> tuple[JapanSearchConnector, FakeHttp]:
    http = FakeHttp(pages)
    return JapanSearchConnector(_descriptor(), http), http


@pytest.mark.asyncio
async def test_pdm_record_with_contents_url_yields_asset():
    connector, http = _connector([_page([_common()])])
    assets = await connector.search("浮世絵", limit=10)

    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "japan_search"
    assert asset.source_asset_id == "jp-1"
    assert asset.license == "PDM-1.0"
    assert asset.image_url == "https://example.org/img.jpg"
    assert asset.thumbnail_url == "https://example.org/thumb.jpg"
    assert asset.page_url == "https://example.org/item"
    assert "pdm" in asset.rights
    assert asset.extra["jpsearch_id"] == "jp-1"
    assert asset.extra["rights_code"] == "pdm"
    assert asset.extra["database"] == "国立国会図書館"
    assert asset.extra["contents_type"] == "image"


@pytest.mark.asyncio
async def test_cc0_record_maps_to_cc0_license():
    connector, _ = _connector([_page([_common(contentsRightsType="cc0")])])
    assets = await connector.search("写真", limit=10)
    assert len(assets) == 1
    assert assets[0].license == "CC0-1.0"


@pytest.mark.asyncio
async def test_cc_by_record_maps_to_cc_by_license():
    connector, _ = _connector([_page([_common(contentsRightsType="ccby")])])
    assets = await connector.search("地図", limit=10)
    assert len(assets) == 1
    assert assets[0].license == "CC-BY-4.0"


@pytest.mark.asyncio
async def test_restricted_rights_are_ignored():
    commons = [
        _common(id="r1", contentsRightsType="incr"),
        _common(id="r2", contentsRightsType="ccbync"),
        _common(id="r3", contentsRightsType="unknown"),
    ]
    connector, _ = _connector([_page(commons)])
    assert await connector.search("建築", limit=10) == []


@pytest.mark.asyncio
async def test_non_image_contents_type_is_ignored():
    connector, _ = _connector([_page([_common(contentsType="movie")])])
    assert await connector.search("自然", limit=10) == []


@pytest.mark.asyncio
async def test_restricted_access_is_ignored():
    connector, _ = _connector([_page([_common(contentsAccess="restricted")])])
    assert await connector.search("工場", limit=10) == []


@pytest.mark.asyncio
async def test_record_without_any_url_is_ignored():
    connector, _ = _connector([_page([_common(contentsUrl=[], thumbnailUrl=[])])])
    assert await connector.search("鉄道", limit=10) == []


@pytest.mark.asyncio
async def test_image_falls_back_to_thumbnail():
    connector, _ = _connector(
        [_page([_common(contentsUrl=[], thumbnailUrl=["https://example.org/only-thumb.jpg"])])]
    )
    assets = await connector.search("写真", limit=10)
    assert len(assets) == 1
    assert assets[0].image_url == "https://example.org/only-thumb.jpg"
    assert assets[0].thumbnail_url == "https://example.org/only-thumb.jpg"


@pytest.mark.asyncio
async def test_empty_response_returns_no_assets():
    connector, _ = _connector([{"hit": 0, "from": 0, "list": []}])
    assert await connector.search("rien", limit=10) == []


@pytest.mark.asyncio
async def test_limit_caps_number_of_assets():
    commons = [_common(id=f"jp-{i}") for i in range(5)]
    connector, _ = _connector([_page(commons)])
    assets = await connector.search("浮世絵", limit=2)
    assert len(assets) == 2


@pytest.mark.asyncio
async def test_duplicate_ids_are_deduplicated():
    commons = [_common(id="same"), _common(id="same")]
    connector, _ = _connector([_page(commons)])
    assets = await connector.search("浮世絵", limit=10)
    assert len(assets) == 1


@pytest.mark.asyncio
async def test_pagination_walks_to_the_next_page():
    page1 = _page([_common(id=f"a{i}") for i in range(4)], hit=25)
    page2 = _page([_common(id=f"b{i}") for i in range(4)], hit=25)
    connector, http = _connector([page1, page2])

    assets = await connector.search("地図", limit=5)

    assert len(assets) == 5
    assert len(http.calls) == 2
    first_from = dict(http.calls[0][1]["params"])["from"]
    second_from = dict(http.calls[1][1]["params"])["from"]
    assert first_from == "0"
    assert second_from == "10"  # page_size for limit=5 is 10


@pytest.mark.asyncio
async def test_title_creator_date_description_mapping():
    connector, _ = _connector([_page([_common()])])
    asset = (await connector.search("浮世絵", limit=10))[0]
    assert asset.title == "Titre japonais"
    assert asset.creator == "Auteur A, Auteur B, Auteur C"  # first three contributors
    assert asset.date_text == "1850, 1860"
    assert asset.year == 1850
    assert asset.description == "Une description"


@pytest.mark.asyncio
async def test_english_fallbacks_for_title_and_description():
    connector, _ = _connector([_page([_common(title="", description="")])])
    asset = (await connector.search("浮世絵", limit=10))[0]
    assert asset.title == "English title"
    assert asset.description == "An English description"


@pytest.mark.asyncio
async def test_page_url_fallback_to_jpsearch_item():
    connector, _ = _connector([_page([_common(linkUrl=None, providerUrl=None)])])
    asset = (await connector.search("浮世絵", limit=10))[0]
    assert asset.page_url == "https://jpsearch.go.jp/item/jp-1"


@pytest.mark.asyncio
async def test_request_params_carry_filters_and_repeated_rights():
    connector, http = _connector([_page([_common()])])
    await connector.search("蒸気機関", limit=10)

    url, kwargs = http.calls[0]
    assert url == "https://jpsearch.go.jp/api/item/search/jps-cross"
    params = kwargs["params"]
    pairs = list(params)

    assert ("keyword", "蒸気機関") in pairs
    assert ("f-contents", "image") in pairs
    assert ("f-caccess", "internet") in pairs
    rights = [v for (k, v) in pairs if k == "f-rights"]
    assert rights == ["+pdm", "+cc0", "+ccby"]
    sizes = [v for (k, v) in pairs if k == "size"]
    assert sizes == ["20"]  # min(max(10 * 2, 10), 100)
