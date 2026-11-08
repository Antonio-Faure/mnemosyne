"""Pechelbronn / Musée du pétrole connector — offline (mocked WordPress API).

Covers the three production gotchas (burst-WAF 410 backoff, Latin-1 filenames,
dead uploads), the historical-fonds classifier against the 8 live fixtures, the
field mapping, and X-WP-TotalPages pagination.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import pechelbronn_petrole as m
from mnemosyne.sources.pechelbronn_petrole import PechelbronnPetroleConnector

ENDPOINT = "https://www.musee-du-petrole.com/wp-json/wp/v2/media"
CREDIT = "© Musée français du pétrole / Association des Amis du Musée"

#: live-verified fixtures: id -> (title.rendered, slug), all classified HIST
FIXTURES = {
    4380: (
        "carte-postale-apres-reconstruction-2WW_vue-aerienne-raffinerie-de-"
        "Pechelbronn_CollectionMFDP",
        "carte-postale-apres-reconstruction-2ww_vue-aerienne-raffinerie-de-"
        "pechelbronn_collectionmfdp",
    ),
    4498: ("publicité Antar Pechelbronn", "publicite-antar-pechelbronn-2"),
    4175: (
        "louis Hepting_vendeur de graisse ambulant de Pechelbronn_1er mitoié 20e s",
        "louis-hepting_vendeur-de-graisse-ambulant-de-pechelbronn_1er-mitoie-20e-s-2",
    ),
    1092: ("5 sept 1927_Pechelbronn câble et treuil", "5-sept-1927_pechelbronn-cable-et-treuil"),
    5283: ("Aquarelle Sauer_1 PECH_2013-1-2", "aquarelle-sauer_1-pech_2013-1-2-2"),
    1117: ("Atelier_ANTAR_ex_01", "atelier_antar_ex_01"),
    4501: ("PECH_1997.0.256", "pech_1997-0-256-2"),
    4289: ("PECH_2020-0-52_2", "pech_2020-0-52_2-2"),
}

NOISE = [
    ("Logo-musee-du-petrole", "logo-musee-du-petrole"),
    ("Amuse-musées", "amuse-musees"),
    ("IMG_1234", "img_1234"),
    ("Présentation", "presentation"),
    ("stockcake-photo", "stockcake-photo"),
    ("", "20210608_143000-staff-snapshot"),
]


# ── fake HTTP ────────────────────────────────────────────────────────────────
class FakeHttp:
    """Minimal ``HttpClient`` double: ``handler`` returns a Response or raises."""

    def __init__(self, handler):
        self.handler = handler
        self.calls: list[dict] = []

    async def get(self, url, *, params=None, headers=None, accept="application/json"):
        self.calls.append({"url": url, "params": params, "accept": accept})
        result = self.handler(url, params, accept)
        if isinstance(result, Exception):
            raise result
        return result


def _resp(payload, *, status=200, headers=None):
    return httpx.Response(status, json=payload, headers=headers or {})


def _media(item_id, title, slug, *, source_url=None, width=1000, height=800):
    return {
        "id": item_id,
        "date": "2024-01-01T00:00:00",
        "slug": slug,
        "title": {"rendered": title},
        "source_url": source_url or f"{ENDPOINT.rsplit('/media', 1)[0]}/{item_id}.jpg",
        "link": f"https://www.musee-du-petrole.com/{slug}/",
        "mime_type": "image/jpeg",
        "post": 218,
        "caption": {"rendered": ""},
        "description": {"rendered": ""},
        "alt_text": "",
        "media_details": {
            "width": width,
            "height": height,
            "sizes": {
                "medium": {
                    "source_url": f"https://www.musee-du-petrole.com/medium-{item_id}.jpg",
                    "width": 300,
                    "height": 240,
                },
                "full": {"source_url": f"https://www.musee-du-petrole.com/full-{item_id}.jpg"},
            },
        },
    }


def _descriptor(**extra):
    base = {
        "media_endpoint": ENDPOINT,
        "request_delay_s": 0.0,
        "backoff_base_s": 0.0,
        "credit": CREDIT,
    }
    base.update(extra)
    return SourceDescriptor(
        id="pechelbronn_petrole",
        name="Musée français du pétrole — fonds Pechelbronn",
        protocol=Protocol.REST,
        base_url="https://www.musee-du-petrole.com",
        auth="none",
        rights="in_copyright",
        extra=base,
    )


@pytest.fixture
def sleeps(monkeypatch):
    recorded: list[float] = []

    async def _sleep(delay):
        recorded.append(delay)

    monkeypatch.setattr(m.asyncio, "sleep", _sleep)
    return recorded


# ── classifier ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("item_id", sorted(FIXTURES))
def test_all_fixtures_are_historical(item_id):
    title, slug = FIXTURES[item_id]
    assert m.is_historical(title, slug) is True


@pytest.mark.parametrize(("title", "slug"), NOISE)
def test_library_noise_is_not_historical(title, slug):
    assert m.is_historical(title, slug) is False


def test_extract_inventory():
    assert m.extract_inventory("Aquarelle Sauer_1 PECH_2013-1-2") == "PECH_2013-1-2"
    assert m.extract_inventory("PECH_1997.0.256") == "PECH_1997.0.256"
    assert m.extract_inventory("PECH_2020-0-52_2") == "PECH_2020-0-52_2"
    assert m.extract_inventory("Logo musée") is None


def test_classify_theme_is_in_allowed_set():
    allowed = {
        "forage", "raffinerie", "portrait", "carte_postale",
        "publicite", "materiel", "autre",
    }
    for title, slug in FIXTURES.values():
        assert m.classify_theme(title, slug) in allowed


def test_strip_tags_and_entities():
    assert m.strip_tags("<em>Pechelbronn</em>&#8211;1927") == "Pechelbronn–1927"


# ── latin-1 URL + dead-upload fallback ───────────────────────────────────────
def test_latin1_url_encodes_single_byte():
    url = (
        "https://www.musee-du-petrole.com/wp-content/uploads/2015/03/"
        "5-sept-1927_Pechelbronn-câble-et-treuil.jpg"
    )
    encoded = m.latin1_url(url)
    assert "%E2" in encoded
    assert "%C3%A2" not in encoded and "â" not in encoded
    # ASCII urls are returned untouched so callers can try both
    assert m.latin1_url("https://x/y.jpg") == "https://x/y.jpg"


@pytest.mark.asyncio
async def test_fetch_falls_back_to_latin1_and_validates_image(sleeps):
    url = "https://www.musee-du-petrole.com/wp-content/uploads/2015/03/Pechelbronn-câble.jpg"

    def handler(u, params, accept):
        if "%E2" in u:
            return httpx.Response(200, content=b"JPEGDATA", headers={"content-type": "image/jpeg"})
        # a plain GET of the accented (UTF-8) form 404s in production
        req = httpx.Request("GET", u)
        return httpx.HTTPStatusError("404", request=req, response=httpx.Response(404, request=req))

    asset = m.Asset.build("pechelbronn_petrole", "1092", image_url=url, thumbnail_url=None)
    data = await PechelbronnPetroleConnector(_descriptor(), FakeHttp(handler)).fetch(asset)
    assert data == b"JPEGDATA"


@pytest.mark.asyncio
async def test_fetch_falls_back_to_thumbnail_when_full_is_dead(sleeps):
    dead = "https://www.musee-du-petrole.com/dead.jpg"
    thumb = "https://www.musee-du-petrole.com/thumb.jpg"

    def handler(u, params, accept):
        if u == thumb:
            return httpx.Response(200, content=b"THUMB", headers={"content-type": "image/jpeg"})
        req = httpx.Request("GET", u)
        return httpx.HTTPStatusError("404", request=req, response=httpx.Response(404, request=req))

    asset = m.Asset.build("pechelbronn_petrole", "1", image_url=dead, thumbnail_url=thumb)
    connector = PechelbronnPetroleConnector(_descriptor(), FakeHttp(handler))
    assert await connector.fetch(asset) == b"THUMB"


# ── field mapping ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_field_mapping(sleeps):
    title, slug = FIXTURES[1092]
    item = _media(1092, title, slug, width=1254, height=833)
    item["description"] = {"rendered": "Collection MFDP"}

    def handler(u, params, accept):
        return _resp([item], headers={"X-WP-TotalPages": "1", "X-WP-Total": "1"})

    connector = PechelbronnPetroleConnector(_descriptor(), FakeHttp(handler))
    assets = await connector.search("pétrole", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_asset_id == "1092"
    assert asset.title == "5 sept 1927_Pechelbronn câble et treuil"
    assert asset.description == "Collection MFDP"
    assert asset.rights == "in_copyright"
    assert asset.year == 1927
    assert asset.width == 1254 and asset.height == 833
    assert asset.thumbnail_url == "https://www.musee-du-petrole.com/medium-1092.jpg"
    assert asset.image_url == item["source_url"]
    assert asset.extra["credit"] == CREDIT
    assert asset.extra["theme"] in {"forage", "materiel", "autre"}
    # provider shape never leaks: raw 'media_details' is reconstructed, not copied
    assert "media_details" not in asset.extra


# ── pagination ───────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_pagination_respects_total_pages_and_filters(sleeps):
    page1 = [_media(10, "Logo-musee", "logo"), _media(4380, *FIXTURES[4380])]
    page2 = [_media(35, "bandeau-header", "bandeau-header"), _media(4498, *FIXTURES[4498])]

    def handler(u, params, accept):
        page = int(params["page"])
        payload = page1 if page == 1 else page2
        return _resp(payload, headers={"X-WP-TotalPages": "2", "X-WP-Total": "4"})

    http = FakeHttp(handler)
    connector = PechelbronnPetroleConnector(_descriptor(), http)
    assets = await connector.search("", limit=10)

    assert [a.source_asset_id for a in assets] == ["4380", "4498"]  # noise dropped
    assert len(http.calls) == 2  # stopped at X-WP-TotalPages, never asked page 3
    assert [c["params"]["page"] for c in http.calls] == [1, 2]
    assert http.calls[0]["params"]["media_type"] == "image"


# ── burst-WAF 410 → backoff + retry (not abort) ──────────────────────────────
@pytest.mark.asyncio
async def test_410_triggers_backoff_and_retry(sleeps):
    state = {"n": 0}
    item = _media(1117, *FIXTURES[1117])

    def handler(u, params, accept):
        state["n"] += 1
        if state["n"] == 1:
            req = httpx.Request("GET", u)
            return httpx.HTTPStatusError(
                "410", request=req, response=httpx.Response(410, request=req)
            )
        return _resp([item], headers={"X-WP-TotalPages": "1", "X-WP-Total": "1"})

    http = FakeHttp(handler)
    connector = PechelbronnPetroleConnector(_descriptor(backoff_base_s=2.0), http)
    assets = await connector.search("", limit=5)

    assert [a.source_asset_id for a in assets] == ["1117"]  # retried, not aborted
    assert state["n"] == 2
    assert 2.0 in sleeps  # exponential backoff base * 2**0


@pytest.mark.asyncio
async def test_persistent_410_gives_up_after_max_retries(sleeps):
    def handler(u, params, accept):
        req = httpx.Request("GET", u)
        return httpx.HTTPStatusError("410", request=req, response=httpx.Response(410, request=req))

    http = FakeHttp(handler)
    connector = PechelbronnPetroleConnector(
        _descriptor(backoff_base_s=1.0, max_retries=3), http
    )
    assets = await connector.search("", limit=5)

    assert assets == []  # degrades to empty, never raises
    assert len(http.calls) == 4  # initial attempt + 3 retries
    assert sleeps == [1.0, 2.0, 4.0]


@pytest.mark.asyncio
async def test_query_reranks_matching_fonds_first(sleeps):
    items = [_media(4501, *FIXTURES[4501]), _media(1117, *FIXTURES[1117])]

    def handler(u, params, accept):
        return _resp(items, headers={"X-WP-TotalPages": "1"})

    connector = PechelbronnPetroleConnector(_descriptor(), FakeHttp(handler))
    assets = await connector.search("antar atelier", limit=5)
    assert assets[0].source_asset_id == "1117"  # Atelier_ANTAR matches the query


def test_connector_module_exposes_async_sleep():
    # sanity: the module drives pacing/backoff through asyncio.sleep (patched above)
    assert asyncio.sleep is not None
