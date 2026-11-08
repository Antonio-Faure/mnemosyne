"""CONTENTdm connector: generic search/singleitem into canonical assets (offline).

Every HTTP call is served by a local ``FakeHttp`` that dispatches on the URL:

* ``.../digital/api/search/searchterm/...``  -> a canned search page per ``start``
* ``.../digital/api/singleitem/collection/<alias>/id/<id>`` -> a canned detail
  (or a raised error to emulate a per-item 404).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources import CONNECTORS
from mnemosyne.sources.contentdm import ContentDmConnector

ROOT = Path(__file__).resolve().parents[1]

TEVA = "https://teva.contentdm.oclc.org"
SCDL = "https://digital.tcl.sc.edu"
INDIANA = "https://indianamemory.contentdm.oclc.org"
BYU = "https://contentdm.lib.byu.edu"
ATLANTA = "https://album.atlantahistorycenter.com"
NORTH_DAKOTA = "https://digitalhorizonsonline.org"
PENN_STATE = "https://digital.libraries.psu.edu"
HILLSBOROUGH = "https://digitalcollections.hcplc.org"
HENNEPIN = "https://digitalcollections.hclib.org"

_SENTINEL = object()


def _descriptor(source_id: str, base: str) -> SourceDescriptor:
    return SourceDescriptor(id=source_id, name=source_id, protocol=Protocol.REST, base_url=base)


def _field(key: str, label: str, value: str) -> dict:
    return {"key": key, "label": label, "value": value}


def _iiif(base: str, alias: str, item_id: str) -> str:
    return f"{base}/iiif/2/{alias}:{item_id}/full/full/0/default.jpg"


def _search_item(
    alias: str,
    item_id: str,
    *,
    item_link=_SENTINEL,
    title: str | None = None,
    thumbnail_uri: str | None = None,
) -> dict:
    item: dict = {"collectionAlias": alias, "itemId": item_id}
    if item_link is _SENTINEL:
        item["itemLink"] = f"/collection/{alias}/id/{item_id}"
    elif item_link is not None:
        item["itemLink"] = item_link
    if title is not None:
        item["title"] = title
    if thumbnail_uri is not None:
        item["thumbnailUri"] = thumbnail_uri
    return item


def _detail(
    *,
    content_type: str = "image/jp2",
    image_uri: str | None = None,
    fields: list[dict] | None = None,
    thumbnail_uri: str | None = None,
) -> dict:
    return {
        "contentType": content_type,
        "imageUri": image_uri,
        "thumbnailUri": thumbnail_uri,
        "fields": fields or [],
    }


def _search_page(items: list[dict], total: int | None = None) -> dict:
    return {"totalResults": len(items) if total is None else total, "items": items}


class FakeHttp:
    def __init__(
        self,
        search_pages: dict[int, dict],
        details: dict[tuple[str, str], object],
    ) -> None:
        self.search_pages = search_pages
        self.details = details
        self.calls: list[tuple[str, dict]] = []

    async def get_json(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if "/digital/api/search/searchterm/" in url:
            start = (kwargs.get("params") or {}).get("start", 0)
            return self.search_pages.get(start, _search_page([]))
        if "/digital/api/singleitem/collection/" in url:
            tail = url.split("/singleitem/collection/", 1)[1]
            alias, _, item_id = tail.partition("/id/")
            result = self.details.get((alias, item_id))
            if isinstance(result, Exception):
                raise result
            if result is None:
                raise RuntimeError(f"404 {url}")
            return result
        raise AssertionError(f"unexpected url: {url}")

    def search_starts(self) -> list[int]:
        return [
            (kw.get("params") or {}).get("start")
            for url, kw in self.calls
            if "/digital/api/search/searchterm/" in url
        ]


def _run(source_id: str, base: str, search_pages, details, *, limit=20, **filters):
    http = FakeHttp(search_pages, details)
    connector = ContentDmConnector(_descriptor(source_id, base), http)
    return connector, http


# --------------------------------------------------------------------------- #
# Per-institution happy paths
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_teva_noc_us_image_is_asset():
    alias, item_id = "p15138coll5", "0"
    fields = [
        _field("title", "Title", "States Rights Gist"),
        _field("creato", "Creator", "Unknown"),
        _field("date", "Date", "1861"),
        _field(
            "rights",
            "Copyright",
            "No copyright - United States: http://rightsstatements.org/vocab/NoC-US/1.0/",
        ),
    ]
    details = {(alias, item_id): _detail(image_uri=_iiif(TEVA, alias, item_id), fields=fields)}
    pages = {0: _search_page([_search_item(alias, item_id)])}
    connector, _ = _run("teva", TEVA, pages, details)

    assets = await connector.search("civil war")

    assert len(assets) == 1
    asset = assets[0]
    assert asset.license == "PDM-1.0"
    assert asset.title == "States Rights Gist"
    assert asset.year == 1861
    assert "!1200,1200" in asset.image_url
    assert "!400,400" in asset.thumbnail_url
    assert asset.image_url.startswith(f"{TEVA}/iiif/2/{alias}:{item_id}/full/!1200,1200/0/")
    assert asset.extra["alias"] == alias
    assert asset.extra["item_id"] == item_id
    assert asset.extra["content_type"] == "image/jp2"
    assert asset.extra["rights_uri"] == "http://rightsstatements.org/vocab/NoC-US/1.0/"
    assert asset.source_id == "teva"


@pytest.mark.asyncio
async def test_atlanta_noc_us_image_is_asset():
    alias, item_id = "p16828coll1", "0"
    fields = [
        _field("title", "Title", "Steam locomotive, Atlanta"),
        _field("date", "Date", "1905"),
        _field(
            "rights",
            "Copyright",
            "No copyright - United States: http://rightsstatements.org/vocab/NoC-US/1.0/",
        ),
    ]
    details = {(alias, item_id): _detail(image_uri=_iiif(ATLANTA, alias, item_id), fields=fields)}
    pages = {0: _search_page([_search_item(alias, item_id)])}
    connector, _ = _run("atlanta", ATLANTA, pages, details)

    assets = await connector.search("steam engine")

    assert len(assets) == 1
    asset = assets[0]
    assert asset.license == "PDM-1.0"
    assert asset.title == "Steam locomotive, Atlanta"
    assert asset.year == 1905
    assert "!1200,1200" in asset.image_url
    assert "!400,400" in asset.thumbnail_url
    assert asset.image_url.startswith(f"{ATLANTA}/iiif/2/{alias}:{item_id}/full/!1200,1200/0/")
    assert asset.extra["alias"] == alias
    assert asset.extra["item_id"] == item_id
    assert asset.extra["content_type"] == "image/jp2"
    assert asset.source_id == "atlanta"


@pytest.mark.asyncio
async def test_scdl_public_domain_is_asset():
    alias, item_id = "p16002coll1", "10"
    fields = [
        _field("title", "Title", "Charleston harbor"),
        _field("rights", "Rights", "Public Domain. For further information, see the library."),
    ]
    details = {(alias, item_id): _detail(image_uri=_iiif(SCDL, alias, item_id), fields=fields)}
    pages = {0: _search_page([_search_item(alias, item_id)])}
    connector, _ = _run("scdl", SCDL, pages, details)

    assets = await connector.search("charleston")

    assert len(assets) == 1
    assert assets[0].license == "PDM-1.0"
    assert assets[0].rights.startswith("Public Domain")


@pytest.mark.asyncio
async def test_noc_us_is_asset():
    alias, item_id = "p15078coll1", "20"
    fields = [
        _field("title", "Title", "Indiana glass negative"),
        _field("rights", "Copyright", "http://rightsstatements.org/vocab/NoC-US/1.0/;"),
    ]
    details = {(alias, item_id): _detail(image_uri=_iiif(INDIANA, alias, item_id), fields=fields)}
    pages = {0: _search_page([_search_item(alias, item_id)])}
    connector, _ = _run("indiana_memory", INDIANA, pages, details)

    assets = await connector.search("glass negative")

    assert len(assets) == 1
    assert assets[0].license == "PDM-1.0"


@pytest.mark.asyncio
async def test_byu_public_domain_is_asset():
    alias, item_id = "p16099coll1", "30"
    fields = [
        _field("title", "Title", "Brigham Young portrait"),
        _field("copyri", "Copyright Status Owner", "Public Domain"),
    ]
    details = {(alias, item_id): _detail(image_uri=_iiif(BYU, alias, item_id), fields=fields)}
    pages = {0: _search_page([_search_item(alias, item_id)])}
    connector, _ = _run("byu", BYU, pages, details)

    assets = await connector.search("portrait")

    assert len(assets) == 1
    assert assets[0].license == "PDM-1.0"


@pytest.mark.asyncio
async def test_north_dakota_in_public_domain_is_asset():
    alias, item_id = "ndsu-npl", "60"
    fields = [
        _field("title", "Title", "Speaking of Steam Rollers"),
        _field("rights", "Rights", "In public domain."),
    ]
    details = {
        (alias, item_id): _detail(image_uri=_iiif(NORTH_DAKOTA, alias, item_id), fields=fields)
    }
    pages = {0: _search_page([_search_item(alias, item_id)])}
    connector, _ = _run("north_dakota", NORTH_DAKOTA, pages, details)

    assets = await connector.search("steam")

    assert len(assets) == 1
    asset = assets[0]
    assert asset.license == "PDM-1.0"
    assert asset.title == "Speaking of Steam Rollers"
    assert "!1200,1200" in asset.image_url
    assert asset.image_url.startswith(f"{NORTH_DAKOTA}/iiif/2/{alias}:{item_id}/full/!1200,1200/0/")
    assert asset.source_id == "north_dakota"


@pytest.mark.asyncio
async def test_penn_state_public_domain_is_asset():
    alias, item_id = "pageol", "52125"
    fields = [
        _field("title", "Title", "Map of Pennsylvania"),
        _field(
            "rights",
            "Rights",
            "Public Domain. This item is made available by Penn State "
            "University Libraries.",
        ),
    ]
    details = {
        (alias, item_id): _detail(image_uri=_iiif(PENN_STATE, alias, item_id), fields=fields)
    }
    pages = {0: _search_page([_search_item(alias, item_id)])}
    connector, _ = _run("penn_state", PENN_STATE, pages, details)

    assets = await connector.search("map")

    assert len(assets) == 1
    asset = assets[0]
    assert asset.license == "PDM-1.0"
    assert asset.title == "Map of Pennsylvania"
    assert "!1200,1200" in asset.image_url
    assert asset.image_url.startswith(
        f"{PENN_STATE}/iiif/2/{alias}:{item_id}/full/!1200,1200/0/"
    )
    assert "!400,400" in asset.thumbnail_url
    assert asset.source_id == "penn_state"


@pytest.mark.asyncio
async def test_hillsborough_public_domain_portrait_is_asset():
    alias, item_id = "p15140coll1", "42"
    fields = [
        _field("title", "Title", "Portrait of a Tampa family"),
        _field("date", "Date", "1898"),
        _field(
            "rights",
            "Rights",
            "Public Domain. This item is in the public domain; credit: "
            "Tampa-Hillsborough County Public Library.",
        ),
    ]
    details = {
        (alias, item_id): _detail(image_uri=_iiif(HILLSBOROUGH, alias, item_id), fields=fields)
    }
    pages = {0: _search_page([_search_item(alias, item_id)])}
    connector, _ = _run("hillsborough", HILLSBOROUGH, pages, details)

    assets = await connector.search("portrait")

    assert len(assets) == 1
    asset = assets[0]
    assert asset.license == "PDM-1.0"
    assert "!1200,1200" in asset.image_url
    assert "!400,400" in asset.thumbnail_url
    assert asset.image_url.startswith(
        f"{HILLSBOROUGH}/iiif/2/{alias}:{item_id}/full/!1200,1200/0/"
    )
    assert asset.source_id == "hillsborough"


@pytest.mark.asyncio
async def test_hennepin_noc_us_lake_is_asset():
    alias, item_id = "p16094coll1", "7"
    fields = [
        _field("title", "Title", "Lake Calhoun, Minneapolis"),
        _field("date", "Date", "1905"),
        _field(
            "rights",
            "Rights",
            "No Copyright - United States: http://rightsstatements.org/vocab/NoC-US/1.0/",
        ),
    ]
    oclc_uri = f"{HENNEPIN}/api/singleitem/image/{alias}/{item_id}/default.jpg"
    details = {(alias, item_id): _detail(image_uri=oclc_uri, fields=fields)}
    pages = {0: _search_page([_search_item(alias, item_id)])}
    connector, _ = _run("hennepin", HENNEPIN, pages, details)

    assets = await connector.search("lake")

    assert len(assets) == 1
    asset = assets[0]
    assert asset.license == "PDM-1.0"
    assert "api/singleitem/image/" not in asset.image_url
    assert asset.image_url == (
        f"{HENNEPIN}/digital/iiif/2/{alias}:{item_id}/full/!1200,1200/0/default.jpg"
    )
    assert asset.thumbnail_url == (
        f"{HENNEPIN}/digital/iiif/2/{alias}:{item_id}/full/!400,400/0/default.jpg"
    )
    assert asset.source_id == "hennepin"


@pytest.mark.asyncio
async def test_hennepin_oclc_image_uri_is_rebuilt_as_iiif():
    """Regression: Hennepin's /api/singleitem/image/ imageUri 403s -> rebuild IIIF."""
    alias, item_id = "p1", "1"
    fields = [
        _field("title", "Title", "Hennepin lake"),
        _field(
            "rights",
            "Rights",
            "No Copyright - United States: http://rightsstatements.org/vocab/NoC-US/1.0/",
        ),
    ]
    details = {
        (alias, item_id): _detail(
            image_uri="/api/singleitem/image/p1/1/default.jpg", fields=fields
        )
    }
    pages = {0: _search_page([_search_item(alias, item_id)])}
    connector, _ = _run("hennepin", HENNEPIN, pages, details)

    assets = await connector.search("lake")

    assert len(assets) == 1
    asset = assets[0]
    assert asset.image_url == (
        f"{HENNEPIN}/digital/iiif/2/p1:1/full/!1200,1200/0/default.jpg"
    )
    assert asset.thumbnail_url == (
        f"{HENNEPIN}/digital/iiif/2/p1:1/full/!400,400/0/default.jpg"
    )


@pytest.mark.asyncio
async def test_cc0_rights_yield_cc0_license():
    alias, item_id = "p1", "1"
    fields = [
        _field("title", "Title", "CC0 item"),
        _field("rights", "Rights", "CC0 1.0 Universal Public Domain Dedication"),
    ]
    details = {(alias, item_id): _detail(image_uri=_iiif(TEVA, alias, item_id), fields=fields)}
    pages = {0: _search_page([_search_item(alias, item_id)])}
    connector, _ = _run("teva", TEVA, pages, details)

    assets = await connector.search("cc0")

    assert len(assets) == 1
    assert assets[0].license == "CC0-1.0"


# --------------------------------------------------------------------------- #
# Rights rejections
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rights_value",
    [
        "Copyright not evaluated",
        "All rights reserved",
        "CC BY-NC 4.0",
        "In Copyright",
        "Copyright Undetermined",
    ],
)
async def test_bad_rights_are_ignored(rights_value):
    alias, item_id = "p1", "1"
    fields = [
        _field("title", "Title", "Rejected"),
        _field("rights", "Rights", rights_value),
    ]
    details = {(alias, item_id): _detail(image_uri=_iiif(TEVA, alias, item_id), fields=fields)}
    pages = {0: _search_page([_search_item(alias, item_id)])}
    connector, _ = _run("teva", TEVA, pages, details)

    assert await connector.search("anything") == []


@pytest.mark.asyncio
async def test_missing_rights_are_ignored():
    # No rights field at all -> not explicitly open -> rejected.
    alias, item_id = "p1", "1"
    fields = [_field("title", "Title", "No rights stated")]
    details = {(alias, item_id): _detail(image_uri=_iiif(TEVA, alias, item_id), fields=fields)}
    pages = {0: _search_page([_search_item(alias, item_id)])}
    connector, _ = _run("teva", TEVA, pages, details)

    assert await connector.search("anything") == []


@pytest.mark.asyncio
async def test_public_domain_with_contact_note_is_open():
    # "please contact the library" is informational, not a restriction.
    alias, item_id = "p1", "1"
    fields = [
        _field(
            "rights",
            "Rights",
            "Public Domain. For further information please contact South "
            "Caroliniana Library, Columbia, SC.",
        )
    ]
    details = {(alias, item_id): _detail(image_uri=_iiif(SCDL, alias, item_id), fields=fields)}
    pages = {0: _search_page([_search_item(alias, item_id)])}
    connector, _ = _run("scdl", SCDL, pages, details)

    assets = await connector.search("map")

    assert len(assets) == 1
    assert assets[0].license == "PDM-1.0"


@pytest.mark.asyncio
async def test_restrictive_personal_educational_statement_is_rejected():
    # NoC-US is present, but the use statement limits reuse to personal /
    # educational / not-for-profit purposes -> reject.
    alias, item_id = "p1", "1"
    fields = [
        _field(
            "rights",
            "Rights",
            "http://rightsstatements.org/vocab/NoC-US/1.0/; This image may be "
            "used for personal, educational, and not-for-profit purposes until "
            "further notice; for other uses contact the museum.",
        )
    ]
    details = {(alias, item_id): _detail(image_uri=_iiif(INDIANA, alias, item_id), fields=fields)}
    pages = {0: _search_page([_search_item(alias, item_id)])}
    connector, _ = _run("indiana_memory", INDIANA, pages, details)

    assert await connector.search("portrait") == []


@pytest.mark.asyncio
async def test_http_image_uri_is_upgraded_to_https():
    alias, item_id = "p1", "1"
    fields = [_field("rights", "Rights", "Public Domain")]
    http_uri = f"http://teva.contentdm.oclc.org/iiif/2/{alias}:{item_id}/full/full/0/default.jpg"
    details = {(alias, item_id): _detail(image_uri=http_uri, fields=fields)}
    pages = {0: _search_page([_search_item(alias, item_id)])}
    connector, _ = _run("teva", TEVA, pages, details)

    assets = await connector.search("engine")

    assert len(assets) == 1
    assert assets[0].image_url.startswith("https://teva.contentdm.oclc.org/")
    assert "!1200,1200" in assets[0].image_url
    assert "!400,400" in assets[0].thumbnail_url


# --------------------------------------------------------------------------- #
# Image filter rejections
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_pdf_content_type_is_ignored():
    alias, item_id = "p1", "1"
    fields = [_field("rights", "Rights", "Public Domain")]
    details = {
        (alias, item_id): _detail(
            content_type="application/pdf",
            image_uri=_iiif(TEVA, alias, item_id),
            fields=fields,
        )
    }
    pages = {0: _search_page([_search_item(alias, item_id)])}
    connector, _ = _run("teva", TEVA, pages, details)

    assert await connector.search("pdf") == []


@pytest.mark.asyncio
async def test_null_image_uri_is_ignored():
    alias, item_id = "p1", "1"
    fields = [_field("rights", "Rights", "Public Domain")]
    details = {(alias, item_id): _detail(content_type="image/jp2", image_uri=None, fields=fields)}
    pages = {0: _search_page([_search_item(alias, item_id)])}
    connector, _ = _run("teva", TEVA, pages, details)

    assert await connector.search("null") == []


# --------------------------------------------------------------------------- #
# Robustness: a 404 single-item must not abort the run
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_singleitem_404_does_not_abort_others():
    fields_ok = [_field("rights", "Rights", "Public Domain")]
    details = {
        ("p1", "0"): RuntimeError("404 not found"),
        ("p1", "1"): _detail(image_uri=_iiif(TEVA, "p1", "1"), fields=fields_ok),
    }
    pages = {
        0: _search_page([_search_item("p1", "0"), _search_item("p1", "1")], total=2),
    }
    connector, _ = _run("teva", TEVA, pages, details)

    assets = await connector.search("resilient")

    assert len(assets) == 1
    assert assets[0].extra["item_id"] == "1"


# --------------------------------------------------------------------------- #
# Pagination + limit + dedupe
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_pagination_requests_second_page():
    fields_ok = [_field("rights", "Rights", "Public Domain")]
    details = {
        ("p1", "0"): _detail(image_uri=_iiif(TEVA, "p1", "0"), fields=fields_ok),
        ("p1", "1"): _detail(image_uri=_iiif(TEVA, "p1", "1"), fields=fields_ok),
    }
    pages = {
        0: _search_page([_search_item("p1", "0")], total=11),
        10: _search_page([_search_item("p1", "1")], total=11),
    }
    connector, http = _run("teva", TEVA, pages, details)

    assets = await connector.search("paginate", limit=20, max_pages=3)

    assert len(assets) == 2
    assert http.search_starts() == [0, 10]


@pytest.mark.asyncio
async def test_limit_is_respected():
    fields_ok = [_field("rights", "Rights", "Public Domain")]
    details = {
        ("p1", str(i)): _detail(image_uri=_iiif(TEVA, "p1", str(i)), fields=fields_ok)
        for i in range(5)
    }
    pages = {0: _search_page([_search_item("p1", str(i)) for i in range(5)], total=5)}
    connector, _ = _run("teva", TEVA, pages, details)

    assets = await connector.search("limit", limit=2)

    assert len(assets) == 2


@pytest.mark.asyncio
async def test_duplicates_are_deduplicated():
    fields_ok = [_field("rights", "Rights", "Public Domain")]
    details = {("p1", "0"): _detail(image_uri=_iiif(TEVA, "p1", "0"), fields=fields_ok)}
    # the same (alias, item) appears twice on the page
    pages = {0: _search_page([_search_item("p1", "0"), _search_item("p1", "0")], total=2)}
    connector, _ = _run("teva", TEVA, pages, details)

    assets = await connector.search("dupes")

    assert len(assets) == 1


# --------------------------------------------------------------------------- #
# Metadata mapping / truncation / page_url
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_metadata_mapping_and_truncation():
    alias, item_id = "p1", "1"
    long_desc = "x" * 900
    fields = [
        _field("title", "Title", "Mapped title"),
        _field("creato", "Creator", "Jane Doe"),
        _field("date", "Date", "1899"),
        _field("descri", "Description", long_desc),
        _field("rights", "Rights", "Public Domain"),
    ]
    details = {(alias, item_id): _detail(image_uri=_iiif(TEVA, alias, item_id), fields=fields)}
    pages = {0: _search_page([_search_item(alias, item_id)])}
    connector, _ = _run("teva", TEVA, pages, details)

    assets = await connector.search("mapping")

    assert len(assets) == 1
    asset = assets[0]
    assert asset.title == "Mapped title"
    assert asset.creator == "Jane Doe"
    assert asset.date_text == "1899"
    assert asset.year == 1899
    assert len(asset.description) == 600


@pytest.mark.asyncio
async def test_title_falls_back_to_item_title():
    alias, item_id = "p1", "1"
    fields = [_field("rights", "Rights", "Public Domain")]
    details = {(alias, item_id): _detail(image_uri=_iiif(TEVA, alias, item_id), fields=fields)}
    pages = {0: _search_page([_search_item(alias, item_id, title="Item title")])}
    connector, _ = _run("teva", TEVA, pages, details)

    assets = await connector.search("title fallback")

    assert assets[0].title == "Item title"


@pytest.mark.asyncio
async def test_page_url_from_item_link_and_fallback():
    fields_ok = [_field("rights", "Rights", "Public Domain")]
    details = {
        ("p1", "0"): _detail(image_uri=_iiif(TEVA, "p1", "0"), fields=fields_ok),
        ("p1", "1"): _detail(image_uri=_iiif(TEVA, "p1", "1"), fields=fields_ok),
    }
    item_with_link = _search_item("p1", "0", item_link="/collection/p1/id/0")
    item_without_link = _search_item("p1", "1", item_link=None)
    pages = {0: _search_page([item_with_link, item_without_link], total=2)}
    connector, _ = _run("teva", TEVA, pages, details)

    assets = await connector.search("page url")

    by_id = {a.extra["item_id"]: a for a in assets}
    assert by_id["0"].page_url == f"{TEVA}/digital/collection/p1/id/0"
    assert by_id["1"].page_url == f"{TEVA}/digital/collection/p1/id/1"


# --------------------------------------------------------------------------- #
# Descriptors + registry
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("source_id", "base_url"),
    [
        ("atlanta", ATLANTA),
        ("byu", BYU),
        ("hennepin", HENNEPIN),
        ("hillsborough", HILLSBOROUGH),
        ("north_dakota", NORTH_DAKOTA),
        ("penn_state", PENN_STATE),
        ("scdl", SCDL),
        ("teva", TEVA),
    ],
)
def test_descriptor_deserializes_and_is_registered(source_id, base_url):
    raw = yaml.safe_load((ROOT / "config" / "sources" / f"{source_id}.yaml").read_text("utf-8"))
    descriptor = SourceDescriptor(**raw)

    assert descriptor.id == source_id
    assert descriptor.protocol == Protocol.REST
    assert descriptor.base_url == base_url
    assert descriptor.auth == "none"
    assert descriptor.enabled is True
    assert descriptor.license
    assert CONNECTORS[source_id] is ContentDmConnector


def test_all_contentdm_sources_registered():
    for source_id in (
        "atlanta",
        "byu",
        "hennepin",
        "hillsborough",
        "north_dakota",
        "penn_state",
        "scdl",
        "teva",
    ):
        assert CONNECTORS[source_id] is ContentDmConnector
