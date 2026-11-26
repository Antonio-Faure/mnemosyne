"""La Contemporaine / L'Argonnaute — relevance tolerance for long Resolver
phrases (offline). Complements ``tests/test_la_contemporaine_argonnaute.py``.

The curated seed list must stay useful for long, inflected Resolver phrases
(e.g. « ouvriers Citroën grèves 1930 ») **without** leaking curated photos into
unrelated searches. We lock that in here: plural/singular equivalence,
decade-year matching, and the « no overlap -> dropped » guard.
"""

from __future__ import annotations

import pytest

from mnemosyne.models import Protocol, SourceDescriptor
from mnemosyne.sources.la_contemporaine_argonnaute import (
    LaContemporaineArgonnauteConnector,
    _tokens,
)

BASE = "https://argonnaute.parisnanterre.fr"

GREVE = ("grv0000001", "11111111-1111-1111-1111-111111111111")
CITROEN = ("cit0000001", "22222222-2222-2222-2222-222222222222")
FERME = ("frm0000001", "33333333-3333-3333-3333-333333333333")


def _doc(ark, uuid, title, date_from, date_to, keywords=None, ref=None):
    return {
        "media": [
            {
                "url": f"{BASE}/ark:/14707/{ark}/{uuid}",
                "record": {
                    "arkId": {"arkName": ark, "naan": 14707},
                    "url": f"{BASE}/ark:/14707/{ark}",
                    "title": [title],
                    "referenceCode": ref or [],
                    "description": "",
                    "period": {
                        "boundaries": [date_from, date_to],
                        "certainty": None,
                    },
                    "locationKeywords": keywords or [],
                },
                "uuid": uuid,
                "location": {
                    "original": f"{BASE}/images/{uuid}.jpg",
                    "thumb": f"{BASE}/images/{uuid}_thumbnail.jpg",
                    "iiif": None,
                },
                "type": "image",
                "format": "jpg",
                "title": None,
            }
        ]
    }


def _api_url(ark: str, uuid: str) -> str:
    return f"{BASE}/visualizer/api?arkName={ark}&uuid={uuid}"


def _seed(ark: str, uuid: str) -> str:
    return f"{BASE}/ark:/14707/{ark}/{uuid}"


def _docs() -> dict:
    return {
        _api_url(*GREVE): _doc(
            *GREVE,
            "La grève des Bateliers à Conflans",
            "1936-01-01",
            "1936-12-31",
            keywords=["Paris (France)"],
            ref=["PH C4 03 (16)"],
        ),
        _api_url(*CITROEN): _doc(
            *CITROEN,
            "Paris. Usine Citroën. Quai de Javel. Ouvrier blessé",
            "1915-03-01",
            "1915-03-31",
            keywords=["Paris (France)"],
            ref=["VAL 364/022"],
        ),
        _api_url(*FERME): _doc(
            *FERME,
            "Ferme modèle. Moisson du blé en Beauce",
            "1925-01-01",
            "1925-12-31",
            keywords=["France"],
            ref=["XX 1"],
        ),
    }


class FakeHttp:
    def __init__(self, routes: dict) -> None:
        self.routes = routes

    async def get_json(self, url: str, **kwargs):
        if url not in self.routes:
            raise RuntimeError(f"no route for {url}")
        return self.routes[url]

    async def get_bytes(self, url: str, **kwargs):  # pragma: no cover
        raise AssertionError(f"connector must not download images: {url}")


def _descriptor(seeds=()) -> SourceDescriptor:
    return SourceDescriptor(
        id="la_contemporaine_argonnaute",
        name="La Contemporaine — L'Argonnaute (bibliothèque numérique)",
        institution="La Contemporaine (ex-BDIC), Nanterre",
        country="FR",
        protocol=Protocol.REST,
        base_url=BASE,
        auth="none",
        license="Licence Ouverte / Open Licence — sinon tous droits réservés",
        rights="La Contemporaine / L'Argonnaute — voir la notice",
        seeds=list(seeds),
        extra={
            "api_path": "/visualizer/api",
            "ark_naan": "14707",
            "attribution": "La Contemporaine / L'Argonnaute",
        },
    )


def _connector(seeds) -> LaContemporaineArgonnauteConnector:
    return LaContemporaineArgonnauteConnector(_descriptor(seeds), FakeHttp(_docs()))


_ALL_SEEDS = [_seed(*GREVE), _seed(*CITROEN), _seed(*FERME)]


def test_tokens_singularise_plural_forms() -> None:
    assert _tokens("grèves") == _tokens("grève")
    assert _tokens("ouvriers") == _tokens("ouvrier")
    assert "greve" in _tokens("Grèves des transports")
    # a 4-digit year survives tokenisation intact (needed for decade match)
    assert "1930" in _tokens("grève 1930")


@pytest.mark.asyncio
async def test_plural_query_matches_singular_caption() -> None:
    assets = await _connector(_ALL_SEEDS).search("grèves", limit=10)
    assert {a.source_asset_id for a in assets} == {GREVE[1]}


@pytest.mark.asyncio
async def test_resolver_phrase_surfaces_labor_photos() -> None:
    assets = await _connector(_ALL_SEEDS).search(
        "ouvriers Citroën grèves 1930", limit=10
    )
    ids = {a.source_asset_id for a in assets}
    # grève photo kept via "grève" (+1930s decade); Citroën photo via "Citroën"
    # and "ouvrier"; the unrelated "ferme" never leaks in.
    assert ids == {GREVE[1], CITROEN[1]}


@pytest.mark.asyncio
async def test_decade_year_matches_same_decade() -> None:
    assets = await _connector(_ALL_SEEDS).search("1930", limit=10)
    assert {a.source_asset_id for a in assets} == {GREVE[1]}  # 1936 is 193x


@pytest.mark.asyncio
async def test_decade_year_does_not_overreach() -> None:
    # no curated photo lives in the 1900s decade -> empty, never a blanket hit
    assets = await _connector(_ALL_SEEDS).search("1900", limit=10)
    assert assets == []


@pytest.mark.asyncio
async def test_plural_query_does_not_leak_unrelated_seed() -> None:
    assets = await _connector(_ALL_SEEDS).search("moisson blé", limit=10)
    assert {a.source_asset_id for a in assets} == {FERME[1]}
