"""Offline tests for the POP (Plateforme ouverte du patrimoine) connector.

Everything is mocked: a :class:`_FakeHttp` returns canned JSON payloads, so no
network call is ever made. The tests exercise the unit-level helpers (rights
detection, image-path extraction, IIIF/URL builders, manifest and facet
parsing) and the full ``search`` normalization + pagination path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mnemosyne.models import SourceDescriptor
from mnemosyne.sources import build_connector
from mnemosyne.sources import pop as pop_mod
from mnemosyne.sources.pop import (
    PopConnector,
    bucket_url,
    facet_buckets,
    iiif_image_url,
    iiif_info_url,
    iiif_service_id,
    iiif_thumb_url,
    is_restrictive,
    manifest_image_services,
    notice_image_paths,
)

POP_YAML = Path(__file__).resolve().parents[1] / "config" / "sources" / "pop.yaml"

_MEMOIRE_RESTRICTIVE: dict[str, Any] = {
    "_source": {
        "REF": "SAPR44_20235700043",
        "TITRE": "Usine sidérurgique",
        "IMG": "memoire/SAPR44_20235700043/photo.jpg",
        "COPY": "© Région Provence-Alpes-Côte d'Azur",
        "DIFF": "tous droits réservés",
        "CONTIENT_IMAGE": "oui",
    }
}
_MEMOIRE_FREE: dict[str, Any] = {
    "_source": {
        "REF": "AP80L05579",
        "LEG": "Domaine public",
        "IMG": "memoire/AP80L05579/photo.jpg",
        "COPY": "Domaine public",
        "DIFF": "Domaine public",
        "CONTIENT_IMAGE": "oui",
    }
}
_JOCONDE_HIT: dict[str, Any] = {
    "_source": {
        "REF": "50000000001",
        "TITRE": "Machine à vapeur",
        "IMG": ["joconde/50000000001/a.jpg", "joconde/50000000001/b.jpg"],
        "DIFFU": "oui",
        "COPY": "Domaine public",
    }
}

_MANIFEST: dict[str, Any] = {
    "type": "Manifest",
    "items": [
        {
            "type": "Canvas",
            "items": [
                {
                    "type": "AnnotationPage",
                    "items": [
                        {
                            "type": "Annotation",
                            "body": {
                                "type": "Image",
                                "service": [
                                    {
                                        "id": "https://iiif.prd.cloud.culture.fr/iiif/3/"
                                        "memoire%2FSAPR44_20235700043%2Fphoto.jpg",
                                        "type": "ImageService3",
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
    ],
}

_FACETS: dict[str, Any] = {
    "total": 1200000,
    "aggregations": {
        "DIFF.keyword": {
            "buckets": [
                {"key": "reproduction soumise à autorisation", "doc_count": 1018341},
                {"key": "tous droits réservés", "doc_count": 5494},
                {"key": "Domaine public", "doc_count": 3},
            ]
        }
    },
}


class _FakeHttp:
    """Routes requests to canned payloads by URL substring; never touches the net."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self._routes = routes
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        for needle, payload in self._routes.items():
            if needle in url:
                if callable(payload):
                    return payload(url, kwargs)
                return payload
        raise AssertionError(f"unexpected URL in offline test: {url}")


def _raw() -> dict[str, Any]:
    return yaml.safe_load(POP_YAML.read_text(encoding="utf-8"))


def _descriptor(**extra: Any) -> SourceDescriptor:
    raw = _raw()
    raw["extra"] = {**raw.get("extra", {}), **extra}
    return SourceDescriptor(**raw)


# ── descriptor wiring ────────────────────────────────────────────────────────
def test_pop_descriptor_is_keyless_iiif_and_disabled():
    raw = _raw()
    assert raw["id"] == "pop"
    assert raw["protocol"] == "iiif"
    assert raw["auth"] == "none"
    assert raw["enabled"] is False
    assert raw["license"] == "Licence Ouverte 2.0 (etalab)"
    assert "api.pop.culture.gouv.fr" in raw["base_url"]
    assert raw["extra"]["databases"] == ["memoire", "joconde"]


def test_pop_uses_registered_connector():
    assert isinstance(build_connector(_descriptor(), _FakeHttp({})), PopConnector)


# ── pure helpers ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "src,expected",
    [
        ({"DIFF": "Domaine public"}, False),
        ({"DIFF": "Licence Ouverte 2.0 (etalab)"}, False),
        ({"DIFF": "tous droits réservés"}, True),
        ({"DIFF": "reproduction soumise à autorisation"}, True),
        ({"DIFF": "communication libre, reproduction soumise à autorisation"}, True),
        ({"DIFFU": "non"}, True),
        ({"DIFFU": "oui", "COPY": "© RMN-Grand Palais"}, True),
        ({}, True),  # conservative default: no free signal
    ],
)
def test_is_restrictive(src: dict[str, Any], expected: bool):
    assert is_restrictive(src) is expected


def test_notice_image_paths_handles_string_and_list():
    assert notice_image_paths({"IMG": "memoire/R/f.jpg"}) == ["memoire/R/f.jpg"]
    assert notice_image_paths({"IMG": ["a.jpg", "b.jpg"]}) == ["a.jpg", "b.jpg"]
    assert notice_image_paths({"IMG": None}) == []
    assert notice_image_paths({}) == []


def test_iiif_and_bucket_urls_are_built_from_the_path():
    path = "memoire/SAPR44_20235700043/photo.jpg"
    enc = "memoire%2FSAPR44_20235700043%2Fphoto.jpg"
    assert iiif_service_id(path) == f"https://iiif.prd.cloud.culture.fr/iiif/3/{enc}"
    assert iiif_info_url(path).endswith(f"/{enc}/info.json")
    assert iiif_image_url(path).endswith(f"/{enc}/full/max/0/default.jpg")
    assert iiif_thumb_url(path).endswith(f"/{enc}/full/200,/0/default.jpg")
    assert bucket_url(path) == (
        "https://popcorn-prd-perf-assets.s3.gra.io.cloud.ovh.net/" + path
    )


def test_manifest_image_services_extracts_service_id():
    assert manifest_image_services(_MANIFEST) == [
        "https://iiif.prd.cloud.culture.fr/iiif/3/memoire%2FSAPR44_20235700043%2Fphoto.jpg"
    ]
    assert manifest_image_services({}) == []


def test_facet_buckets_normalizes_aggregations():
    parsed = facet_buckets(_FACETS)
    top = parsed["DIFF.keyword"][0]
    assert top == {"key": "reproduction soumise à autorisation", "count": 1018341}
    assert parsed["DIFF.keyword"][-1] == {"key": "Domaine public", "count": 3}
    assert facet_buckets({}) == {}


# ── search: parsing + pagination ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_search_parses_records_and_paginates():
    def simple(url: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        params = kwargs.get("params") or {}
        if params.get("bases[0]") != "memoire":
            return {"total": 0, "hits": []}
        # same page for every offset -> dedup keeps 2 records, offset advances
        return {"total": 4, "hits": [_MEMOIRE_RESTRICTIVE, _MEMOIRE_FREE]}

    http = _FakeHttp({"/search/simple": simple})
    connector = PopConnector(_descriptor(databases=["memoire"], page_size=2), http)

    assets = await connector.search("usine", limit=10)

    assert len(assets) == 2
    by_ref = {a.source_asset_id: a for a in assets}
    restricted = by_ref["memoire/SAPR44_20235700043"]
    free = by_ref["memoire/AP80L05579"]

    # per-notice restrictive flag
    assert restricted.extra["restrictive"] is True
    assert free.extra["restrictive"] is False

    # image URL only for the free notice, never for the restricted one
    assert restricted.image_url is None
    assert restricted.thumbnail_url is None
    assert restricted.extra["bucket_url"] is None
    assert free.image_url == iiif_image_url("memoire/AP80L05579/photo.jpg")
    assert free.thumbnail_url == iiif_thumb_url("memoire/AP80L05579/photo.jpg")
    assert free.iiif_id == iiif_service_id("memoire/AP80L05579/photo.jpg")

    # metadata is Open Licence, rights carry the per-notice text
    assert free.license == "Licence Ouverte 2.0 (etalab)"
    assert restricted.rights and "tous droits" in restricted.rights
    assert free.page_url == "https://pop.culture.gouv.fr/notice/memoire/AP80L05579"

    # pagination: the offset advanced across two pages
    offsets = [c[1]["params"]["from"] for c in http.calls]
    assert offsets == [0, 2]
    assert all(c[1]["params"]["bases[0]"] == "memoire" for c in http.calls)
    assert all(c[1]["params"]["filters[hasImage]"] == "true" for c in http.calls)


@pytest.mark.asyncio
async def test_search_joconde_collects_multiple_image_paths():
    def simple(url: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        params = kwargs.get("params") or {}
        if params.get("bases[0]") != "joconde":
            return {"total": 0, "hits": []}
        return {"total": 1, "hits": [_JOCONDE_HIT]}

    http = _FakeHttp({"/search/simple": simple})
    connector = PopConnector(_descriptor(databases=["joconde"], page_size=10), http)

    assets = await connector.search("machine", limit=5)

    assert len(assets) == 1
    asset = assets[0]
    assert asset.source_asset_id == "joconde/50000000001"
    assert asset.extra["image_paths"] == [
        "joconde/50000000001/a.jpg",
        "joconde/50000000001/b.jpg",
    ]
    # free (COPY "Domaine public") -> first path drives the image URL
    assert asset.image_url == iiif_image_url("joconde/50000000001/a.jpg")


@pytest.mark.asyncio
async def test_search_without_query_iterates_industrial_terms():
    seen_terms: list[str] = []

    def simple(url: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        params = kwargs.get("params") or {}
        if params.get("bases[0]") == "memoire":
            seen_terms.append(params.get("text"))
        return {"total": 0, "hits": []}

    http = _FakeHttp({"/search/simple": simple})
    connector = PopConnector(_descriptor(databases=["memoire"]), http)

    await connector.search("", limit=5)

    assert seen_terms[: len(pop_mod.INDUSTRIAL_TERMS)] == list(pop_mod.INDUSTRIAL_TERMS)


# ── per-notice IIIF manifest + facets endpoints ──────────────────────────────
@pytest.mark.asyncio
async def test_image_services_reads_the_iiif_manifest():
    http = _FakeHttp({"/iiif/manifest": _MANIFEST})
    connector = PopConnector(_descriptor(), http)

    services = await connector.image_services("memoire", "SAPR44_20235700043")

    assert services == [
        "https://iiif.prd.cloud.culture.fr/iiif/3/memoire%2FSAPR44_20235700043%2Fphoto.jpg"
    ]
    assert http.calls[0][0].endswith("/notices/memoire/SAPR44_20235700043/iiif/manifest")


@pytest.mark.asyncio
async def test_facets_parses_buckets():
    http = _FakeHttp({"/search/facets": _FACETS})
    connector = PopConnector(_descriptor(), http)

    buckets = await connector.facets("usine", db="memoire")

    assert buckets["DIFF.keyword"][0]["count"] == 1018341
    assert http.calls[0][1]["params"]["bases[0]"] == "memoire"
