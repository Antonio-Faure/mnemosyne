"""Gallica (BnF) press/photo connector — SRU→Asset with tag enrichment (offline)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import CONNECTORS, build_connector
from mnemosyne.sources.gallica import GallicaConnector
from mnemosyne.sources.gallica_bnf import GallicaBnfConnector

BASE = "https://gallica.bnf.fr/SRU"
ARK = "ark:/12148/btv1b9000000x"
SRU = f"""<?xml version="1.0" encoding="UTF-8"?>
<searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/">
  <records>
    <record>
      <recordData>
        <dc xmlns:dc="http://purl.org/dc/elements/1.1/">
          <dc:title>Puits de pétrole à Pechelbronn</dc:title>
          <dc:creator>Agence Rol</dc:creator>
          <dc:date>1920</dc:date>
          <dc:type>image</dc:type>
          <dc:type>photographie</dc:type>
          <dc:subject>Pétrole</dc:subject>
          <dc:subject>Pechelbronn</dc:subject>
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


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="gallica_bnf",
        name="Gallica (BnF) — presse & photographie",
        protocol=Protocol.SRU,
        base_url=BASE,
        auth="none",
        license="varies",
    )


def test_connector_is_registered_and_subclasses_gallica():
    assert CONNECTORS["gallica_bnf"] is GallicaBnfConnector
    assert issubclass(GallicaBnfConnector, GallicaConnector)
    built = build_connector(_descriptor(), FakeHttp(""))
    assert isinstance(built, GallicaBnfConnector)


@pytest.mark.asyncio
async def test_search_parses_and_tags_visual_records():
    http = FakeHttp(SRU)
    assets = await GallicaBnfConnector(_descriptor(), http).search("pétrole", limit=10)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "gallica_bnf"
    assert asset.title == "Puits de pétrole à Pechelbronn"
    assert asset.creator == "Agence Rol"
    assert asset.year == 1920
    assert asset.rights == "Domaine public"
    assert asset.image_url == f"https://gallica.bnf.fr/iiif/{ARK}/f1/full/full/0/native.jpg"
    assert asset.thumbnail_url == f"https://gallica.bnf.fr/iiif/{ARK}/f1/full/384,/0/native.jpg"
    assert asset.iiif_id == ARK
    # dc:type and dc:subject become tags (order preserved, de-duplicated)
    assert asset.tags == ["image", "photographie", "Pétrole", "Pechelbronn"]
    assert asset.extra["connector"] == "gallica-bnf"
    assert asset.extra["variant_of"] == "gallica"

    params = http.calls[0][1]["params"]
    assert params["operation"] == "searchRetrieve"
    assert "pétrole" in params["query"]


@pytest.mark.asyncio
async def test_search_ignores_records_without_ark():
    connector = GallicaBnfConnector(_descriptor(), FakeHttp(SRU.replace(ARK, "no-ark")))
    assert await connector.search("pétrole") == []


@pytest.mark.asyncio
async def test_search_survives_malformed_xml():
    connector = GallicaBnfConnector(_descriptor(), FakeHttp("<not-xml"))
    assert await connector.search("pétrole") == []


def test_descriptor_is_petroleum_focused():
    path = Path(__file__).resolve().parents[1] / "config" / "sources" / "gallica_bnf.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert raw["id"] == "gallica_bnf"
    assert raw["protocol"] == "sru"
    assert raw["base_url"] == BASE
    assert raw.get("enabled", True) is True
    seeds = " ".join(raw.get("seeds", [])).lower()
    assert "pétrole" in seeds or "petrole" in seeds
