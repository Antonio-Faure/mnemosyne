"""Archives de Paris — public Arkothèque JSON search + IIIF normalisation (offline)."""

from __future__ import annotations

import pytest

from mnemosyne.models import Asset, Protocol, SourceDescriptor
from mnemosyne.sources.archives_paris import ArchivesParisConnector

BASE = "https://archives.paris.fr"

SEARCH_PAYLOAD = {
    "total": 1,
    "results": [
        {"id": 2551724, "intitule": "11Fi 418", "refUnique": "arko_fiche_test1"},
    ],
}

# Trimmed render-fiche html: an <img> carrying the image id + a few data-champ
# fields and a <dt>/<dd> author, as the public endpoint returns them.
DETAIL_HTML = (
    '<div class="image_detail">'
    '<img src="https://archives.paris.fr/_recherche-images/show/2551724/image/'
    '11590576/0?size=!400,400" />'
    '<div data-champ="titre">Quai de Grenelle</div>'
    '<div data-champ="datation">1905</div>'
    '<div data-champ="cote">11Fi 418</div>'
    '<div data-champ="lieu_administratif">15e arrondissement</div>'
    "<dl><dt>Auteur</dt><dd>Anonyme</dd></dl>"
    "</div>"
)


class _Response:
    def __init__(self, payload: object | None) -> None:
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


class FakeHttp:
    def __init__(
        self,
        search_payload: object | None,
        detail_by_ref: dict[str, object] | None = None,
    ) -> None:
        self.search_payload = search_payload
        self.detail_by_ref = detail_by_ref or {}
        self.calls: list[tuple[str, dict]] = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if "search-simple" in url:
            return _Response(self.search_payload)
        for ref_unique, payload in self.detail_by_ref.items():
            if ref_unique in url:
                return _Response(payload)
        return _Response({})


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="archives_paris",
        name="Archives de Paris — fonds photographiques",
        protocol=Protocol.REST,
        base_url=BASE,
        auth="none",
        license="varies",
        rights="Archives de Paris",
    )


def _params_of(http: FakeHttp) -> dict[str, str]:
    pairs = http.calls[0][1]["params"]
    return {key: value for key, value in pairs}


@pytest.mark.asyncio
async def test_search_normalises_a_record_into_an_asset():
    http = FakeHttp(
        SEARCH_PAYLOAD,
        {"arko_fiche_test1": {"html": DETAIL_HTML}},
    )
    connector = ArchivesParisConnector(_descriptor(), http)

    assets = await connector.search("Grenelle", limit=10)

    assert len(assets) == 1
    asset = assets[0]
    assert isinstance(asset, Asset)
    assert asset.source_id == "archives_paris"
    assert asset.source_asset_id == "2551724"
    assert asset.title == "Quai de Grenelle"
    assert asset.creator == "Anonyme"
    assert asset.date_text == "1905"
    assert asset.year == 1905
    assert asset.rights == "Archives de Paris"  # descriptor fallback
    assert asset.license == "varies"
    assert asset.extra["cote"] == "11Fi 418"
    assert asset.extra["lieu"] == "15e arrondissement"

    image_base = f"{BASE}/_recherche-images/show/2551724/image/11590576/0"
    assert asset.iiif_id == image_base
    assert asset.image_url == f"{image_base}/full/!800,800/0/default.jpg"
    assert asset.thumbnail_url == f"{image_base}/full/!400,400/0/default.jpg"
    assert asset.page_url == (
        f"{BASE}/rechercher-dans-les-collections-photographiques?detail=2551724"
    )

    # Search uses the public JSON endpoint with the free-text facet query.
    search_url = http.calls[0][0]
    assert search_url.endswith("/_recherche-api/search-simple/41")
    params = _params_of(http)
    assert "Grenelle" in params.values()
    assert params["arko_default_67d426d4c0eab--searchMode"] == "strict"


@pytest.mark.asyncio
async def test_record_without_image_is_skipped():
    http = FakeHttp(
        SEARCH_PAYLOAD,
        {"arko_fiche_test1": {"html": "<div>no image here</div>"}},
    )
    connector = ArchivesParisConnector(_descriptor(), http)
    assert await connector.search("Grenelle") == []


@pytest.mark.asyncio
async def test_malformed_search_json_returns_empty():
    connector = ArchivesParisConnector(_descriptor(), FakeHttp(None))
    assert await connector.search("Grenelle") == []


@pytest.mark.asyncio
async def test_record_without_refunique_is_skipped():
    payload = {"total": 1, "results": [{"id": 1, "intitule": "11Fi 1"}]}
    connector = ArchivesParisConnector(_descriptor(), FakeHttp(payload))
    assert await connector.search("Grenelle") == []


@pytest.mark.asyncio
async def test_blank_query_short_circuits_without_network():
    http = FakeHttp(SEARCH_PAYLOAD)
    connector = ArchivesParisConnector(_descriptor(), http)
    assert await connector.search("   ") == []
    assert http.calls == []
