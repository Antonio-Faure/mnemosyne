"""Resolver golden dataset: validation and import."""

from __future__ import annotations

import json

import pytest

from mnemosyne.db import Database
from mnemosyne.resolver import GoldenFileError, load_golden


def _label(**overrides):
    data = {
        "id": "yt_vid_1",
        "video": {
            "id": "vid",
            "title": "A history video",
            "channel": "History",
            "url": "https://www.youtube.com/watch?v=vid",
        },
        "segment": {"start_s": 1.0, "end_s": 4.0, "text": "In 1914, Belgium was invaded."},
        "gold": {
            "status": "match",
            "images": [
                {
                    "url": "https://example.org/image.jpg",
                    "source_id": "gallica",
                    "why": "photo of the invasion",
                }
            ],
            "hard_negatives": [
                {
                    "url": "https://example.org/wrong.jpg",
                    "why_wrong": "same war, wrong year",
                }
            ],
        },
    }
    for path, value in overrides.items():
        target = data
        parts = path.split(".")
        for part in parts[:-1]:
            target = target[part]
        target[parts[-1]] = value
    return data


def _write(tmp_path, rows, *, array=False):
    path = tmp_path / "golden.json"
    if array:
        path.write_text(json.dumps(rows), encoding="utf-8")
    else:
        path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    return path


def test_load_golden_jsonl(tmp_path):
    labels = load_golden(_write(tmp_path, [_label()]))
    assert len(labels) == 1
    assert labels[0].id == "yt_vid_1"
    assert labels[0].gold.status == "match"
    assert labels[0].gold.images[0].source_id == "gallica"


def test_load_golden_json_array(tmp_path):
    labels = load_golden(_write(tmp_path, [_label(), _label(id="yt_vid_2")], array=True))
    assert [label.id for label in labels] == ["yt_vid_1", "yt_vid_2"]


def test_match_requires_an_image(tmp_path):
    path = _write(tmp_path, [_label(**{"gold.images": []})])
    with pytest.raises(GoldenFileError, match="requires at least one image"):
        load_golden(path)


def test_no_match_may_have_no_image(tmp_path):
    labels = load_golden(
        _write(tmp_path, [_label(**{"gold": {"status": "no_match", "images": []}})])
    )
    assert labels[0].gold.status == "no_match"


def test_urls_must_be_http(tmp_path):
    path = _write(
        tmp_path,
        [_label(**{"gold.images": [{"url": "file:///x.jpg", "why": "bad"}]})],
    )
    with pytest.raises(GoldenFileError, match="http"):
        load_golden(path)


def test_duplicate_ids_are_rejected(tmp_path):
    path = _write(tmp_path, [_label(), _label()])
    with pytest.raises(GoldenFileError, match="duplicate id"):
        load_golden(path)


def test_start_after_end_is_rejected(tmp_path):
    path = _write(tmp_path, [_label(**{"segment.start_s": 10.0, "segment.end_s": 2.0})])
    with pytest.raises(GoldenFileError, match="start_s"):
        load_golden(path)


def test_bad_status_is_rejected(tmp_path):
    path = _write(tmp_path, [_label(**{"gold.status": "maybe"})])
    with pytest.raises(GoldenFileError, match="status"):
        load_golden(path)


def test_extra_fields_are_preserved(tmp_path):
    row = _label()
    row["custom_annotation"] = "kept"
    labels = load_golden(_write(tmp_path, [row]))
    assert labels[0].model_dump()["custom_annotation"] == "kept"


def test_import_and_stats(config, tmp_path):
    labels = load_golden(
        _write(
            tmp_path,
            [
                _label(),
                _label(id="yt_vid_2", **{"gold": {"status": "no_match", "images": []}}),
            ],
            array=True,
        )
    )
    db = Database(config.db_file())
    try:
        assert db.upsert_resolver_golden(labels) == 2
        assert db.resolver_golden_count() == 2
        assert db.resolver_golden_stats() == {"match": 1, "no_match": 1}
        stored = db.list_resolver_golden()
        assert {item["id"] for item in stored} == {"yt_vid_1", "yt_vid_2"}
        # idempotent upsert
        assert db.upsert_resolver_golden(labels) == 2
        assert db.resolver_golden_count() == 2
    finally:
        db.close()
