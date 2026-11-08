"""Rank catalog candidates for one historical sentence (cheap lexical scoring).

`catalog_search` can return hundreds of rows across 50+ providers. Providers
come back in catalog-priority order, so truncating the payload used to throw
away the *relevant* records and keep the first ones alphabetically. Ranking
before truncation is what makes the tool usable by the resolver.

The score is deliberately simple and explainable — token overlap (title worth
double) plus year proximity — so it can be tested offline and never invents a
match. The adversarial judgement stays with the resolver + the operator.
"""

from __future__ import annotations

import re
import unicodedata

from mnemosyne.models import Asset

_WORD = re.compile(r"[a-z0-9]{2,}")
_YEAR = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")

#: Words that appear in every historical query: matching them proves nothing.
_STOP = frozenset(
    {
        "the", "and", "for", "with", "from", "into", "was", "were", "are", "its",
        "his", "her", "their", "this", "that", "these", "those", "une", "des",
        "les", "dans", "pour", "par", "sur", "avec", "est", "sont", "aux", "du",
        "de", "la", "le", "et", "en", "au", "un", "der", "die", "das", "und",
        "von", "den", "dem", "ein", "eine", "of", "to", "in", "on", "at", "by",
        "an", "as", "or",
    }
)

#: Bonus when the record's date sits within this many years of the claim.
_CLOSE_YEARS = 5
#: Beyond this distance a dated record is probably an anachronism.
_FAR_YEARS = 60


def fold(text: str) -> str:
    """Lowercase + strip accents: 'Révolution' and 'revolution' must meet."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall(fold(text)) if w not in _STOP}


def query_years(query: str) -> list[int]:
    return [int(y) for y in _YEAR.findall(query or "")]


def _title_tokens(asset: Asset) -> set[str]:
    return tokens(asset.title)


def _record_tokens(asset: Asset) -> set[str]:
    return tokens(
        " ".join(
            part
            for part in (asset.title, asset.creator, asset.date_text, asset.description)
            if part
        )
    )


def score(query: str, asset: Asset) -> float:
    """0.0 = nothing in common; higher = more defensible candidate."""
    wanted = tokens(query)
    if not wanted:
        return 0.0
    record = _record_tokens(asset)
    if not record:
        return 0.0
    overlap = len(wanted & record) / len(wanted)
    bonus = len(wanted & _title_tokens(asset)) / len(wanted)  # title counts twice
    value = overlap + 0.5 * bonus

    years = query_years(query)
    if years and asset.year:
        delta = min(abs(asset.year - year) for year in years)
        if delta <= _CLOSE_YEARS:
            value += 0.6
        elif delta >= _FAR_YEARS:
            value -= 0.6
        else:
            value += 0.3 * (1 - delta / _FAR_YEARS)
    return round(value, 4)


def rank(query: str, assets: list[Asset], limit: int | None = None) -> list[Asset]:
    """Best first; the catalog order breaks ties (deterministic)."""
    scored = [(score(query, asset), index, asset) for index, asset in enumerate(assets)]
    scored.sort(key=lambda item: (-item[0], item[1]))
    ordered = [asset for _value, _index, asset in scored]
    return ordered[:limit] if limit is not None else ordered
