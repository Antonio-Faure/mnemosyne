"""Shared IIIF Presentation v2/v3 label & metadata parsing.

Both the generic `iiif.py` connector and bespoke IIIF-family connectors (ANMT's
Ligeo-Archives platform) need the same tolerant parsers: labels and metadata
values are `str | {lang: str | [str]} | {"@value": ...} | list`.
"""

from __future__ import annotations

from typing import Any


def label(value: Any) -> str:
    """IIIF labels: str | lang->str | lang->[str] | {"@value": ...} | list."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return label(value[0]) if value else ""
    if isinstance(value, dict):
        # v2 label/value object: {"@language": "en", "@value": "…"}
        if "@value" in value:
            return label(value["@value"])
        for key in ("fr", "en", "none"):
            if key in value:
                text = label(value[key])
                if text:
                    return text
        for item in value.values():
            text = label(item)
            if text:
                return text
    return ""


def metadata(manifest: dict, *names: str) -> str | None:
    """First metadata entry whose label matches one of `names` (case-insensitive)."""
    wanted = {name.lower() for name in names}
    for entry in manifest.get("metadata", []) or []:
        if not isinstance(entry, dict):
            continue
        if label(entry.get("label")).lower() in wanted:
            text = label(entry.get("value"))
            if text:
                return text
    return None
