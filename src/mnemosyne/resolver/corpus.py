"""Ingest historical sentences (a corpus) without requiring a gold label.

The resolver must be able to work on any sentence: a YouTube transcript
segment, a dataset line, a manually written claim. `resolver_golden` holds
*evaluated* pairs (match/partial/no_match/ambiguous) for benchmarking; this
module feeds the corpus the resolver actually processes.

Accepted inputs:

* JSONL, one object per line: ``{"id": "...", "text": "...", "start_s": 0}``
  (a full golden label with a ``segment`` key is accepted too);
* a JSON array of those objects;
* a transcript document: ``{"video": {...}, "segments": [{start, end, text}]}``
  — ids are derived as ``yt_<video_id>_<index>``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_WS = re.compile(r"\s+")


class CorpusFileError(ValueError):
    """A corpus file could not be parsed or violates the contract."""


def _text_of(row: dict[str, Any]) -> tuple[str, float | None, float | None]:
    segment = row.get("segment") if isinstance(row.get("segment"), dict) else None
    source = segment or row
    text = source.get("text") or row.get("sentence") or ""
    start = source.get("start_s", source.get("start"))
    end = source.get("end_s", source.get("end"))
    return _WS.sub(" ", str(text)).strip(), start, end


def _video_of(row: dict[str, Any]) -> dict[str, Any]:
    video = row.get("video")
    return dict(video) if isinstance(video, dict) else {}


def _entry(
    row: dict[str, Any],
    *,
    fallback_id: str | None,
    where: str,
    min_words: int,
) -> dict[str, Any] | None:
    text, start, end = _text_of(row)
    if not text:
        raise CorpusFileError(f"{where}: empty text")
    if len(text.split()) < min_words:
        return None
    segment_id = str(row.get("id") or fallback_id or "").strip()
    if not segment_id:
        raise CorpusFileError(f"{where}: missing id (needed for lines without a transcript)")
    video = _video_of(row)
    return {
        "id": segment_id,
        "text": text,
        "start_s": start,
        "end_s": end,
        "video": video,
        "claim": row.get("claim") if isinstance(row.get("claim"), dict) else {},
    }


def _parse(text: str, *, path: Path) -> list[Any]:
    stripped = text.lstrip()
    if stripped.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CorpusFileError(f"{path}: invalid JSON array: {exc}") from exc
        if not isinstance(parsed, list):
            raise CorpusFileError(f"{path}: expected a JSON array")
        return parsed

    # One document (transcript / single sentence) or JSONL: try the whole text
    # first, fall back to one object per line.
    if stripped.startswith("{"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if parsed is not None:
            return [parsed]

    rows: list[Any] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise CorpusFileError(f"{path}:{line_no}: invalid JSON: {exc.msg}") from exc
    return rows


def _expand(document: dict[str, Any]) -> list[tuple[dict[str, Any], str | None]]:
    """A transcript document yields one entry per segment (id derived)."""
    segments = document.get("segments")
    if not isinstance(segments, list):
        return [(document, None)]
    video = _video_of(document)
    video_id = str(video.get("id") or "video")
    expanded: list[tuple[dict[str, Any], str | None]] = []
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            raise CorpusFileError(f"segment {index}: expected an object")
        row = dict(segment)
        row.setdefault("video", video)
        if "claim" not in row and isinstance(document.get("claim"), dict):
            row["claim"] = document["claim"]
        expanded.append((row, f"yt_{video_id}_{index}"))
    return expanded


def load_corpus(
    path: str | Path, *, prefix: str | None = None, min_words: int = 4
) -> list[dict[str, Any]]:
    """Load and normalize a corpus file, rejecting duplicate ids."""
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CorpusFileError(f"{file_path}: {exc}") from exc

    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for document_index, document in enumerate(_parse(text, path=file_path), start=1):
        if not isinstance(document, dict):
            raise CorpusFileError(f"{file_path}:{document_index}: expected an object")
        for row, derived_id in _expand(document):
            if prefix and derived_id:
                derived_id = f"{prefix}{derived_id}"
            where = f"{file_path}:{document_index}"
            entry = _entry(row, fallback_id=derived_id, where=where, min_words=min_words)
            if entry is None:
                continue
            if entry["id"] in seen:
                raise CorpusFileError(f"{where}: duplicate id {entry['id']!r}")
            seen.add(entry["id"])
            entries.append(entry)

    if not entries:
        raise CorpusFileError(f"{file_path}: no usable sentence (min_words={min_words})")
    return entries
