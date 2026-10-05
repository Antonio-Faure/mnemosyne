"""Archives départementales du Nord connector: normalization + parsing (offline).

No network: the HTTP transport is faked. Fixtures mirror the live shapes:

* (a) a ``/search/results`` HTML page with one notice-with-images + one PDF,
* (b) a ``group`` response ``{"counts": {"media": N, ...}, "media": [...]}``,
* (c) a ``range`` response = a JSON array of Media (``end`` inclusive),
* (d) a ``uuid`` response carrying ``app.licenses.visualizer``,
* (e) the API's HTTP 400 ("Unable to handle this request") when ``end`` is out
  of range — the connector must clamp so it never happens.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import CONNECTORS, build_connector
from mnemosyne.sources.archives_nord import ArchivesNordConnector

BASE = "https://archivesdepartementales.lenord.fr"
ARK = "j0h8xbmd3tkn"
UUID1 = "284c50a2-dd55-417e-8a09-980bdab78f80"
UUID2 = "9dd518e4-b529-4239-9400-4d7f84692340"
PDF_UUID = "11111111-2222-3333-4444-555555555555"

SOURCES_DIR = Path(__file__).resolve().parents[1] / "config" / "sources"


def _media(uuid: str) -> dict[str, Any]:
    return {
        "url": f"{BASE}/ark:/33518/{ARK}/{uuid}",
        "record": {
            "arkId": {"arkName": ARK, "naan": 33518},
            "url": f"{BASE}/ark:/33518/{ARK}",
            "title": ["DOUCHY-LES-MINES"],
            "referenceCode": ["M 474 / 177"],
            "description": None,
            "period": {"boundaries": ["1906-01-01", "1906-12-31"], "certainty": None},
            "locationKeywords": ["DOUCHY-LES-MINES"],
        },
        "uuid": uuid,
        "location": {
            "original": f"{BASE}/images/{uuid}.jpg",
            "thumb": f"{BASE}/images/{uuid}_thumbnail.jpg",
            "iiif": None,
        },
        "type": "image",
        "format": "jpg",
        "title": None,
    }


SEARCH_HTML = f"""
<!DOCTYPE html><html><head><title>mines - page 1 sur 14 - Recherche</title></head>
<body>
  <p class="nb-results">264 résultats</p>
  <ul class="results">
    <li class="element-list">
      <a href="/ark:/33518/{ARK}/{UUID1}"><img src="/images/{UUID1}_thumbnail.jpg"></a>
      <h2>DOUCHY-LES-MINES</h2>
      <div class="info-list-picture">107 medias</div>
    </li>
    <li class="element-list">
      <a href="/media/{PDF_UUID}.pdf">
        <img src="/pdf-preview/{PDF_UUID}_search_result_thumbnail">
      </a>
      <h2>Plan des travaux de la fosse</h2>
      <div class="info-list-picture">Document PDF (12 pages)</div>
    </li>
  </ul>
</body></html>
"""

DETAIL: dict[str, Any] = {
    "counts": {"media": 2, "group": 1},
    "positions": {"media": 0, "group": 0},
    "group": {"title": None},
    "media": [_media(UUID1), _media(UUID2)],
    "app": {
        "licenses": {
            "visualizer": {
                "uuid": "b6bad2e5-96d0-4166-ae0b-f01ebe0ab972",
                "label": "Réutilisation des informations publiques",
                "text": "La réutilisation commerciale des numérisations est soumise "
                "au paiement d'une redevance et à une licence écrite.",
            }
        }
    },
}


class _FakeResponse:
    def __init__(self, *, text: str = "", json_data: Any = None):
        self.text = text
        self._json = json_data

    def json(self) -> Any:
        return self._json


def _bad_request() -> httpx.HTTPStatusError:
    request = httpx.Request("GET", f"{BASE}/visualizer/api")
    response = httpx.Response(400, text="Unable to handle this request", request=request)
    return httpx.HTTPStatusError("400 Bad Request", request=request, response=response)


class FakeHttp:
    """Canned transport. Range requests with ``end >= N`` raise HTTP 400."""

    def __init__(self, media_list: list[dict[str, Any]], first_page_size: int | None = None):
        self.media_list = media_list
        self.first_page_size = len(media_list) if first_page_size is None else first_page_size
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        accept: str = "application/json",
    ) -> _FakeResponse:
        params = dict(params or {})
        self.calls.append((url, params))
        if "search/results" in url:
            return _FakeResponse(text=SEARCH_HTML)
        if "visualizer/api" in url:
            if "uuid" in params:
                return _FakeResponse(json_data=DETAIL)
            if "start" in params or "end" in params:
                start = int(params["start"])
                end = int(params["end"])
                if end >= len(self.media_list):
                    raise _bad_request()
                return _FakeResponse(json_data=self.media_list[start : end + 1])
            return _FakeResponse(
                json_data={
                    "counts": {"media": len(self.media_list), "group": 1},
                    "positions": {"media": 0, "group": 0},
                    "group": {"title": None},
                    "media": self.media_list[: self.first_page_size],
                }
            )
        raise AssertionError(f"unexpected url: {url}")

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        response = await self.get(url, **kwargs)
        return response.json()


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="archives_nord",
        name="Archives départementales du Nord",
        protocol=Protocol.REST,
        base_url=BASE,
        auth="none",
        license="Restrictive — délibération CD Nord du 27/03/2017",
        rights="Numérisations : réutilisation commerciale soumise à licence écrite.",
        enabled=False,
        extra={"ark_naan": 33518},
    )


def _connector(http: FakeHttp) -> ArchivesNordConnector:
    return ArchivesNordConnector(_descriptor(), http)


# --- (a) search page parsing ------------------------------------------------


async def test_search_parses_notice_and_pdf():
    http = FakeHttp([_media(UUID1), _media(UUID2)])
    connector = _connector(http)

    assets = await connector.search("mines", limit=20)

    # one image notice + one PDF notice
    assert len(assets) == 2
    image, pdf = assets

    assert image.source_id == "archives_nord"
    assert image.source_asset_id == UUID1
    assert image.title == "DOUCHY-LES-MINES"
    assert image.image_url == f"{BASE}/images/{UUID1}.jpg"
    assert image.thumbnail_url == f"{BASE}/images/{UUID1}_thumbnail.jpg"
    assert image.page_url == f"{BASE}/ark:/33518/{ARK}"
    assert image.extra["viewer_url"] == f"{BASE}/ark:/33518/{ARK}/{UUID1}"
    assert image.extra["ark_name"] == ARK
    assert image.extra["media_count"] == 107
    assert image.extra["kind"] == "image"

    assert pdf.source_asset_id == PDF_UUID
    assert pdf.title == "Plan des travaux de la fosse"
    assert pdf.image_url is None
    assert pdf.thumbnail_url == f"{BASE}/pdf-preview/{PDF_UUID}_search_result_thumbnail"
    assert pdf.page_url == f"{BASE}/media/{PDF_UUID}.pdf"
    assert pdf.extra["kind"] == "pdf"
    assert pdf.extra["pages"] == 12

    url, params = http.calls[0]
    assert url.endswith("/search/results")
    assert params["q"] == "mines"
    assert params["page"] == "1"
    assert params["resultsPerPage"] == "20"


def test_parse_search_total_and_ark_extraction():
    connector = _connector(FakeHttp([]))
    hits, total = connector.parse_search(SEARCH_HTML)

    assert total == 264
    assert [h["kind"] for h in hits] == ["image", "pdf"]
    assert hits[0]["ark_name"] == ARK
    assert hits[0]["uuid"] == UUID1
    assert hits[1]["uuid"] == PDF_UUID


# --- (b)/(c)/(e) viewer API: counts, ranges, 400 ----------------------------


async def test_all_media_pages_with_inclusive_clamped_end():
    # group returns only the first media; the rest must come from a range call
    # whose ``end`` is clamped to N-1 (else the fake transport raises 400).
    http = FakeHttp([_media(UUID1), _media(UUID2)], first_page_size=1)
    connector = _connector(http)

    media = await connector.all_media(ARK)

    assert [m["uuid"] for m in media] == [UUID1, UUID2]
    range_calls = [(p["start"], p["end"]) for _, p in http.calls if "end" in p]
    assert range_calls == [(1, 1)]  # end inclusive, clamped to N-1 (=1)


async def test_record_media_returns_range():
    http = FakeHttp([_media(UUID1), _media(UUID2)])
    connector = _connector(http)

    media = await connector.record_media(ARK, start=0, end=1, group=0)

    assert [m["uuid"] for m in media] == [UUID1, UUID2]
    _, params = http.calls[0]
    assert params == {"arkName": ARK, "start": 0, "end": 1, "group": 0}


async def test_out_of_range_end_raises_http_400():
    http = FakeHttp([_media(UUID1), _media(UUID2)])
    connector = _connector(http)

    with pytest.raises(httpx.HTTPStatusError):
        await connector.record_media(ARK, start=0, end=5, group=0)


# --- (d) detail + licence ---------------------------------------------------


async def test_media_detail_exposes_visualizer_license():
    http = FakeHttp([_media(UUID1), _media(UUID2)])
    connector = _connector(http)

    data = await connector.media_detail(ARK, UUID1)

    assert connector.detail_media(data, UUID1)["uuid"] == UUID1
    license_block = connector.visualizer_license(data)
    assert license_block["uuid"] == "b6bad2e5-96d0-4166-ae0b-f01ebe0ab972"
    assert "redevance" in license_block["text"]

    _, params = http.calls[0]
    assert params == {"arkName": ARK, "uuid": UUID1}


# --- normalization + static URLs -------------------------------------------


def test_media_to_asset_normalizes_fields():
    connector = _connector(FakeHttp([]))
    asset = connector.media_to_asset(_media(UUID1))

    assert asset is not None
    assert asset.source_asset_id == UUID1
    assert asset.title == "DOUCHY-LES-MINES"
    assert asset.page_url == f"{BASE}/ark:/33518/{ARK}"
    assert asset.extra["viewer_url"] == f"{BASE}/ark:/33518/{ARK}/{UUID1}"
    assert asset.image_url == f"{BASE}/images/{UUID1}.jpg"
    assert asset.thumbnail_url == f"{BASE}/images/{UUID1}_thumbnail.jpg"
    assert asset.date_text == "1906-01-01"
    assert asset.year == 1906
    assert asset.tags == ["DOUCHY-LES-MINES"]
    assert asset.extra["reference_code"] == "M 474 / 177"
    assert asset.extra["naan"] == 33518
    assert "Restrictive" in asset.license


def test_image_urls():
    connector = _connector(FakeHttp([]))
    urls = connector.image_urls(UUID1)
    assert urls == {
        "original": f"{BASE}/images/{UUID1}.jpg",
        "thumbnail": f"{BASE}/images/{UUID1}_thumbnail.jpg",
    }


# --- descriptor wiring ------------------------------------------------------


def test_descriptor_is_disabled_rest_and_registered():
    raw = yaml.safe_load((SOURCES_DIR / "archives_nord.yaml").read_text(encoding="utf-8"))

    assert raw["id"] == "archives_nord"
    assert raw["protocol"] == "rest"
    assert raw["auth"] == "none"
    assert raw["license"]
    assert raw["enabled"] is False
    assert raw["extra"]["ark_naan"] == 33518

    descriptor = SourceDescriptor(**raw)
    assert descriptor.enabled is False
    assert CONNECTORS["archives_nord"] is ArchivesNordConnector
    assert isinstance(build_connector(descriptor, FakeHttp([])), ArchivesNordConnector)
