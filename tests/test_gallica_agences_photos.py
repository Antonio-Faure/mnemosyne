"""Gallica agences photos (SRU photo-only) — XML parsing into assets (offline)."""

from __future__ import annotations

from typing import Any

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.gallica_agences_photos import GallicaAgencesPhotosConnector

BASE = "https://gallica.bnf.fr/SRU"
ARK = "ark:/12148/btv1b9045876v"
SRU = f"""<?xml version="1.0" encoding="UTF-8"?>
<searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/">
  <records>
    <record>
      <recordData>
        <dc xmlns:dc="http://purl.org/dc/elements/1.1/">
          <dc:title>Usine Citroën, quai de Javel</dc:title>
          <dc:creator>Agence Mondial</dc:creator>
          <dc:date>1932</dc:date>
          <dc:type>photographie</dc:type>
          <dc:description>Vue de l'usine automobile</dc:description>
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
        id="gallica_agences_photos",
        name="Gallica (BnF) — Agences photographiques de presse",
        protocol=Protocol.SRU,
        base_url=BASE,
        auth="none",
        license="varies",
        extra=extra,
    )


@pytest.mark.asyncio
async def test_search_parses_photo_records():
    http = FakeHttp(SRU)
    connector = GallicaAgencesPhotosConnector(_descriptor(), http)

    assets = await connector.search("Citroën", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.title == "Usine Citroën, quai de Javel"
    assert asset.creator == "Agence Mondial"
    assert asset.year == 1932
    assert asset.description == "Vue de l'usine automobile"
    assert asset.rights == "Domaine public"
    assert asset.page_url == f"https://gallica.bnf.fr/{ARK}"
    assert asset.image_url == f"https://gallica.bnf.fr/iiif/{ARK}/f1/full/full/0/native.jpg"
    assert asset.thumbnail_url == f"https://gallica.bnf.fr/iiif/{ARK}/f1/full/384,/0/native.jpg"
    assert asset.iiif_id == ARK
    # Détection de l'agence de presse exposée côté asset.
    assert asset.extra.get("agence") == "Agence Mondial"
    assert "agence:Agence Mondial" in asset.tags

    params = http.calls[0][1]["params"]
    assert params["operation"] == "searchRetrieve"
    assert 'gallica all "Citroën"' in params["query"]
    # La restriction photo-only est forcée au niveau de la requête SRU.
    assert 'dc.type all "photographie"' in params["query"]


@pytest.mark.asyncio
async def test_search_ignores_records_without_ark():
    connector = GallicaAgencesPhotosConnector(
        _descriptor(), FakeHttp(SRU.replace(ARK, "no-ark-here"))
    )
    assert await connector.search("Citroën") == []


@pytest.mark.asyncio
async def test_search_survives_malformed_xml():
    connector = GallicaAgencesPhotosConnector(_descriptor(), FakeHttp("<not-xml"))
    assert await connector.search("Citroën") == []


@pytest.mark.asyncio
async def test_doc_type_is_overridable_via_extra():
    http = FakeHttp(SRU)
    connector = GallicaAgencesPhotosConnector(_descriptor(doc_type="carte"), http)
    await connector.search("Citroën", limit=5)
    params = http.calls[0][1]["params"]
    assert 'dc.type all "carte"' in params["query"]
