"""Gallica « presse & réclame » (SRU): CQL targeting + parsing (offline)."""

from __future__ import annotations

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.gallica_presse_reclame import GallicaPresseReclameConnector

BASE = "https://gallica.bnf.fr/SRU"
ARK = "ark:/12148/btv1b53012345f"
SRU = f"""<?xml version="1.0" encoding="UTF-8"?>
<searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/">
  <records>
    <record>
      <recordData>
        <dc xmlns:dc="http://purl.org/dc/elements/1.1/">
          <dc:title>Citroën — la Tour Eiffel illuminee</dc:title>
          <dc:creator>Agence Rol</dc:creator>
          <dc:date>1925</dc:date>
          <dc:description>Photographie de presse</dc:description>
          <dc:rights>Domaine public</dc:rights>
          <dc:identifier>https://gallica.bnf.fr/{ARK}</dc:identifier>
        </dc>
      </recordData>
    </record>
  </records>
</searchRetrieveResponse>"""


class _Response:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeHttp:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[tuple[str, dict]] = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response(self.text)


def _descriptor(extra: dict | None = None) -> SourceDescriptor:
    return SourceDescriptor(
        id="gallica_presse_reclame",
        name="Gallica (BnF) — Presse & réclame",
        protocol=Protocol.SRU,
        base_url=BASE,
        auth="none",
        license="varies",
        extra=extra or {},
    )


@pytest.mark.asyncio
async def test_query_targets_press_and_posters_with_date_window():
    http = FakeHttp(SRU)
    connector = GallicaPresseReclameConnector(_descriptor(), http)
    await connector.search("citroen tour eiffel", limit=5)
    params = http.calls[0][1]["params"]
    assert params["operation"] == "searchRetrieve"
    query = params["query"]
    assert 'gallica all "citroen tour eiffel"' in query
    assert 'dc.type all "photographie"' in query
    assert 'dc.type all "affiche"' in query
    assert 'dc.type all "estampe"' in query
    assert 'dc.date within "1919 1935"' in query


@pytest.mark.asyncio
async def test_search_parses_records_into_assets():
    connector = GallicaPresseReclameConnector(_descriptor(), FakeHttp(SRU))
    assets = await connector.search("citroen", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.title.startswith("Citroën")
    assert asset.creator == "Agence Rol"
    assert asset.year == 1925
    assert asset.rights == "Domaine public"
    assert asset.page_url == f"https://gallica.bnf.fr/{ARK}"
    assert asset.image_url == f"https://gallica.bnf.fr/iiif/{ARK}/f1/full/full/0/native.jpg"
    assert asset.iiif_id == ARK
    assert asset.extra["source"] == "gallica-presse-reclame-sru"


@pytest.mark.asyncio
async def test_descriptor_extra_overrides_facets():
    extra = {"doc_types": ["affiche"], "year_min": 1920, "year_max": 1930}
    http = FakeHttp(SRU)
    connector = GallicaPresseReclameConnector(_descriptor(extra), http)
    await connector.search("citroen", limit=5)
    query = http.calls[0][1]["params"]["query"]
    assert 'dc.type all "affiche"' in query
    assert 'dc.type all "photographie"' not in query
    assert 'dc.date within "1920 1930"' in query


@pytest.mark.asyncio
async def test_search_ignores_records_without_ark():
    connector = GallicaPresseReclameConnector(
        _descriptor(), FakeHttp(SRU.replace(ARK, "no-ark-here"))
    )
    assert await connector.search("citroen") == []


@pytest.mark.asyncio
async def test_search_survives_malformed_xml():
    connector = GallicaPresseReclameConnector(_descriptor(), FakeHttp("<not-xml"))
    assert await connector.search("citroen") == []
