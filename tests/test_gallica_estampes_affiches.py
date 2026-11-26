"""Gallica estampes/affiches (SRU estampe+affiche) — parsing into assets (offline)."""

from __future__ import annotations

from typing import Any

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.gallica_estampes_affiches import GallicaEstampesAffichesConnector

BASE = "https://gallica.bnf.fr/SRU"
ARK = "ark:/12148/btv1b10123456z"
SRU = f"""<?xml version="1.0" encoding="UTF-8"?>
<searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/">
  <records>
    <record>
      <recordData>
        <dc xmlns:dc="http://purl.org/dc/elements/1.1/">
          <dc:title>Bibendum, pneumatiques Michelin</dc:title>
          <dc:creator>O'Galop</dc:creator>
          <dc:date>1910</dc:date>
          <dc:type>affiche</dc:type>
          <dc:description>Affiche publicitaire pour le pneu Michelin</dc:description>
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
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get(self, url: str, **kwargs: Any) -> _Response:
        self.calls.append((url, kwargs))
        return _Response(self.text)


def _descriptor(**extra: Any) -> SourceDescriptor:
    return SourceDescriptor(
        id="gallica_estampes_affiches",
        name="Gallica (BnF) — Estampes et affiches (publicité industrielle)",
        protocol=Protocol.SRU,
        base_url=BASE,
        auth="none",
        license="varies",
        extra=extra,
    )


@pytest.mark.asyncio
async def test_search_parses_poster_records():
    http = FakeHttp(SRU)
    connector = GallicaEstampesAffichesConnector(_descriptor(), http)

    assets = await connector.search("Michelin", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.title == "Bibendum, pneumatiques Michelin"
    assert asset.creator == "O'Galop"
    assert asset.year == 1910
    assert asset.description == "Affiche publicitaire pour le pneu Michelin"
    assert asset.rights == "Domaine public"
    assert asset.page_url == f"https://gallica.bnf.fr/{ARK}"
    assert asset.image_url == f"https://gallica.bnf.fr/iiif/{ARK}/f1/full/full/0/native.jpg"
    assert asset.thumbnail_url == f"https://gallica.bnf.fr/iiif/{ARK}/f1/full/384,/0/native.jpg"
    assert asset.iiif_id == ARK
    # Genre de document exposé côté asset (dérivé de dc.type).
    assert asset.extra.get("genre") == "affiche"
    assert "genre:affiche" in asset.tags

    params = http.calls[0][1]["params"]
    assert params["operation"] == "searchRetrieve"
    assert 'gallica all "Michelin"' in params["query"]
    # La restriction estampe/affiche est forcée au niveau de la requête SRU.
    assert 'dc.type all "estampe"' in params["query"]
    assert 'dc.type all "affiche"' in params["query"]


@pytest.mark.asyncio
async def test_search_ignores_records_without_ark():
    connector = GallicaEstampesAffichesConnector(
        _descriptor(), FakeHttp(SRU.replace(ARK, "no-ark-here"))
    )
    assert await connector.search("Michelin") == []


@pytest.mark.asyncio
async def test_search_survives_malformed_xml():
    connector = GallicaEstampesAffichesConnector(_descriptor(), FakeHttp("<not-xml"))
    assert await connector.search("Michelin") == []


@pytest.mark.asyncio
async def test_doc_types_are_overridable_via_extra():
    http = FakeHttp(SRU)
    connector = GallicaEstampesAffichesConnector(_descriptor(doc_types=["carte"]), http)
    await connector.search("Michelin", limit=5)
    params = http.calls[0][1]["params"]
    assert 'dc.type all "carte"' in params["query"]
    assert 'dc.type all "estampe"' not in params["query"]


@pytest.mark.asyncio
async def test_estampe_genre_is_detected():
    connector = GallicaEstampesAffichesConnector(
        _descriptor(), FakeHttp(SRU.replace("<dc:type>affiche", "<dc:type>estampe"))
    )
    assets = await connector.search("Michelin", limit=5)
    assert assets[0].extra.get("genre") == "estampe"
    assert "genre:estampe" in assets[0].tags
