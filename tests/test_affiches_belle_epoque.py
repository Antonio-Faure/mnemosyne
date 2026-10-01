"""Offline checks for the « Affiches de la Belle Époque » collection manifest.

Runs against a reduced fixture (tests/fixtures/affiches_belle_epoque.json);
performs no network I/O.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "affiches_belle_epoque.json"

REQUIRED_FIELDS = (
    "title",
    "creator",
    "date",
    "source",
    "page_url",
    "image_url",
    "license",
    "license_url",
    "retrieved_at",
)

#: Free-license allowlist: public domain (incl. PDM / PD-old), CC0, or CC-BY.
_FREE_LICENSE_RE = re.compile(
    r"(public[ -]?domain|\bpd\b|pd-old|\bcc0\b|cc[ -]?by)",
    re.IGNORECASE,
)


def _items() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_manifest_schema_and_required_fields():
    items = _items()
    assert items, "fixture must not be empty"
    for i, item in enumerate(items):
        for field in REQUIRED_FIELDS:
            assert field in item, f"item {i} missing field {field!r}"
        for field in ("title", "source", "page_url", "image_url", "license", "license_url"):
            assert str(item[field]).strip(), f"item {i} has an empty {field!r}"


def test_page_and_image_urls_are_unique():
    items = _items()
    pages = [item["page_url"] for item in items]
    images = [item["image_url"] for item in items]
    assert len(pages) == len(set(pages)), "duplicate page_url found"
    assert len(images) == len(set(images)), "duplicate image_url found"


def test_licenses_are_in_free_allowlist():
    for i, item in enumerate(_items()):
        haystack = f"{item['license']} {item['license_url']}"
        assert _FREE_LICENSE_RE.search(haystack), (
            f"item {i} license is not in the free allowlist: {item['license']!r}"
        )


def test_retrieved_at_is_iso8601():
    for i, item in enumerate(_items()):
        value = item["retrieved_at"].replace("Z", "+00:00")
        try:
            datetime.fromisoformat(value)
        except ValueError as exc:  # pragma: no cover - failure path
            raise AssertionError(f"item {i} retrieved_at is not ISO 8601: {value!r}") from exc
