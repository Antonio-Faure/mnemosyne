"""Global video context: card rendering, transcript tools, summary generation."""

from __future__ import annotations

import asyncio
import json

from mnemosyne.db import Database
from mnemosyne.resolver.context import (
    _extract_json,
    generate_video_context,
    video_context_card,
)


def _entry(video_id: str, index: int, text: str) -> dict:
    return {
        "id": f"yt_{video_id}_{index}",
        "text": text,
        "start_s": float(index * 10),
        "end_s": float(index * 10 + 8),
        "video": {"id": video_id, "title": "La France et le pétrole"},
        "claim": {},
    }


def _seed(db: Database, video_id: str, count: int = 30) -> None:
    db.upsert_resolver_corpus(
        [
            _entry(
                video_id,
                index,
                "Le pétrole de Pechelbronn." if index == 15 else f"Phrase {index}.",
            )
            for index in range(count)
        ]
    )


def test_video_context_card_has_summary_plan_position_and_neighbours(config):
    db = Database(config.db_file())
    try:
        _seed(db, "v1")
        db.upsert_video_context(
            "v1",
            title="La France et le pétrole",
            duration_s=300,
            summary="Le pétrole français oublié, de Pechelbronn à Lacq.",
            outline=[
                {"start_s": 0, "end_s": 60, "title": "Le gisement", "summary": ""},
                {"start_s": 60, "end_s": 120, "title": "Les hommes", "summary": ""},
            ],
            meta={"period": "1920", "places": ["Alsace"], "entities": ["Pechelbronn"]},
            model="fake",
        )

        card = video_context_card(db, "yt_v1_15", before=5, after=5)

        assert "Résumé : Le pétrole français oublié" in card
        assert "Période : 1920" in card
        assert "Lieux : Alsace" in card
        assert "Plan :" in card
        assert "Le gisement" in card
        assert "Position : [15] — 16/30" in card
        assert "[15] 2:30 — Le pétrole de Pechelbronn.  ← phrase" in card
        assert "[10] 1:40" in card
        assert "[20] 3:20" in card
        assert "jamais une preuve" in card
    finally:
        db.close()


def test_video_context_card_without_summary_says_so(config):
    db = Database(config.db_file())
    try:
        _seed(db, "v2")
        card = video_context_card(db, "yt_v2_3", before=2, after=2)
        assert "Résumé global : non généré" in card
        assert "Position : [3] — 4/30" in card
    finally:
        db.close()


def test_transcript_search_and_time_window(config):
    db = Database(config.db_file())
    try:
        _seed(db, "v3")
        matches = db.search_resolver_corpus("v3", "Pechelbronn")
        assert [m["id"] for m in matches] == ["yt_v3_15"]

        window = db.resolver_corpus_window(
            "v3", start_s=100, end_s=120, limit=3
        )
        assert [w["id"] for w in window] == ["yt_v3_10", "yt_v3_11", "yt_v3_12"]
    finally:
        db.close()


def test_extract_json_tolerates_fences():
    raw = '```json\n{"summary": "ok", "outline": []}\n```'
    assert _extract_json(raw)["summary"] == "ok"


def test_generate_video_context_stores_the_summary(config):
    class FakeClient:
        model = "fake-model"

        async def chat(self, messages, **kwargs):
            assert "Transcription complète" in messages[-1]["content"]
            return json.dumps(
                {
                    "summary": "Un résumé global.",
                    "meta": {"period": "1914", "places": ["Belgique"], "entities": []},
                    "outline": [
                        {"start_s": 0, "end_s": 60, "title": "Début", "summary": ""}
                    ],
                }
            )

    db = Database(config.db_file())
    try:
        _seed(db, "v4")
        stored = asyncio.run(
            generate_video_context(config, db, "v4", force=True, client=FakeClient())
        )
        assert stored["summary"] == "Un résumé global."
        assert stored["meta"]["period"] == "1914"
        assert stored["outline"][0]["title"] == "Début"
        assert db.get_video_context("v4")["model"] == "fake-model"
    finally:
        db.close()
