"""Ranking of catalog candidates: the best record must survive the truncation."""

from __future__ import annotations

import json

from mnemosyne.models import Asset
from mnemosyne.resolver.agent import _compact_row, _fit_rows
from mnemosyne.resolver.ranking import rank, score, tokens


def _asset(title: str, *, year=None, creator=None, description="", source="gallica") -> Asset:
    return Asset.build(
        source,
        title.lower().replace(" ", "-"),
        title=title,
        year=year,
        creator=creator,
        description=description,
        image_url="https://example.org/i.jpg",
        page_url="https://example.org/p",
    )


def test_accents_and_case_do_not_hide_a_candidate():
    asset = _asset("Révolution de 1830 à Bruxelles")
    assert "revolution" in tokens("RÉVOLUTION")
    assert score("revolution bruxelles 1830", asset) > 1.0


def test_a_dated_record_beats_an_undated_one():
    dated = _asset("German troops entering Brussels", year=1914)
    undated = _asset("German troops entering Brussels", year=None)
    assert score("German troops entering Brussels 1914", dated) > score(
        "German troops entering Brussels 1914", undated
    )


def test_anachronism_is_pushed_down_but_not_hidden():
    period = _asset("Belgian refugees on the road", year=1914)
    modern = _asset("Belgian refugees on the road", year=2015)
    assert score("Belgian refugees 1914", period) > score("Belgian refugees 1914", modern)
    assert score("Belgian refugees 1914", modern) >= 0.0


def test_rank_is_best_first_and_stable_on_ties():
    weak = _asset("Steam locomotive in Pennsylvania", year=1900)
    strong = _asset("German invasion of Belgium", year=1914)
    twin = _asset("German invasion of Belgium, another print", year=1914)
    ordered = rank("German invasion of Belgium 1914", [weak, strong, twin])
    assert ordered[0] in (strong, twin)
    assert ordered[-1] is weak
    assert rank("German invasion of Belgium 1914", [weak, strong], limit=1) == [strong]


def test_empty_query_keeps_catalog_order():
    first = _asset("Puits de Lacq", source="a")
    second = _asset("Raffinerie", source="b")
    assert rank("", [first, second]) == [first, second]


def test_payload_is_never_truncated_mid_json():
    rows = [
        _compact_row(_asset(f"German invasion of Belgium {1914 + i % 10}", year=1914))
        for i in range(200)
    ]
    shown = _fit_rows(rows, budget=2000)
    assert 0 < len(shown) < len(rows)
    json.loads(json.dumps(shown, ensure_ascii=False))  # valid JSON, no dangling bracket
