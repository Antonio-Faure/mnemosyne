"""Corpus ingestion: any sentence can be resolved, not only labeled ones."""

from __future__ import annotations

import json

import pytest

from mnemosyne.db import Database
from mnemosyne.resolver import CorpusFileError, load_corpus


def _write(tmp_path, name: str, content) -> str:
    path = tmp_path / name
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_text(json.dumps(content), encoding="utf-8")
    return str(path)


def test_jsonl_sentences_keep_their_order_and_get_normalised(tmp_path):
    path = _write(
        tmp_path,
        "corpus.jsonl",
        "\n".join(
            [
                json.dumps({"id": "a", "text": "  In 1914   the German army   crossed  "}),
                json.dumps({"id": "b", "text": "The city grew during the industrial revolution."}),
            ]
        ),
    )
    entries = load_corpus(path)
    assert [entry["id"] for entry in entries] == ["a", "b"]
    assert entries[0]["text"] == "In 1914 the German army crossed"


def test_a_transcript_document_becomes_one_entry_per_segment(tmp_path):
    path = _write(
        tmp_path,
        "transcript.json",
        {
            "video": {"id": "abc123", "title": "WWI", "url": "https://youtu.be/abc123"},
            "segments": [
                {"start": 1.0, "end": 4.0, "text": "In August 1914 the army crossed."},
                {"start": 4.0, "end": 5.0, "text": "Yes."},  # too short
                {"start": 5.0, "end": 9.0, "text": "Refugees fled to the Netherlands."},
            ],
        },
    )
    entries = load_corpus(path)
    assert [entry["id"] for entry in entries] == ["yt_abc123_1", "yt_abc123_3"]
    assert entries[0]["video"]["id"] == "abc123"
    assert entries[0]["start_s"] == 1.0


def test_a_prefix_avoids_collisions_between_transcripts(tmp_path):
    path = _write(
        tmp_path,
        "transcript.json",
        {
            "video": {"id": "v1"},
            "segments": [{"start": 0, "end": 2, "text": "A sentence about Belgium in 1914."}],
        },
    )
    entries = load_corpus(path, prefix="nb_")
    assert entries[0]["id"] == "nb_yt_v1_1"


def test_a_golden_label_is_accepted_as_a_corpus_line(tmp_path):
    path = _write(
        tmp_path,
        "golden.jsonl",
        json.dumps(
            {
                "id": "yt_x_1",
                "video": {"id": "x", "url": "https://youtu.be/x"},
                "segment": {"start_s": 0, "end_s": 3, "text": "The city grew rapidly."},
                "gold": {"status": "no_match", "images": []},
            }
        ),
    )
    entries = load_corpus(path)
    assert entries[0]["text"] == "The city grew rapidly."


def test_duplicate_ids_are_rejected(tmp_path):
    path = _write(
        tmp_path,
        "dup.jsonl",
        "\n".join(
            [
                json.dumps({"id": "same", "text": "The city grew very rapidly."}),
                json.dumps({"id": "same", "text": "Another sentence about it."}),
            ]
        ),
    )
    with pytest.raises(CorpusFileError, match="duplicate id"):
        load_corpus(path)


def test_a_line_without_id_is_rejected_outside_a_transcript(tmp_path):
    path = _write(tmp_path, "noid.jsonl", json.dumps({"text": "The city grew rapidly."}))
    with pytest.raises(CorpusFileError, match="missing id"):
        load_corpus(path)


def test_a_file_with_nothing_usable_is_rejected(tmp_path):
    path = _write(tmp_path, "tiny.jsonl", json.dumps({"id": "a", "text": "Yes."}))
    with pytest.raises(CorpusFileError, match="no usable sentence"):
        load_corpus(path)


def test_corpus_roundtrip_and_open_task_detection(config):
    db = Database(config.db_file())
    try:
        written = db.upsert_resolver_corpus(
            [
                {
                    "id": "yt_a_1",
                    "text": "In 1914 the German army crossed into Belgium.",
                    "video": {"id": "a"},
                    "start_s": 1.0,
                    "end_s": 4.0,
                }
            ]
        )
        assert written == 1
        assert db.resolver_corpus_count() == 1
        stored = db.get_resolver_corpus("yt_a_1")
        assert stored is not None and stored["text"].startswith("In 1914")

        assert db.open_resolver_task("yt_a_1") is None
        task_id = db.enqueue_task(
            "resolver", "resolve it", payload={"kind": "resolver", "segment_id": "yt_a_1"}
        )
        assert db.open_resolver_task("yt_a_1") == task_id
        db.set_task_status(task_id, "done", agent="resolver")
        assert db.open_resolver_task("yt_a_1") is None
    finally:
        db.close()


def test_transcript_timestamps_given_as_strings_become_seconds(tmp_path):
    """The shorts pipeline writes "10.2" (string): keep them as numbers."""
    path = _write(
        tmp_path,
        "transcript.json",
        {
            "video": {"id": "v2"},
            "segments": [
                {"start": "10.2", "end": "13.3", "text": "La France a des idées."},
            ],
        },
    )
    entry = load_corpus(path)[0]
    assert entry["start_s"] == 10.2
    assert entry["end_s"] == 13.3
