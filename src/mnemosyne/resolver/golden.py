"""Load and validate a resolver golden dataset (JSONL or JSON array)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from mnemosyne.resolver.models import GoldenSentence


class GoldenFileError(ValueError):
    """A golden file could not be parsed or violates the contract."""


def _validate_label(data: Any, *, where: str) -> GoldenSentence:
    try:
        label = GoldenSentence.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(part) for part in first.get("loc", ()))
        message = first.get("msg", str(exc))
        raise GoldenFileError(f"{where}: {loc}: {message}") from exc

    if label.segment.start_s > label.segment.end_s:
        raise GoldenFileError(f"{where}: start_s > end_s")
    if label.gold.status == "match" and not label.gold.images:
        raise GoldenFileError(f"{where}: status=match requires at least one image")
    return label


def load_golden(path: str | Path) -> list[GoldenSentence]:
    """Load a golden dataset, preserving order and rejecting duplicate ids."""
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GoldenFileError(f"{file_path}: {exc}") from exc

    rows: list[Any] = []
    stripped = text.lstrip()
    if stripped.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise GoldenFileError(f"{file_path}: invalid JSON array: {exc}") from exc
        if not isinstance(parsed, list):
            raise GoldenFileError(f"{file_path}: expected a JSON array")
        rows = parsed
    else:
        for line_no, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise GoldenFileError(
                    f"{file_path}:{line_no}: invalid JSON: {exc.msg}"
                ) from exc

    if not rows:
        raise GoldenFileError(f"{file_path}: no labels found")

    labels: list[GoldenSentence] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        where = f"{file_path}:{index}"
        label = _validate_label(row, where=where)
        if label.id in seen:
            raise GoldenFileError(f"{where}: duplicate id {label.id!r}")
        seen.add(label.id)
        labels.append(label)
    return labels
