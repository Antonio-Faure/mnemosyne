"""The sources/licences inventory (`docs/SOURCES.md`) must track the descriptors.

Guards mission B: the markdown table of *active* sources and their licences is
only useful if it never drifts from `config/sources/*.yaml`. This test fails as
soon as a provider is added, removed, enabled or disabled without updating the
doc (and vice-versa).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCES_DIR = ROOT / "config" / "sources"
DOC_PATH = ROOT / "docs" / "SOURCES.md"

#: markdown table row -> first cell (the source id, lower-snake-case)
_ROW = re.compile(r"^\|\s*([a-z0-9_]+)\s*\|")


def _descriptors() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted(SOURCES_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        out[raw["id"]] = raw
    return out


def _enabled_ids(descriptors: dict[str, dict]) -> set[str]:
    return {sid for sid, raw in descriptors.items() if raw.get("enabled", True)}


def _doc_ids_by_section() -> tuple[set[str], set[str]]:
    """Return (active_ids, disabled_ids) parsed from the two markdown tables."""
    text = DOC_PATH.read_text(encoding="utf-8")
    active: set[str] = set()
    disabled: set[str] = set()
    section: set[str] | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            if "désactiv" in line:
                section = disabled
            elif "active" in line:
                section = active
            else:
                section = None
            continue
        match = _ROW.match(line)
        if match and section is not None:
            section.add(match.group(1))
    return active, disabled


def test_inventory_doc_exists() -> None:
    assert DOC_PATH.is_file(), "docs/SOURCES.md is missing"


def test_active_table_matches_enabled_descriptors() -> None:
    descriptors = _descriptors()
    enabled = _enabled_ids(descriptors)
    # the id column header itself must not be mistaken for a source
    enabled.discard("id")

    active, disabled = _doc_ids_by_section()
    active.discard("id")
    disabled.discard("id")

    assert active == enabled, f"active table out of sync: {active ^ enabled}"
    assert disabled == set(descriptors) - enabled, (
        f"disabled table out of sync: {disabled ^ (set(descriptors) - enabled)}"
    )


def test_every_active_source_declares_a_licence() -> None:
    for sid, raw in _descriptors().items():
        if raw.get("enabled", True):
            assert raw.get("license"), f"active source {sid} has no license field"


def test_html_sources_carry_scraping_consent() -> None:
    """A scraper is only legitimate with written consent (e-mail) on file."""
    for sid, raw in _descriptors().items():
        if raw.get("protocol") == "html":
            consent = (raw.get("extra") or {}).get("scraping_consent")
            assert consent, f"{sid}: protocol html without extra.scraping_consent"
