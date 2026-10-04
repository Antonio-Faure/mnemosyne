"""Smithsonian connector: normalization + key handling (no network)."""

from __future__ import annotations

from typing import Any

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.smithsonian import SmithsonianConnector

SAMPLE: dict[str, Any] = {
    "status": 200,
    "responseCode": 1,
    "response": {
        "rowCount": 2,
        "message": "content found",
        "rows": [
            {
                "id": "edanmdm-nmaahc_2011.123",
                "title": "Drumstick",
                "unitCode": "NMAAHC",
                "type": "edanmdm",
                "url": "edanmdm:nmaahc_2011.123",
                "content": {
                    "freetext": {
                        "name": [{"label": "Maker", "content": "Unknown"}],
                        "date": [{"label": "Date", "content": "1920"}],
                        "notes": [{"label": "Notes", "content": "A carved drumstick."}],
                        "topic": [
                            {"label": "Topic", "content": "Music"},
                            {"label": "Topic", "content": "African American culture"},
                        ],
                        "place": [{"label": "Place", "content": "United States"}],
                        "objectType": [{"label": "Type", "content": "Musical instruments"}],
                    },
                    "descriptiveNonRepeating": {
                        "guid": "https://nmaahc.si.edu/object/nmaahc_2011.123",
                        "record_ID": "nmaahc_2011.123",
                        "record_link": "https://nmaahc.si.edu/object/nmaahc_2011.123",
                        "unit_code": "NMAAHC",
                        "data_source": "National Museum of African American History and Culture",
                        "metadata_usage": {"access": "CC0"},
                        "online_media": {
                            "media": [
                                {
                                    "id": "media-1",
                                    "type": "Images",
                                    "usage": {"access": "CC0"},
                                    "content": "https://ids.si.edu/ids/deliveryService?id=NMAAHC-1",
                                    "thumbnail": "https://ids.si.edu/ids/deliveryService?id=NMAAHC-1&max=300",
                                }
                            ]
                        },
                    },
                },
            },
            {
                "id": "edanmdm-fsg_2",
                "title": "Engine part",
                "unitCode": "FSG",
                # no online_media -> should be skipped
                "content": {"freetext": {}, "descriptiveNonRepeating": {}},
            },
        ],
    },
}


class FakeHttp:
    """Records calls and returns a canned Smithsonian payload."""

    def __init__(self, payload: Any):
        self.payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        return self.payload


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="smithsonian",
        name="Smithsonian Open Access",
        protocol=Protocol.REST,
        base_url="https://api.si.edu/openaccess/api/v1.0",
        auth="api_key",
        key_env="SMITHSONIAN_API_KEY",
        license="CC0",
        rights="Open Access; most records CC0",
    )


async def test_search_normalizes_rows(monkeypatch):
    monkeypatch.setenv("SMITHSONIAN_API_KEY", "secret-key")
    http = FakeHttp(SAMPLE)
    connector = SmithsonianConnector(_descriptor(), http)

    assets = await connector.search("drumstick", limit=10)

    # row without online_media is skipped
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "smithsonian"
    assert asset.source_asset_id == "edanmdm-nmaahc_2011.123"
    assert asset.title == "Drumstick"
    assert asset.creator == "Unknown"
    assert asset.year == 1920
    assert asset.description == "A carved drumstick."
    assert asset.license == "CC0"
    assert asset.page_url == "https://nmaahc.si.edu/object/nmaahc_2011.123"
    assert asset.image_url == "https://ids.si.edu/ids/deliveryService?id=NMAAHC-1"
    assert asset.thumbnail_url == (
        "https://ids.si.edu/ids/deliveryService?id=NMAAHC-1&max=300"
    )
    assert "Music" in asset.tags
    assert asset.extra["unit_code"] == "NMAAHC"
    assert asset.extra["media_type"] == "Images"
    assert asset.extra["place"] == ["United States"]

    url, kwargs = http.calls[0]
    assert url.endswith("/search")
    assert kwargs["params"]["api_key"] == "secret-key"
    assert kwargs["params"]["q"] == "drumstick"
    assert kwargs["params"]["rows"] == "10"
    assert kwargs["params"]["start"] == "0"


async def test_search_without_key_returns_empty(monkeypatch):
    monkeypatch.delenv("SMITHSONIAN_API_KEY", raising=False)
    http = FakeHttp(SAMPLE)
    connector = SmithsonianConnector(_descriptor(), http)

    assert await connector.search("drumstick") == []
    assert http.calls == []  # no key -> never hits the network


async def test_title_falls_back_to_descriptive_title(monkeypatch):
    monkeypatch.setenv("SMITHSONIAN_API_KEY", "k")
    payload = {
        "response": {
            "rows": [
                {
                    "id": "edanmdm-x",
                    "content": {
                        "freetext": {},
                        "descriptiveNonRepeating": {
                            "title": {"label": "Title", "content": "Fallback title"},
                            "online_media": {
                                "media": [
                                    {
                                        "type": "Images",
                                        "usage": {"access": "CC0"},
                                        "content": "https://ids.si.edu/ids/deliveryService?id=X",
                                    }
                                ]
                            },
                        },
                    },
                }
            ]
        }
    }
    http = FakeHttp(payload)
    connector = SmithsonianConnector(_descriptor(), http)

    assets = await connector.search("x")
    assert len(assets) == 1
    assert assets[0].title == "Fallback title"
    assert assets[0].thumbnail_url == assets[0].image_url
