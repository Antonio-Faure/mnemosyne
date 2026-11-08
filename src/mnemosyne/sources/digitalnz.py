"""DigitalNZ (Te Puna Mātauranga o Aotearoa) — REST aggregator (``records.json``).

DigitalNZ is the National Library of New Zealand's heritage aggregator. Its
public v3 REST API (``/v3/records.json``) answers keyless for reasonable use.
Provider shapes (multi-valued ``usage``/``date``/``creator`` lists, sometimes
empty ``is_commercial_use``) are normalized into the canonical :class:`Asset`
at this boundary; the raw provider shape never leaks past it.

Per-record filters (the aggregator mixes licences, so we decide record by
record):

* **commercial use** — ``usage`` must contain "Use commercially". The API often
  returns ``is_commercial_use: null`` even for reusable items, so only an
  explicit ``false`` disqualifies a record.
* **rights** — accept public domain / "No known copyright restrictions" /
  "out of copyright" / CC0 / CC BY; reject "Some rights reserved",
  "All rights reserved", "Copyright must be cleared" and CC BY-NC / CC BY-ND.
* **image** — a non-empty http(s) ``large_thumbnail_url`` (else
  ``thumbnail_url``) is required; metadata-only records are skipped.
"""

from __future__ import annotations

from typing import Any

from mnemosyne.connectors.base import Connector
from mnemosyne.logger import get_logger
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

log = get_logger("sources.digitalnz")

#: substrings that force a record to be rejected (checked before the accepts)
_RIGHTS_REJECT = (
    "some rights reserved",
    "all rights reserved",
    "rights reserved",
    "copyright must be cleared",
    "rights must be cleared",
    "copyright not cleared",
    "in copyright",
    "by-nc",
    "by nc",
    "by-nd",
    "by nd",
    "noncommercial",
    "non-commercial",
    "no commercial",
    "no derivatives",
)
#: substrings, any one of which admits a record as reusable
_RIGHTS_ACCEPT = (
    "public domain",
    "no known copyright",
    "no copyright",
    "no known restrictions",
    "out of copyright",
    "cc0",
    "cc by",
    "cc-by",
    "creative commons attribution",
)

_MAX_PER_PAGE = 100
_MAX_PAGES = 10


def _first_text(value: Any) -> str | None:
    """DigitalNZ fields are multi-valued (list), scalar or None; return first text."""
    if isinstance(value, list):
        for item in value:
            text = _first_text(item)
            if text:
                return text
        return None
    if isinstance(value, dict):
        for item in value.values():
            text = _first_text(item)
            if text:
                return text
        return None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _http_url(value: Any) -> str | None:
    """Return ``value`` only when it is a non-empty http(s) URL."""
    text = _first_text(value)
    if text and (text.startswith("http://") or text.startswith("https://")):
        return text
    return None


def _rights_blob(record: dict[str, Any]) -> str:
    """Concatenate the free-text rights fields into one lowercase blob."""
    parts = [
        _first_text(record.get("rights")),
        _first_text(record.get("copyright")),
        _first_text(record.get("license")),
    ]
    return " ".join(p.lower() for p in parts if p)


def _rights_allowed(record: dict[str, Any]) -> bool:
    blob = _rights_blob(record)
    if not blob:
        return False
    if any(marker in blob for marker in _RIGHTS_REJECT):
        return False
    return any(marker in blob for marker in _RIGHTS_ACCEPT)


def _usage_values(record: dict[str, Any]) -> list[str]:
    usage = record.get("usage")
    if isinstance(usage, str):
        return [usage.strip().lower()]
    if isinstance(usage, list):
        return [str(u).strip().lower() for u in usage if u is not None]
    return []


def _has_commercial_use(record: dict[str, Any]) -> bool:
    """Require "Use commercially" usage and the absence of an explicit refusal.

    The API returns ``is_commercial_use: null`` on most records (even reusable
    ones), so we treat ``usage`` as authoritative and only an explicit ``false``
    disqualifies a record.
    """
    if record.get("is_commercial_use") is False:
        return False
    return any("use commercially" in value for value in _usage_values(record))


class DigitalNzConnector(Connector):
    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        per_page = max(1, min(limit, _MAX_PER_PAGE))
        assets: list[Asset] = []
        page = 1
        while len(assets) < limit and page <= _MAX_PAGES:
            params = {
                "text": query,
                "and[category][]": "Images",
                "and[usage][]": "Use commercially",
                "per_page": str(per_page),
                "page": str(page),
            }
            data = await self.http.get_json(self.descriptor.base_url, params=params)
            results = ((data or {}).get("search") or {}).get("results") or []
            if not results:
                break
            for record in results:
                asset = self._record_to_asset(record)
                if asset is not None:
                    assets.append(asset)
                if len(assets) >= limit:
                    break
            if len(results) < per_page:
                break
            page += 1
        return assets[:limit]

    def _record_to_asset(self, record: dict[str, Any]) -> Asset | None:
        if not isinstance(record, dict):
            return None
        dnz_id = _first_text(record.get("id"))
        if not dnz_id:
            return None
        if not _has_commercial_use(record) or not _rights_allowed(record):
            return None

        large = _http_url(record.get("large_thumbnail_url"))
        thumb = _http_url(record.get("thumbnail_url"))
        image_url = large or thumb
        if not image_url:
            return None
        thumbnail_url = thumb or large

        landing = _http_url(record.get("landing_url")) or _http_url(record.get("object_url"))
        creator = _first_text(record.get("creator")) or _first_text(record.get("contributor"))
        date_text = _first_text(record.get("date")) or _first_text(record.get("display_date"))
        partner = _first_text(record.get("display_content_partner")) or _first_text(
            record.get("content_partner")
        )

        return Asset.build(
            self.id,
            dnz_id,
            title=_first_text(record.get("title")) or landing or dnz_id,
            description=_first_text(record.get("description")) or "",
            creator=creator,
            date_text=date_text,
            year=parse_year(date_text),
            license=_first_text(record.get("license")) or self.descriptor.license,
            rights=_first_text(record.get("rights")) or self.descriptor.rights,
            page_url=landing,
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            extra={
                "dnz_id": dnz_id,
                "partner": partner,
                "rights_url": _first_text(record.get("rights_url")),
            },
        )
