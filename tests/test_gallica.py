"""Gallica (BnF) SRU search: XML parsing into canonical assets (offline)."""

from __future__ import annotations

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.gallica import GallicaConnector

BASE = "https://gallica.bnf.fr/SRU"
ARK = "ark:/12148/bpt6k1234567"
SRU = f"""<?xml version="1.0" encoding="UTF-8"?>
<searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/">
  <records>
    <record>
      <recordData>
        <dc xmlns:dc="http://purl.org/dc/elements/1.1/">
          <dc:title>Usine de Lacq</dc:title>
          <dc:creator>Anonyme</dc:creator>
          <dc:date>1950</dc:date>
          <dc:description>Photographie d'usine</dc:description>
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


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="gallica",
        name="Gallica (BnF)",
        protocol=Protocol.SRU,
        base_url=BASE,
        auth="none",
        license="varies",
    )


@pytest.mark.asyncio
async def test_search_parses_sru_records():
    http = FakeHttp(SRU)
    connector = GallicaConnector(_descriptor(), http)

    assets = await connector.search("usine", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.title == "Usine de Lacq"
    assert asset.creator == "Anonyme"
    assert asset.year == 1950
    assert asset.description == "Photographie d'usine"
    assert asset.rights == "Domaine public"
    assert asset.page_url == f"https://gallica.bnf.fr/{ARK}"
    assert asset.image_url == f"https://gallica.bnf.fr/iiif/{ARK}/f1/full/full/0/native.jpg"
    assert asset.thumbnail_url == f"https://gallica.bnf.fr/iiif/{ARK}/f1/full/384,/0/native.jpg"
    assert asset.iiif_id == ARK

    params = http.calls[0][1]["params"]
    assert params["operation"] == "searchRetrieve"
    assert "usine" in params["query"]


@pytest.mark.asyncio
async def test_search_ignores_records_without_ark():
    connector = GallicaConnector(_descriptor(), FakeHttp(SRU.replace(ARK, "no-ark-here")))
    assert await connector.search("usine") == []


@pytest.mark.asyncio
async def test_search_survives_malformed_xml():
    connector = GallicaConnector(_descriptor(), FakeHttp("<not-xml"))
    assert await connector.search("usine") == []
