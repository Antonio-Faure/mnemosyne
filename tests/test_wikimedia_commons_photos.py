"""Wikimedia Commons photographs: imageinfo JSON into canonical assets (offline).

The connector must restrict the search to ``filetype:bitmap`` and additionally
discard any non-raster file (PDF book scan, DjVu, SVG) that slips through, so a
1914 historical query yields photographs, not digitised text.
"""

from __future__ import annotations

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.wikimedia_commons_photos import WikimediaCommonsPhotosConnector

BASE = "https://commons.wikimedia.org/w/api.php"
PHOTO_URL = "https://upload.wikimedia.org/wikipedia/commons/a/ab/German_troops_Brussels.jpg"
PHOTO_PAGE = "https://commons.wikimedia.org/wiki/File:German_troops_Brussels_1914.jpg"
PHOTO_THUMB = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/x.jpg/512px-x.jpg"

PAYLOAD = {
    "query": {
        "pages": [
            {
                "pageid": 123,
                "ns": 6,
                "title": "File:German troops Brussels 1914.jpg",
                "imageinfo": [
                    {
                        "url": PHOTO_URL,
                        "descriptionurl": PHOTO_PAGE,
                        "thumburl": PHOTO_THUMB,
                        "width": 2000,
                        "height": 1500,
                        "mime": "image/jpeg",
                        "extmetadata": {
                            "DateTimeOriginal": {"value": "1914-08-20"},
                            "LicenseShortName": {"value": "Public domain"},
                            "Artist": {"value": "<a href='#'>Anonyme</a>"},
                            "ImageDescription": {"value": "Troupes allemandes à Bruxelles"},
                            "Credit": {"value": "Bibliothèque nationale"},
                        },
                    }
                ],
            },
            {
                "pageid": 456,
                "ns": 6,
                "title": "File:Some Internet Archive book.pdf",
                "imageinfo": [
                    {
                        "url": "https://upload.wikimedia.org/wikipedia/commons/1/1a/book.pdf",
                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Some_book.pdf",
                        "mime": "application/pdf",
                        "extmetadata": {},
                    }
                ],
            },
            {
                "pageid": 789,
                "ns": 6,
                "title": "File:Old volume.djvu",
                "imageinfo": [
                    {
                        "url": "https://upload.wikimedia.org/wikipedia/commons/7/7a/old.djvu",
                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Old_volume.djvu",
                        "mime": "image/vnd.djvu",
                        "extmetadata": {},
                    }
                ],
            },
            {"pageid": 999, "ns": 6, "title": "File:No imageinfo.jpg"},
        ]
    }
}


class FakeHttp:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict]] = []

    async def get_json(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.payload


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="wikimedia_commons_photos",
        name="Wikimedia Commons — Photographies",
        protocol=Protocol.REST,
        base_url=BASE,
        auth="none",
        license="varies",
    )


@pytest.mark.asyncio
async def test_search_keeps_photos_and_drops_documents():
    http = FakeHttp(PAYLOAD)
    connector = WikimediaCommonsPhotosConnector(_descriptor(), http)

    assets = await connector.search("troupes allemandes Bruxelles 1914", limit=10)

    # Only the JPEG photograph survives: the PDF, the DjVu and the page with no
    # imageinfo are all discarded.
    assert len(assets) == 1
    asset = assets[0]
    assert asset.title == "German troops Brussels 1914"
    assert asset.creator == "Anonyme"  # HTML tags stripped from the Artist field
    assert asset.year == 1914
    assert asset.description == "Troupes allemandes à Bruxelles"
    assert asset.license == "Public domain"
    assert asset.page_url == PHOTO_PAGE
    assert asset.image_url == PHOTO_URL
    assert asset.thumbnail_url == PHOTO_THUMB
    assert asset.width == 2000
    assert asset.height == 1500
    assert asset.extra["mime"] == "image/jpeg"
    assert asset.extra["credit"] == "Bibliothèque nationale"

    params = http.calls[0][1]["params"]
    assert "filetype:bitmap" in params["gsrsearch"]
    assert params["gsrnamespace"] == "6"
    assert "mime" in params["iiprop"]


@pytest.mark.asyncio
async def test_search_without_pages_returns_empty():
    connector = WikimediaCommonsPhotosConnector(_descriptor(), FakeHttp({"query": {}}))
    assert await connector.search("troupes allemandes") == []


@pytest.mark.asyncio
async def test_search_respects_limit():
    many = {
        "query": {
            "pages": [
                {
                    "pageid": 1,
                    "ns": 6,
                    "title": "File:a.jpg",
                    "imageinfo": [{"mime": "image/jpeg", "url": PHOTO_URL, "extmetadata": {}}],
                },
                {
                    "pageid": 2,
                    "ns": 6,
                    "title": "File:b.jpg",
                    "imageinfo": [{"mime": "image/jpeg", "url": PHOTO_URL, "extmetadata": {}}],
                },
            ]
        }
    }
    connector = WikimediaCommonsPhotosConnector(_descriptor(), FakeHttp(many))
    assets = await connector.search("x", limit=1)
    assert len(assets) == 1
