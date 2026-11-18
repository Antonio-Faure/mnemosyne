"""The active vocabulary must follow docs/NOMENCLATURE.md.

This is deliberately a small, curated check: it catches the old names that
have an unambiguous replacement, not every English code identifier.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Documents that intentionally preserve the old vocabulary.
SKIP = {
    "docs/NOMENCLATURE.md",
    "docs/FIXES-LOT1.md",
    "docs/FIXES-LOT2.md",
    "docs/FIXES-LOT3.md",
    "docs/CLEANUP-AGENTS.md",
    "docs/P2-AGENTS.md",
    "docs/BENCHMARK-ARCHITECTE.md",
    "docs/CONCIN-ARCHITECTURE.md",
    "docs/LE-GOUT-ARCHITECTE.md",
}

#: Product-facing files where "notice" and "crédit" are banned.
PRODUCT_FILES = {
    "README.md",
    "docs/POUR-LES-INSTITUTIONS.md",
    "docs/OUTREACH.md",
    "web/search.html",
    "web/index.html",
}

BANNED = [
    ("tri-agent", re.compile(r"\btri-agent\b", re.I)),
    ("bi-agent", re.compile(r"\bbi-agent\b", re.I)),
    ("archiviste", re.compile(r"\barchiviste\b", re.I)),
    ("fournisseur", re.compile(r"\bfournisseurs?\b(?!\s+LLM)", re.I)),
    ("système résolveur", re.compile(r"\bsystème\s+résolveur\b", re.I)),
    ("système navigateur/codeur", re.compile(r"\bsystème\s+navigateur\s*/\s*codeur\b", re.I)),
    ("harvest", re.compile(r"\bharvest\b", re.I)),
    ("moissonnage", re.compile(r"\bmoissonnage\b", re.I)),
    ("sidebar", re.compile(r"\bsidebar\b", re.I)),
    ("timeline", re.compile(r"\btimeline\b", re.I)),
    ("replay", re.compile(r"\breplay\b", re.I)),
    ("orchestrateur", re.compile(r"\borchestrateur\b", re.I)),
]

PRODUCT_BANNED = [
    ("notice", re.compile(r"\bnotice\b", re.I)),
    ("crédit", re.compile(r"\bcrédit\b", re.I)),
]

_CODE_SPAN = re.compile(r"`[^`]*`")


def _strip_code(line: str) -> str:
    return _CODE_SPAN.sub("", line)


def _files():
    yield ROOT / "README.md"
    yield ROOT / "AGENTS.md"
    yield from sorted((ROOT / "docs").glob("*.md"))
    yield from sorted((ROOT / "agents").glob("*.md"))
    yield from sorted((ROOT / "web").glob("*.html"))


def _scan(rules, only: set[str] | None = None) -> list[str]:
    hits: list[str] = []
    for path in _files():
        rel = path.relative_to(ROOT).as_posix()
        if rel in SKIP:
            continue
        if only is not None and rel not in only:
            continue
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            clean = _strip_code(line)
            for term, pattern in rules:
                if pattern.search(clean):
                    hits.append(f"{rel}:{number}: « {term} » — {line.strip()[:140]}")
    return hits


def test_active_vocabulary_has_no_old_names():
    hits = _scan(BANNED)
    assert not hits, (
        "Vocabulaire hors nomenclature (voir docs/NOMENCLATURE.md) :\n"
        + "\n".join(hits)
    )


def test_product_copy_has_no_notice_or_credit():
    hits = _scan(PRODUCT_BANNED, only=PRODUCT_FILES)
    assert not hits, (
        "Copie produit hors nomenclature (utiliser fiche / mention) :\n"
        + "\n".join(hits)
    )
