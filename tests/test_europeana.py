"""Europeana connector: normalization + key handling (no network)."""

from __future__ import annotations

from typing import Any

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.europeana import EuropeanaConnector

SAMPLE: dict[str, Any] = {
    "success": True,
    "itemsCount": 2,
    "totalResults": 2,
    "items": [
        {
            "id": "/9200338/BibliographicResource_3000095653203",
            "title": ["Derrick abandonné près de Lacq"],
            "dcCreator": ["Anonyme"],
            "dcDescription": ["Vue d'un derrick de pétrole."],
            "year": ["1905"],
            "edmIsShownBy": ["https://example.org/img/derrick.jpg"],
            "edmPreview": ["https://example.org/img/derrick_thumbs.jpg"],
            "guid": "https://www.europeana.eu/item/9200338/BibliographicResource_3000095653203",
            "rights": ["http://creativecommons.org/publicdomain/mark/1.0/"],
            "dataProvider": ["Bibliothèque nationale de France"],
            "provider": ["Europeana"],
            "country": ["France"],
            "type": "IMAGE",
        },
        {
            "id": "/2048128/SomeItem",
            "title": ["Usine métallurgique"],
            # no edmIsShownBy, but a preview -> still usable
            "edmPreview": ["https://example.org/img/only_preview.jpg"],
            "guid": "https://www.europeana.eu/item/2048128/SomeItem",
            "rights": ["http://rightsstatements.org/vocab/InC/1.0/"],
            "country": ["Germany"],
        },
    ],
}


class FakeHttp:
    """Records calls and returns a canned Europeana payload."""

    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        return self.payload


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="europeana",
        name="Europeana",
        protocol=Protocol.REST,
        base_url="https://api.europeana.eu/record/v2/search.json",
        auth="api_key",
        key_env="EUROPEANA_API_KEY",
        license="varies",
        rights="per record",
    )


async def test_search_normalizes_items(monkeypatch):
    monkeypatch.setenv("EUROPEANA_API_KEY", "secret-key")
    http = FakeHttp(SAMPLE)
    connector = EuropeanaConnector(_descriptor(), http)

    assets = await connector.search("derrick", limit=10)

    assert len(assets) == 2
    first = assets[0]
    assert first.source_id == "europeana"
    assert first.source_asset_id == "9200338/BibliographicResource_3000095653203"
    assert first.title == "Derrick abandonné près de Lacq"
    assert first.creator == "Anonyme"
    assert first.year == 1905
    assert first.image_url == "https://example.org/img/derrick.jpg"
    assert first.thumbnail_url == "https://example.org/img/derrick_thumbs.jpg"
    assert first.page_url.startswith("https://www.europeana.eu/item/")
    assert first.license.startswith("http://creativecommons.org")
    assert first.extra["data_provider"] == "Bibliothèque nationale de France"

    # second item has no edmIsShownBy -> falls back to the preview image
    assert assets[1].image_url == "https://example.org/img/only_preview.jpg"

    url, kwargs = http.calls[0]
    assert url.endswith("/record/v2/search.json")
    assert kwargs["params"]["wskey"] == "secret-key"
    assert kwargs["params"]["query"] == "derrick"
    assert kwargs["params"]["qf"] == "TYPE:IMAGE"


async def test_search_without_key_returns_empty(monkeypatch):
    monkeypatch.delenv("EUROPEANA_API_KEY", raising=False)
    http = FakeHttp(SAMPLE)
    connector = EuropeanaConnector(_descriptor(), http)

    assert await connector.search("derrick") == []
    assert http.calls == []  # no key -> never hits the network


async def test_search_skips_items_without_media(monkeypatch):
    monkeypatch.setenv("EUROPEANA_API_KEY", "k")
    http = FakeHttp({"items": [{"id": "/1/x", "title": ["sans image"]}]})
    connector = EuropeanaConnector(_descriptor(), http)

    assert await connector.search("x") == []
