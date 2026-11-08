"""INA catalogue (catalogue.ina.fr, Surface A) — offline parsing and guards.

No network: fixtures under ``tests/fixtures/ina/`` mimic the real OPSIS pages.
Surface B (www.ina.fr) must stay gated off until written permission is on file.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import CONNECTORS, build_connector, ina
from mnemosyne.sources.ina import InaConnector

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "ina"


class _Response:
    def __init__(self, text: str) -> None:
        self.text = text
        self.status_code = 200


class FakeHttp:
    def __init__(self, *, single: str | None = None, html_by_page=None) -> None:
        self.single = single
        self.html_by_page = html_by_page or {}
        self.calls: list[tuple[str, dict]] = []

    async def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        if self.single is not None:
            return _Response(self.single)
        match = re.search(r"page=(\d+)", url)
        page = int(match.group(1)) if match else 1
        return _Response(self.html_by_page.get(page, ""))


def _descriptor(**extra) -> SourceDescriptor:
    return SourceDescriptor(
        id="ina",
        name="INA — Institut national de l'audiovisuel",
        protocol=Protocol.HTML,
        base_url="https://catalogue.ina.fr",
        auth="none",
        license="Tous droits réservés © INA",
        extra=extra,
    )


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _raw_descriptor() -> dict:
    return yaml.safe_load(
        (ROOT / "config" / "sources" / "ina.yaml").read_text(encoding="utf-8")
    )


def _paged_html(total: int, start: int) -> str:
    rows = []
    for i in range(start, start + 2):
        rows.append(
            f'<tr class="result_line_a"><td>{i}</td><td>Chaîne</td>'
            f"<td>01/01/1960</td><td></td><td>00:01:00</td>"
            f'<td><a href="https://catalogue.ina.fr/doc/TV-RADIO/DA_TEST{i}/slug?rang=1">'
            f"Titre {i}</a></td><td></td><td>Prog</td><td>Genre</td></tr>"
        )
    return (
        f"<p>Enregistrements 1 à 2 sur {total}</p>"
        '<table class="tableau tableau-header-gris">' + "".join(rows) + "</table>"
    )


def test_build_search_url() -> None:
    url = ina.build_search_url("Lacq pétrole")
    assert url.startswith("https://catalogue.ina.fr/docListe/TV-RADIO/?")
    assert "base_label=TVNAT,RADIO,TVSAT,PUBTV,TVREG,CLIPTV,DLDON" in url
    assert "itoustext=Lacq+p%C3%A9trole" in url
    assert "sujets_filter=Sujet" in url
    assert "bool_operator=AND" in url
    assert "tri=score1" in url
    assert "nbLignes=50" in url
    assert "page=1" in url
    with pytest.raises(ValueError):
        ina.build_search_url("x", sort="bogus")
    with pytest.raises(ValueError):
        ina.build_search_url("x", n_rows=33)


def test_parse_search_page() -> None:
    total, rows = ina.parse_search_page(_fixture("search_lacq.html"))
    assert total == 166
    assert len(rows) == 3

    first = next(r for r in rows if r["doc_id"] == "DA_AFE85003518")
    assert first["title"] == "Le pétrole d'Aquitaine"
    assert first["date_iso"] == "1950-05-04"
    assert first["channel"] == "Les Actualités Françaises"
    assert first["genre"] == "Presse filmée"
    assert first["duration_seconds"] == 40
    assert first["collection"] == "Journal Les Actualités Françaises"
    assert first["notice_url"] == (
        "https://catalogue.ina.fr/doc/TV-RADIO/DA_AFE85003518/le-petrole-d-aquitaine"
    )
    assert "?rang" not in first["notice_url"]

    empty = next(r for r in rows if r["doc_id"] == "RD_913264.001.003")
    assert empty["channel"] is None
    assert empty["collection"] is None
    assert empty["genre"] is None
    assert empty["duration_seconds"] == 900


def test_parse_notice_tv() -> None:
    notice = ina.parse_notice(
        _fixture("notice_da_afe85003518.html"),
        url="https://catalogue.ina.fr/doc/TV-RADIO/DA_AFE85003518/le-petrole-d-aquitaine",
    )
    assert notice["id"] == "DA_AFE85003518"
    assert "forage pétrolier" in notice["description"]  # via RES
    assert notice["duration_seconds"] == 40
    assert notice["channel"] == "Les Actualités Françaises"
    assert notice["date_iso"] == "1950-05-04"
    assert notice["year"] == 1950
    assert notice["collection"] == "Journal Les Actualités Françaises"
    assert notice["type"] == "audiovisual-archive-notice"
    assert notice["image_url"] is None and notice["media_url"] is None
    # keywords = DE + DES
    assert "pétrole" in notice["keywords"]
    assert "forage" in notice["keywords"]
    assert "Lacq" in notice["keywords"]


def test_parse_notice_radio() -> None:
    notice = ina.parse_notice(
        _fixture("notice_rd_913264_001_003.html"),
        url="https://catalogue.ina.fr/doc/TV-RADIO/RD_913264.001.003/pour-memoire",
    )
    assert notice["id"] == "RD_913264.001.003"
    assert "Chronique" in notice["description"]  # CHAP fallback (no RES)
    assert notice["duration_seconds"] == 900
    assert notice["channel"] == "Radio Bleue"
    assert "gaz" in notice["keywords"]
    assert "industrialisation" in notice["keywords"]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("00:00:40", 40),
        ("00:15:00", 900),
        ("01:02:03", 3723),
        ("15:00", 900),
        ("00:00:40:12", 40),  # frames ignored
        (None, None),
        ("", None),
        ("bogus", None),
    ],
)
def test_parse_duration(text, expected) -> None:
    assert ina.parse_duration(text) == expected


def test_descriptor() -> None:
    raw = _raw_descriptor()
    descriptor = SourceDescriptor(**raw)
    assert descriptor.id == "ina"
    assert descriptor.enabled is True
    assert descriptor.protocol == Protocol.HTML
    assert descriptor.license

    extra = raw["extra"]
    assert extra["type"] == "audiovisual-archive-notice"
    assert extra["reuse_allowed"] is False
    assert extra["media_download"] is False
    assert extra["attribution_required"] is True
    assert extra["attribution_text"]
    assert extra["reuse_contact"]
    assert extra["scraping_consent"]
    assert extra["public_surface_enabled"] is False

    assert CONNECTORS["ina"] is InaConnector
    assert isinstance(build_connector(descriptor, FakeHttp(single="")), InaConnector)


@pytest.mark.asyncio
async def test_no_media_download() -> None:
    http = FakeHttp(single=_fixture("notice_da_afe85003518.html"))
    connector = InaConnector(_descriptor(), http)
    notice = ina.parse_notice(
        _fixture("notice_da_afe85003518.html"),
        url="https://catalogue.ina.fr/doc/TV-RADIO/DA_AFE85003518/le-petrole-d-aquitaine",
    )
    asset = connector.notice_to_asset(notice)
    assert asset.image_url is None
    assert asset.thumbnail_url is None
    assert asset.extra["image_url"] is None
    assert asset.extra["media_url"] is None
    assert await connector.fetch(asset) is None
    assert http.calls == []


@pytest.mark.asyncio
async def test_search_returns_row_assets() -> None:
    http = FakeHttp(single=_fixture("search_lacq.html"))
    connector = InaConnector(_descriptor(crawl_delay_s=0), http)
    assets = await connector.search("Lacq pétrole", limit=2)
    assert len(assets) == 2
    assert all(asset.image_url is None for asset in assets)
    assert all(
        asset.page_url and asset.page_url.startswith("https://catalogue.ina.fr/")
        for asset in assets
    )
    assert any(asset.source_asset_id == "DA_AFE85003518" for asset in assets)
    # a single search page was fetched (no enrichment, no media download)
    assert len(http.calls) == 1


@pytest.mark.asyncio
async def test_surface_b_gate() -> None:
    assert ina.public_search_allowed() is False
    connector = InaConnector(_descriptor(), FakeHttp(single="{}"))
    with pytest.raises(PermissionError):
        await connector.search_public("Lacq")


@pytest.mark.asyncio
async def test_crawl_delay_pagination() -> None:
    http = FakeHttp(html_by_page={1: _paged_html(100, 0), 2: _paged_html(100, 2)})

    class RecordingConnector(InaConnector):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.paces: list[float] = []

        async def _pace(self, seconds: float) -> None:
            self.paces.append(seconds)

    connector = RecordingConnector(_descriptor(crawl_delay_s=5), http)
    assets = await connector.search_all("Lacq", max_results=4, n_rows=20)

    assert len(assets) == 4
    assert connector.paces == [5.0]
    assert ina.CRAWL_DELAY == 5.0
    assert len(http.calls) == 2
