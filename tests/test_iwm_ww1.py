"""IWM WW1 connector (Q series via the Wikimedia Commons MediaWiki API), offline."""

from __future__ import annotations

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.iwm_ww1 import IwmWw1Connector

BASE = "https://commons.wikimedia.org/w/api.php"


class FakeHttp:
    def __init__(self, responder):
        self._responder = responder
        self.calls: list[tuple[str, dict]] = []

    async def get_json(self, url, **kwargs):
        if callable(self._responder):
            reply = self._responder(kwargs["params"], len(self.calls))
        else:
            reply = self._responder
        self.calls.append((url, kwargs))
        return reply


def _page(
    pageid,
    title,
    *,
    lic="Public domain",
    copyrighted="False",
    mime="image/jpeg",
    url="https://upload.wikimedia.org/wikipedia/commons/a/ab/Foo.jpg",
    desc="A scene",
    artist="Ernest Brooks",
    date="10 January 1917 (First World War)",
    width=640,
    height=480,
):
    return {
        "pageid": pageid,
        "title": title,
        "ns": 6,
        "imageinfo": [
            {
                "descriptionurl": "https://commons.wikimedia.org/wiki/"
                + title.replace(" ", "_"),
                "url": url,
                "width": width,
                "height": height,
                "mime": mime,
                "user": "Fae",
                "extmetadata": {
                    "LicenseShortName": {"value": lic},
                    "Copyrighted": {"value": copyrighted},
                    "ImageDescription": {"value": desc},
                    "Artist": {"value": artist},
                    "DateTimeOriginal": {"value": date},
                },
            }
        ],
    }


def _descriptor(extra=None):
    return SourceDescriptor(
        id="iwm_ww1",
        name="Imperial War Museums WW1",
        protocol=Protocol.REST,
        base_url=BASE,
        auth="none",
        license="Public domain",
        extra=extra or {},
    )


@pytest.mark.asyncio
async def test_search_maps_records():
    reply = {
        "query": {
            "pages": [
                _page(
                    111,
                    "File:The Trench Warfare on the Western Front, 1914-1918 Q4659.jpg",
                    url="https://upload.wikimedia.org/wikipedia/commons/a/ab/Trench.jpg"
                    "?utm_source=x",
                    desc="<p>A <b>trench</b> scene</p>",
                    artist='<a href="//commons/Ernest_Brooks">Ernest Brooks</a>',
                ),
                _page(
                    222,
                    "File:Belgian refugees 1914 Q27746.jpg",
                    artist="George P. Lewis",
                    date="1914",
                ),
            ]
        }
    }
    http = FakeHttp(lambda params, idx: reply)
    connector = IwmWw1Connector(_descriptor({"categories": ["Cat X"], "max_pages": 1}), http)

    assets = await connector.search("trench Western Front", limit=10)
    assert len(assets) == 2

    first = assets[0]
    assert first.title == "The Trench Warfare on the Western Front, 1914-1918"
    assert first.creator == "Ernest Brooks"
    assert first.description == "A trench scene"
    assert first.year == 1917
    assert first.extra["catalog_ref"] == "Q4659"
    assert first.image_url == "https://upload.wikimedia.org/wikipedia/commons/a/ab/Trench.jpg"
    assert first.thumbnail_url.startswith(
        "https://commons.wikimedia.org/wiki/Special:FilePath/"
    )
    assert first.page_url == (
        "https://commons.wikimedia.org/wiki/"
        "File:The_Trench_Warfare_on_the_Western_Front,_1914-1918_Q4659.jpg"
    )

    params = http.calls[0][1]["params"]
    assert params["action"] == "query"
    assert params["generator"] == "search"
    assert params["gsrnamespace"] == "6"
    assert params["formatversion"] == "2"
    assert params["gsrsearch"].startswith("trench Western Front")
    assert 'incategory:"Cat X"' in params["gsrsearch"]


@pytest.mark.asyncio
async def test_search_keeps_only_open_licences():
    reply = {
        "query": {
            "pages": [
                _page(1, "File:Allowed Q1.jpg", lic="Public domain"),
                _page(2, "File:Restricted Q2.jpg", lic="All rights reserved", copyrighted="True"),
                _page(3, "File:CCBY Q3.jpg", lic="CC BY-SA 4.0"),
            ]
        }
    }
    connector = IwmWw1Connector(
        _descriptor({"categories": ["Cat"], "max_pages": 1}), FakeHttp(reply)
    )

    assets = await connector.search("x", limit=10)
    assert {asset.source_asset_id for asset in assets} == {"1", "3"}


@pytest.mark.asyncio
async def test_search_skips_vector_files():
    reply = {
        "query": {
            "pages": [_page(5, "File:Map Q5.svg", mime="image/svg+xml")],
        }
    }
    connector = IwmWw1Connector(
        _descriptor({"categories": ["Cat"], "max_pages": 1}), FakeHttp(reply)
    )
    assert await connector.search("x", limit=10) == []


@pytest.mark.asyncio
async def test_search_dedupes_across_categories():
    reply = {"query": {"pages": [_page(999, "File:Dup Q999.jpg")]}}
    connector = IwmWw1Connector(
        _descriptor({"categories": ["A", "B"], "max_pages": 1}), FakeHttp(reply)
    )
    assets = await connector.search("x", limit=10)
    assert len(assets) == 1


@pytest.mark.asyncio
async def test_search_follows_continue_tokens():
    def responder(params, idx):
        if idx == 0:
            return {
                "continue": {"gsroffset": 50, "continue": "gsroffset||"},
                "query": {"pages": [_page(1, "File:A Q1.jpg")]},
            }
        return {"query": {"pages": [_page(2, "File:B Q2.jpg")]}}

    http = FakeHttp(responder)
    connector = IwmWw1Connector(_descriptor({"categories": ["Cat"], "max_pages": 5}), http)

    assets = await connector.search("x", limit=10)
    assert len(assets) == 2
    second = http.calls[1][1]["params"]
    assert second["gsroffset"] == "50"
    assert second["continue"] == "gsroffset||"


@pytest.mark.asyncio
async def test_search_handles_empty_result():
    connector = IwmWw1Connector(
        _descriptor({"categories": ["Cat"], "max_pages": 1}),
        FakeHttp({"query": {"pages": []}}),
    )
    assert await connector.search("x", limit=10) == []
