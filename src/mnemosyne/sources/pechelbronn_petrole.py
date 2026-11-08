"""Musée français du pétrole — fonds Pechelbronn (WordPress media REST API).

The museum's website (``www.musee-du-petrole.com``, note the ``-du-`` that the
original task URL ``musee-petrole.com`` got wrong — that host is NXDOMAIN) runs
on WordPress + Polylang and exposes its whole media library through the open
WordPress REST endpoint ``/wp-json/wp/v2/media``. No authentication, any
User-Agent, pure JSON: this connector never scrapes HTML.

Baseline (verified live 2026-11-08): ``X-WP-Total: 913`` images over 10 pages at
``per_page=100``. The library is a *mix* — logos, header banners, modern staff
snapshots and the historical Pechelbronn fonds (≈96–160 items). There is **no
taxonomy**, so we curate with a heuristic :func:`is_historical` over
``title + slug`` (PECH_* inventory codes, ``NNNN.0.NNN`` cotes,
``CollectionMFDP``, period vocabulary).

Three production gotchas, all handled here
------------------------------------------
1. **Burst WAF → HTTP 410.** After ~10–13 rapid requests the endpoint answers
   ``410`` with an *HTML* error page (not JSON); it clears on a pause. We pace
   requests (:data:`REQUEST_DELAY_S`) and treat ``410/429/503`` as retryable
   with exponential backoff (2, 4, 8 s) instead of aborting.
2. **Latin-1 filenames.** Accented filenames are stored Latin-1, so ``â`` must
   travel as ``%E2`` (one byte), not UTF-8 ``%C3%A2``. A plain GET of the
   ``source_url`` 404s; :func:`latin1_url` rewrites it to the single-byte form.
3. **Dead uploads.** A few ``source_url``s 404 (record kept, file gone). We keep
   the record and fall back to ``media_details.sizes`` (both at build time when
   ``source_url`` is missing, and lazily in :meth:`fetch` via the thumbnail).

Rights: no open licence is published (no licence/CC/PD field). Catalogued as a
*finder* (metadata + pointers): ``rights="in_copyright"``, mandatory credit
"© Musée français du pétrole / Association des Amis du Musée" (kept in
``extra["credit"]``). The full provider shape never leaks past :class:`Asset`:
everything provider-specific lives in ``Asset.extra``.
"""

from __future__ import annotations

import asyncio
import html
import re
import unicodedata
from typing import Any
from urllib.parse import quote

import httpx

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

DEFAULT_PER_PAGE = 100
#: gap between page requests — keeps us under the WAF burst threshold
REQUEST_DELAY_S = 2.0
#: statuses the WAF/host uses for transient throttling (410 = burst block)
RETRY_STATUS = frozenset({410, 429, 503})
_DEFAULT_FIELDS = (
    "id,date,slug,title,source_url,link,media_details,"
    "alt_text,caption,description,post,mime_type"
)

# ── pure helpers (unit-tested directly) ─────────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

#: modern staff-snapshot slugs start with a compact 8-digit date, e.g. 20210608_
_MODERN_SLUG_RE = re.compile(r"^20\d{6}[_\-]")

#: non-historical library furniture
_NOISE_RE = re.compile(
    r"(?i)(?:^|\b)(?:logo|amuse[\s\-]?mus[ée]es?|img[_\-]?\d|pr[eé]sentation|"
    r"stockcake|banni[eè]re|bandeau|en[\s\-]?t[eê]te|header)\b"
)

#: historical Pechelbronn fonds vocabulary (see module docstring)
HISTORICAL_RE = re.compile(
    r"(?i)"
    r"pech[ _\-]?\d"                       # PECH_2013, pech-1997 …
    r"|\d{4}\.\d+\.\d+"                     # NNNN.0.NNN inventory cote
    r"|collection\s*mfdp"
    r"|pechelbronn|merkwiller"
    r"|antar|sauer|schlumberger|hepting"
    r"|raffiner|refin"
    r"|forage|derrick|puits|sonde|treuil|carottage|sondage|drill"
    r"|carte[\s\-]*postale|\bcpa\b"
    r"|aquarelle|photograph|gravure|lithograph"
    r"|2ww|guerre|mitoi"
    r"|\b1[89]\d{2}\b|\b19[0-6]\d\b"       # years 1800–1969
)

#: ``PECH`` + inventory code, e.g. PECH_2013-1-2 / PECH_1997.0.256
_INVENTORY_RE = re.compile(r"(?i)\bpech[ _\-]?([0-9][0-9._\-]*)")

#: coarse theme buckets -> keyword regex (first match wins)
_THEME_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("carte_postale", re.compile(r"(?i)carte[\s\-]*postale|\bcpa\b|vue a[ée]rienne")),
    ("publicite", re.compile(r"(?i)publicit|affiche|r[eé]clame|advertis")),
    ("portrait", re.compile(r"(?i)portrait|vendeur|monsieur|famille|personnage")),
    ("raffinerie", re.compile(r"(?i)raffiner|refin")),
    ("forage",
     re.compile(r"(?i)forage|derrick|puits|sonde|treuil|carottage|sondage|drill")),
    ("materiel",
     re.compile(r"(?i)materiel|mat[ée]riel|atelier|machine|pompe|outil")),
)

#: a human date embedded in a title, e.g. "5 sept 1927", "07/1927" or bare "1927"
_DATE_RE = re.compile(
    r"(?i)(\d{1,2}\s+[a-zéèûôà]{3,}\s+(?:1[89]\d{2}|19[0-6]\d))"
    r"|((?:0?[1-9]|[12]\d|3[01])[/.\-](?:0?[1-9]|1[0-2])[/.\-](?:1[89]\d{2}|19[0-6]\d))"
    r"|(\b(?:1[89]\d{2}|19[0-6]\d)\b)"
)


def strip_tags(value: Any) -> str:
    """Plain text from a WordPress ``*.rendered`` fragment (tags + entities)."""
    if not value:
        return ""
    text = _TAG_RE.sub("", str(value))
    return _WS_RE.sub(" ", html.unescape(text)).strip()


def normalise(value: Any) -> str:
    """Accent-folded, lower-cased, single-spaced text for keyword matching."""
    text = unicodedata.normalize("NFKD", strip_tags(value).lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return _WS_RE.sub(" ", text).strip()


def is_historical(title: str, slug: str = "", pattern: re.Pattern[str] | None = None) -> bool:
    """True if ``title``/``slug`` looks like a historical fonds image (not noise)."""
    slug = slug or ""
    if _MODERN_SLUG_RE.match(slug):
        return False
    haystack = f"{title or ''} {slug}"
    if _NOISE_RE.search(haystack):
        return False
    return bool((pattern or HISTORICAL_RE).search(haystack))


def extract_inventory(title: str, slug: str = "") -> str | None:
    """Return the normalised inventory code (``PECH_…``) when the title has one."""
    match = _INVENTORY_RE.search(f"{title or ''} {slug or ''}")
    if not match:
        return None
    code = match.group(1).rstrip("._-")
    return f"PECH_{code}" if code else None


def classify_theme(title: str, slug: str = "") -> str:
    """Coarse theme bucket from keywords (forage/raffinerie/portrait/…)."""
    haystack = f"{title or ''} {slug or ''}"
    for name, rule in _THEME_RULES:
        if rule.search(haystack):
            return name
    return "autre"


def latin1_url(url: str) -> str:
    """Percent-encode non-ASCII characters as single Latin-1 bytes.

    ``"câble"`` (with a literal ``â``) becomes ``c%E2ble`` — what the museum's
    server expects — instead of httpx's default UTF-8 ``c%C3%A2ble``. Already
    ASCII URLs are returned untouched, so callers can safely try both.
    """
    if not url or url.isascii():
        return url
    out: list[str] = []
    for ch in url:
        if ch.isascii():
            out.append(ch)
            continue
        try:
            out.append("".join(f"%{byte:02X}" for byte in ch.encode("latin-1")))
        except UnicodeEncodeError:
            out.append(quote(ch, safe=""))
    return "".join(out)


def _extract_date(title: str) -> str | None:
    match = _DATE_RE.search(title or "")
    return match.group(0).strip() if match else None


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _size_url(sizes: dict[str, Any]) -> str:
    for key in ("full", "large", "medium_large", "medium", "thumbnail"):
        node = sizes.get(key)
        if isinstance(node, dict) and node.get("source_url"):
            return str(node["source_url"])
    return ""


class PechelbronnPetroleConnector(Connector):
    """Normalises the WordPress media API into canonical :class:`Asset`s."""

    def __init__(self, descriptor: Any, http: Any) -> None:
        super().__init__(descriptor, http)
        extra = descriptor.extra or {}
        regex = extra.get("historical_regex")
        self._historical_re = re.compile(regex) if regex else HISTORICAL_RE
        self._request_delay = float(extra.get("request_delay_s", REQUEST_DELAY_S))
        self._retry_status = frozenset(extra.get("retry_status") or RETRY_STATUS)
        self._backoff_base = float(extra.get("backoff_base_s", 2.0))
        self._max_retries = int(extra.get("max_retries", 3))

    # ── search ───────────────────────────────────────────────────────────
    async def search(self, query: str = "", limit: int = 20, **filters: Any) -> list[Asset]:
        extra = self.descriptor.extra or {}
        endpoint = str(
            extra.get("media_endpoint")
            or f"{self.descriptor.base_url.rstrip('/')}/wp-json/wp/v2/media"
        )
        per_page = int(filters.get("per_page") or extra.get("per_page") or DEFAULT_PER_PAGE)
        base_params = {
            "media_type": extra.get("media_type", "image"),
            "per_page": per_page,
            "orderby": extra.get("orderby", "id"),
            "order": extra.get("order", "asc"),
            "_fields": extra.get("fields") or _DEFAULT_FIELDS,
        }
        max_pages = int(filters.get("max_pages") or extra.get("max_pages") or 20)

        assets: list[Asset] = []
        page = 1
        while page <= max_pages:
            resp = await self._get_page(endpoint, {**base_params, "page": page})
            if resp is None:
                break
            try:
                data = resp.json()
            except ValueError:
                break
            if not isinstance(data, list) or not data:
                break
            for item in data:
                asset = self._media_to_asset(item)
                if asset is not None:
                    assets.append(asset)
            total_pages = _coerce_int(resp.headers.get("X-WP-TotalPages"))
            if len(assets) >= limit:
                break
            if total_pages is not None and page >= total_pages:
                break
            page += 1
            if self._request_delay > 0:
                await asyncio.sleep(self._request_delay)
        return self._rank(assets, query)[:limit]

    async def _get_page(self, url: str, params: dict[str, Any]) -> httpx.Response | None:
        """GET one page, retrying the WAF's ``410/429/503`` with backoff."""
        attempt = 0
        while True:
            try:
                return await self.http.get(url, params=params, accept="application/json")
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in self._retry_status and attempt < self._max_retries:
                    await asyncio.sleep(self._backoff_base * (2 ** attempt))
                    attempt += 1
                    continue
                return None
            except Exception:  # noqa: BLE001 - a single page must not kill the search
                return None

    def _media_to_asset(self, item: Any) -> Asset | None:
        if not isinstance(item, dict):
            return None
        media_id = item.get("id")
        if media_id is None:
            return None
        title_node = item.get("title")
        raw_title = title_node.get("rendered") if isinstance(title_node, dict) else title_node
        title = strip_tags(raw_title)
        slug = str(item.get("slug") or "")
        if not is_historical(title, slug, self._historical_re):
            return None

        details = item.get("media_details") or {}
        sizes = details.get("sizes") if isinstance(details, dict) else {}
        sizes = sizes if isinstance(sizes, dict) else {}
        source_url = str(item.get("source_url") or "")
        image_url = source_url or _size_url(sizes)
        if not image_url:
            return None
        thumb = ""
        medium = sizes.get("medium")
        if isinstance(medium, dict):
            thumb = str(medium.get("source_url") or "")
        thumb = thumb or image_url

        description = ""
        for key in ("description", "caption"):
            node = item.get(key)
            if isinstance(node, dict):
                text = strip_tags(node.get("rendered"))
                if text:
                    description = text
                    break

        date_text = _extract_date(title)
        inventory = extract_inventory(title, slug)
        theme = classify_theme(title, slug)
        tags = [theme]
        if inventory:
            tags.append(inventory)
        if "in_copyright" not in tags:
            tags.append("in_copyright")

        return Asset.build(
            self.id,
            str(media_id),
            title=title,
            description=description,
            date_text=date_text,
            year=parse_year(date_text or title),
            license=self.descriptor.license,
            rights=self.descriptor.rights or "in_copyright",
            page_url=str(item.get("link") or "") or None,
            image_url=image_url,
            thumbnail_url=thumb,
            width=_coerce_int(details.get("width")),
            height=_coerce_int(details.get("height")),
            tags=tags,
            extra={
                "media_id": media_id,
                "slug": slug,
                "parent_post": item.get("post"),
                "mime_type": item.get("mime_type"),
                "wp_date": item.get("date"),
                "inventory": inventory,
                "theme": theme,
                "sizes": sorted(sizes) if isinstance(sizes, dict) else [],
                "credit": (self.descriptor.extra or {}).get("credit"),
            },
        )

    @staticmethod
    def _rank(assets: list[Asset], query: str) -> list[Asset]:
        """Stable re-rank so query-matching fonds images surface first."""
        tokens = [t for t in normalise(query).split() if len(t) >= 3]
        if not tokens:
            return assets

        def score(asset: Asset) -> int:
            haystack = normalise(
                f"{asset.title} {asset.extra.get('slug', '')} {' '.join(asset.tags)}"
            )
            return sum(1 for token in tokens if token in haystack)

        return sorted(assets, key=lambda asset: -score(asset))

    # ── lazy image download with Latin-1 + dead-upload fallback ───────────
    async def fetch(self, asset: Asset) -> bytes | None:
        candidates: list[str] = []
        for url in (asset.image_url, asset.thumbnail_url):
            if not url:
                continue
            for candidate in (url, latin1_url(url)):
                if candidate and candidate not in candidates:
                    candidates.append(candidate)
        for url in candidates:
            try:
                resp = await self.http.get(url, accept="image/*, */*;q=0.5")
            except Exception:  # noqa: BLE001 - try the next candidate
                continue
            ctype = resp.headers.get("content-type", "")
            if resp.status_code == 200 and ctype.startswith("image/"):
                return resp.content
        return None

    async def health(self) -> bool:
        endpoint = str(
            (self.descriptor.extra or {}).get("media_endpoint")
            or f"{self.descriptor.base_url.rstrip('/')}/wp-json/wp/v2/media"
        )
        try:
            resp = await self._get_page(endpoint, {"media_type": "image", "per_page": 1})
        except Exception:  # noqa: BLE001
            return False
        return resp is not None
