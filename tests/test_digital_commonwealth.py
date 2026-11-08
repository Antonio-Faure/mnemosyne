"""Digital Commonwealth connector: normalization, rights filter, IIIF, paging.

All network I/O is faked: the Blacklight JSON shape is replayed locally so the
tests exercise only the connector's normalization logic.
"""

from __future__ import annotations

from typing import Any

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.digital_commonwealth import DigitalCommonwealthConnector

IIIF = "https://iiif.digitalcommonwealth.org/iiif/2"


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="digital_commonwealth",
        name="Digital Commonwealth — Massachusetts Collections",
        institution="Digital Commonwealth (Massachusetts)",
        country="US",
        protocol=Protocol.REST,
        base_url="https://www.digitalcommonwealth.org",
        auth="none",
        license="PDM-1.0",
        rights="No known copyright restrictions",
        rate_limit_per_s=1.0,
        priority=50,
    )


def _open_attrs(**overrides: Any) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "title_info_primary_tsi": "Whaling ship at New Bedford",
        "subject_name_tsim": ["Bourne, Edward", "New Bedford Whaling"],
        "date_tsim": ["1850"],
        "date_start_dtsi": "1850-01-01",
        "date_edtf_ssm": "1850",
        "note_tsim": ["A whaling vessel at anchor.", "Photograph, 1850."],
        "rights_ss": "No known copyright restrictions.",
        "license_ss": "",
        "reuse_allowed_ssi": "no restrictions",
        "institution_name_ssi": "New Bedford Free Public Library",
        "collection_name_ssim": ["Whaling Collection"],
        "identifier_uri_ss": "https://ark.digitalcommonwealth.org/ark:/50959/abc123",
        "exemplary_image_key_base_ss": "images/commonwealth:qj72pd28f",
    }
    attrs.update(overrides)
    return attrs


def _doc(doc_id: str, attrs: dict[str, Any]) -> dict[str, Any]:
    return {"id": doc_id, "type": "DigitalObject", "attributes": attrs}


def _payload(docs: list[dict[str, Any]], total_pages: int = 1) -> dict[str, Any]:
    return {
        "links": {},
        "meta": {
            "pages": {
                "current_page": 1,
                "total_pages": total_pages,
                "total_count": len(docs),
                "limit_value": 20,
            }
        },
        "data": docs,
    }


class FakeHttp:
    """Returns canned Blacklight payloads (one per page when given a list)."""

    def __init__(self, pages: Any):
        # pages: a single payload dict (replayed for every page) or a list of
        # payloads indexed by page number (page 1, 2, …).
        self.pages = pages
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        if isinstance(self.pages, list):
            page = int(kwargs["params"]["page"])
            return self.pages[page - 1] if page - 1 < len(self.pages) else {"data": []}
        return self.pages


async def test_open_item_with_image_becomes_asset():
    http = FakeHttp(_payload([_doc("commonwealth:abc123", _open_attrs())]))
    connector = DigitalCommonwealthConnector(_descriptor(), http)

    assets = await connector.search("whaling", limit=10)

    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_id == "digital_commonwealth"
    assert asset.source_asset_id == "commonwealth:abc123"
    assert asset.title == "Whaling ship at New Bedford"
    assert asset.creator == "Bourne, Edward, New Bedford Whaling"
    assert asset.year == 1850
    assert asset.license == "PDM-1.0"
    assert asset.rights == "No known copyright restrictions."
    assert asset.page_url == "https://ark.digitalcommonwealth.org/ark:/50959/abc123"
    assert asset.extra["institution"] == "New Bedford Free Public Library"
    assert asset.extra["collection"] == ["Whaling Collection"]
    assert asset.extra["reuse_allowed"] == "no restrictions"
    assert asset.extra["iiif_image_id"] == "commonwealth:qj72pd28f"
    assert asset.extra["ark_id"] == "https://ark.digitalcommonwealth.org/ark:/50959/abc123"


async def test_contact_host_notice_is_ignored():
    attrs = _open_attrs(
        reuse_allowed_ssi="contact host",
        rights_ss="Rights status not evaluated",
        license_ss="",
    )
    http = FakeHttp(_payload([_doc("commonwealth:closed", attrs)]))
    connector = DigitalCommonwealthConnector(_descriptor(), http)

    assert await connector.search("whaling") == []


async def test_metadata_image_key_is_ignored():
    attrs = _open_attrs(exemplary_image_key_base_ss="metadata/commonwealth:nope")
    http = FakeHttp(_payload([_doc("commonwealth:m1", attrs)]))
    connector = DigitalCommonwealthConnector(_descriptor(), http)

    assert await connector.search("whaling") == []


async def test_notice_without_image_key_is_ignored():
    attrs = _open_attrs()
    attrs.pop("exemplary_image_key_base_ss")
    http = FakeHttp(_payload([_doc("commonwealth:noimg", attrs)]))
    connector = DigitalCommonwealthConnector(_descriptor(), http)

    assert await connector.search("whaling") == []


async def test_empty_response_returns_nothing():
    http = FakeHttp(_payload([]))
    connector = DigitalCommonwealthConnector(_descriptor(), http)

    assert await connector.search("whaling") == []
    # one page fetched, then the empty page stops pagination
    assert len(http.calls) == 1


async def test_limit_caps_results_and_per_page():
    docs = [_doc(f"commonwealth:{i}", _open_attrs()) for i in range(5)]
    http = FakeHttp(_payload(docs, total_pages=5))
    connector = DigitalCommonwealthConnector(_descriptor(), http)

    assets = await connector.search("whaling", limit=2)

    assert len(assets) == 2
    url, kwargs = http.calls[0]
    assert url == "https://www.digitalcommonwealth.org/search.json"
    assert kwargs["params"] == {"q": "whaling", "per_page": "10", "page": "1"}


async def test_pagination_walks_to_page_two():
    page1 = _payload([_doc("commonwealth:p1", _open_attrs())], total_pages=2)
    page2 = _payload([_doc("commonwealth:p2", _open_attrs())], total_pages=2)
    http = FakeHttp([page1, page2])
    connector = DigitalCommonwealthConnector(_descriptor(), http)

    assets = await connector.search("whaling", limit=10)

    assert [a.source_asset_id for a in assets] == ["commonwealth:p1", "commonwealth:p2"]
    assert len(http.calls) == 2
    assert http.calls[0][1]["params"]["page"] == "1"
    assert http.calls[1][1]["params"]["page"] == "2"


async def test_iiif_urls_use_1200_and_400_sizes():
    attrs = _open_attrs(exemplary_image_key_base_ss="images/commonwealth:qj72pd28f")
    http = FakeHttp(_payload([_doc("commonwealth:abc", attrs)]))
    connector = DigitalCommonwealthConnector(_descriptor(), http)

    asset = (await connector.search("whaling"))[0]

    assert asset.image_url == f"{IIIF}/commonwealth:qj72pd28f/full/!1200,1200/0/default.jpg"
    assert asset.thumbnail_url == f"{IIIF}/commonwealth:qj72pd28f/full/!400,400/0/default.jpg"


async def test_rights_filter_is_case_insensitive():
    by_reuse = _open_attrs(reuse_allowed_ssi="No Restrictions", rights_ss="")
    by_rights = _open_attrs(reuse_allowed_ssi="", rights_ss="NO KNOWN COPYRIGHT RESTRICTIONS")
    by_license = _open_attrs(
        reuse_allowed_ssi="", rights_ss="", license_ss="no known restrictions on use"
    )
    by_cc0 = _open_attrs(
        reuse_allowed_ssi="", rights_ss="", license_ss="CC0 1.0 Universal (CC0 1.0)"
    )
    closed = _open_attrs(reuse_allowed_ssi="Rights status not evaluated", rights_ss="")
    docs = [
        _doc("commonwealth:reuse", by_reuse),
        _doc("commonwealth:rights", by_rights),
        _doc("commonwealth:license", by_license),
        _doc("commonwealth:cc0", by_cc0),
        _doc("commonwealth:closed", closed),
    ]
    http = FakeHttp(_payload(docs))
    connector = DigitalCommonwealthConnector(_descriptor(), http)

    ids = [a.source_asset_id for a in await connector.search("whaling", limit=10)]

    assert ids == [
        "commonwealth:reuse",
        "commonwealth:rights",
        "commonwealth:license",
        "commonwealth:cc0",
    ]


async def test_date_and_creator_mapping_and_fallbacks():
    attrs = _open_attrs(
        title_info_primary_tsi=None,
        subject_name_tsim=None,
        date_tsim=[],
        date_start_dtsi=None,
        date_edtf_ssm="1901/1905",
        note_tsim=None,
        identifier_uri_ss=None,
    )
    http = FakeHttp(_payload([_doc("commonwealth:dates", attrs)]))
    connector = DigitalCommonwealthConnector(_descriptor(), http)

    asset = (await connector.search("whaling"))[0]

    # title falls back to id, creator to institution, page to /search/<id>
    assert asset.title == "Digital Commonwealth commonwealth:dates"
    assert asset.creator == "New Bedford Free Public Library"
    assert asset.page_url == "https://www.digitalcommonwealth.org/search/commonwealth:dates"
    assert asset.date_text == "1901/1905"
    assert asset.year == 1901
    assert asset.description == ""


async def test_description_and_date_are_joined():
    attrs = _open_attrs(
        note_tsim=["Note one.", "Note two."],
        date_tsim=["1850", "1851"],
        date_start_dtsi=None,
    )
    http = FakeHttp(_payload([_doc("commonwealth:join", attrs)]))
    connector = DigitalCommonwealthConnector(_descriptor(), http)

    asset = (await connector.search("whaling"))[0]

    assert asset.description == "Note one. ; Note two."
    assert asset.date_text == "1850 ; 1851"
    assert asset.year == 1850
