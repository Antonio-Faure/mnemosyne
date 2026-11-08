"""INA (Institut national de l'audiovisuel) — catalogue notices via Surface A.

The only lawful surface is the legal-deposit catalog ``https://catalogue.ina.fr``
(Inathèque / OPSIS): public HTML search pages whose ``robots.txt`` only blocks
GPTBot/ChatGPT-User (Crawl-delay 5 s), no API key. This connector returns
metadata **notices** + a deep link to each notice — never any media or image
(``reuse_allowed: false``, ``media_download: false``, "Tous droits réservés INA").

The public clip surface (``www.ina.fr``, thumbnails via ``/ajax/recherche``) is
robots/CGU-restricted and gated off: :func:`public_search_allowed` returns
``False`` and :meth:`InaConnector.search_public` raises ``PermissionError``.
"""

from __future__ import annotations

import asyncio
import html as _html
import re
from datetime import date
from urllib.parse import quote_plus, urljoin, urlparse, urlunparse

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

CATALOGUE = "https://catalogue.ina.fr"
SECTION_DEFAULT = "TV-RADIO"
SECTIONS = ("TV-RADIO", "ECRIT", "WEB-MEDIA")
SORT_DEFAULT = "score1"
SORTS = ("score1", "datdif")
BASES = "TVNAT,RADIO,TVSAT,PUBTV,TVREG,CLIPTV,DLDON"
NB_LIGNES = (20, 50, 100, 500)
DEFAULT_NB_ROWS = 50
CRAWL_DELAY = 5.0
MAX_PAGES = 20
LICENSE = "Tous droits réservés © INA"
NOTICE_TYPE = "audiovisual-archive-notice"
PUBLIC_SEARCH_ALLOWED = False
PUBLIC_SEARCH_ENDPOINT = (
    "https://www.ina.fr/ajax/recherche?q={query}&media=2&espace=1&offset={offset}"
)

#: OPSIS field code -> human label (used as fallback when the ``id`` is absent).
FIELD_MAP = {
    "NO": "ID Notice",
    "TI": "Titre propre",
    "TICOL": "Titre collection",
    "TIPROG": "Titre programme",
    "CH": "Chaîne de diffusion",
    "DATDIF": "Date de diffusion",
    "JOUR": "Jour",
    "DATENG": "Date d'enregistrement",
    "STADIF": "Statut",
    "HEURE": "Heure",
    "HEUREFIN": "Heure de fin",
    "DUREE": "Durée",
    "THEMAT": "Thématique",
    "GENRE": "Genre",
    "TYPDESCR": "Type de descripteur",
    "GEN": "Générique",
    "DE": "Descripteurs",
    "DES": "Descripteurs secondaires",
    "RES": "Résumé documentaire",
    "CHAP": "Chapeau",
    "SEQ": "Dispositifs",
    "GEO": "Extension géographique",
    "NATPRO": "Nature du programme",
    "PROD": "Producteurs",
    "BASE": "Base",
    "SELDL": "Sélection dépôt légal",
    "DL": "Dépôt légal",
    "FONDS": "Fonds",
    "TIDL": "Titre dépôt légal",
}

_TOTAL_RE = re.compile(r"Enregistrements.*?sur\s+([\d][\d\s\u00a0.,]*)", re.S | re.I)
_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_TABLE_RE = re.compile(
    r"<table[^>]*tableau-header-gris[^>]*>(.*?)</table>", re.S | re.I
)
_ROW_RE = re.compile(
    r'<tr[^>]*class="[^"]*result_line_(?:a|b)[^"]*"[^>]*>(.*?)</tr>', re.S | re.I
)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_HREF_RE = re.compile(r'href="([^"]+)"', re.I)
_NOTICE_FIELD_RE = re.compile(
    r'<td[^>]*class="[^"]*label_champs_form[^"]*"[^>]*>(?P<label>.*?)</td>\s*'
    r"<td(?P<vattrs>[^>]*)>(?P<value>.*?)</td>",
    re.S | re.I,
)
_ID_ATTR_RE = re.compile(r'id="([^"]+)"')
_DOC_ID_RE = re.compile(r"/doc/[^/]+/([A-Za-z]{2}_[A-Za-z0-9.]+)")
_DOC_FALLBACK_RE = re.compile(r"([A-Z]{2}_[A-Za-z0-9.]+)")


def _clean(fragment: str | None) -> str:
    """Strip tags, unescape entities and collapse whitespace."""
    if not fragment:
        return ""
    text = re.sub(r"<[^>]+>", " ", fragment)
    text = _html.unescape(text)
    text = text.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _null_or(text: str | None) -> str | None:
    cleaned = _clean(text)
    return cleaned or None


def total_from(html: str | None) -> int | None:
    """Read the ``Enregistrements <a> à <b> sur <TOTAL>`` counter of a page."""
    if not html:
        return None
    match = _TOTAL_RE.search(_html.unescape(html))
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    return int(digits) if digits else None


def parse_date_fr(text: str | None) -> str | None:
    """Normalise a ``DD/MM/YYYY`` French date to ISO (``YYYY-MM-DD``)."""
    if not text:
        return None
    match = _DATE_RE.search(str(text))
    if not match:
        return None
    day, month, year = (int(group) for group in match.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_duration(text: str | None) -> int | None:
    """Parse ``HH:MM:SS[:FF]`` (or ``MM:SS``) to whole seconds; frames ignored."""
    if not text:
        return None
    parts = [_clean(part) for part in str(text).split(":")]
    if not parts or any(not part.isdigit() for part in parts):
        return None
    numbers = [int(part) for part in parts]
    if len(numbers) == 2:
        minutes, seconds = numbers
        return minutes * 60 + seconds
    if len(numbers) >= 3:
        hours, minutes, seconds = numbers[0], numbers[1], numbers[2]
        return hours * 3600 + minutes * 60 + seconds
    return None


def _split_keywords(text: str | None) -> list[str]:
    if not text:
        return []
    return [kw.strip() for kw in re.split(r"\s*;\s*", _clean(text)) if kw.strip()]


def _dedup(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.casefold()
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _doc_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    match = _DOC_ID_RE.search(url)
    if match:
        return match.group(1)
    match = _DOC_FALLBACK_RE.search(url)
    return match.group(1) if match else None


def _normalise_href(href: str | None) -> str | None:
    """Resolve the notice href to an absolute URL and drop its query string."""
    if not href:
        return None
    absolute = urljoin(CATALOGUE + "/", href.strip())
    parsed = urlparse(absolute)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def _clamp_nb(value: object) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_NB_ROWS
    return number if number in NB_LIGNES else DEFAULT_NB_ROWS


def build_search_url(
    query: str,
    *,
    section: str = SECTION_DEFAULT,
    bases: str = BASES,
    sort: str = SORT_DEFAULT,
    n_rows: int = DEFAULT_NB_ROWS,
    page: int = 1,
) -> str:
    """Build a Surface A (catalogue.ina.fr) ``docListe`` search URL."""
    if sort not in SORTS:
        raise ValueError(f"unsupported sort {sort!r}; expected one of {SORTS}")
    if n_rows not in NB_LIGNES:
        raise ValueError(f"unsupported nbLignes {n_rows!r}; expected one of {NB_LIGNES}")
    if page < 1:
        raise ValueError("page is 1-based")
    return (
        f"{CATALOGUE}/docListe/{section}/?"
        f"base_label={bases}&"
        f"itoustext={quote_plus(query)}&"
        "sujets_filter=Sujet&"
        "bool_operator=AND&"
        f"tri={sort}&"
        f"nbLignes={n_rows}&"
        f"page={page}"
    )


def _row_from_cells(cells: list[str]) -> dict:
    padded = cells + [""] * (9 - len(cells))
    title_cell = padded[5]
    href_match = _HREF_RE.search(title_cell)
    notice_url = _normalise_href(href_match.group(1)) if href_match else None
    date_raw = _null_or(padded[2])
    return {
        "index": _null_or(padded[0]),
        "channel": _null_or(padded[1]),
        "date_raw": date_raw,
        "date_iso": parse_date_fr(date_raw),
        "time": _null_or(padded[3]),
        "duration_raw": _null_or(padded[4]),
        "duration_seconds": parse_duration(padded[4]),
        "title": _clean(title_cell),
        "notice_url": notice_url,
        "doc_id": _doc_id_from_url(notice_url),
        "collection": _null_or(padded[6]),
        "programme": _null_or(padded[7]),
        "genre": _null_or(padded[8]),
    }


def _parse_rows(html: str | None) -> list[dict]:
    if not html:
        return []
    tables = _TABLE_RE.findall(html)
    scope = "\n".join(tables) if tables else html
    return [_row_from_cells(_CELL_RE.findall(row)) for row in _ROW_RE.findall(scope)]


def parse_search_page(html: str | None) -> tuple[int | None, list[dict]]:
    """Return ``(total, rows)`` for a catalogue.ina.fr ``docListe`` page."""
    return total_from(html), _parse_rows(html)


def parse_notice(html: str | None, url: str | None = None) -> dict:
    """Parse an OPSIS notice page into a normalised metadata dict (no media)."""
    result: dict = {
        "id": None,
        "page_url": url,
        "title": None,
        "description": None,
        "keywords": [],
        "date_raw": None,
        "date_iso": None,
        "year": None,
        "channel": None,
        "genre": None,
        "duration_raw": None,
        "duration_seconds": None,
        "collection": None,
        "programme": None,
        "geo": None,
        "licence": LICENSE,
        "type": NOTICE_TYPE,
        "image_url": None,
        "media_url": None,
        "fields": {},
    }
    if not html:
        result["id"] = _doc_id_from_url(url)
        return result

    by_code: dict[str, str | None] = {}
    by_label: dict[str, str | None] = {}
    for match in _NOTICE_FIELD_RE.finditer(html):
        label = _clean(match.group("label"))
        value = _clean(match.group("value"))
        code_match = _ID_ATTR_RE.search(match.group("vattrs") or "")
        code = code_match.group(1).strip().upper() if code_match else None
        if code:
            by_code[code] = value or None
        if label:
            by_label[label.casefold()] = value or None

    def get(code: str) -> str | None:
        value = by_code.get(code)
        if value:
            return value
        label = FIELD_MAP.get(code)
        if label:
            return by_label.get(label.casefold())
        return None

    result["fields"] = dict(by_code)
    result["id"] = get("NO") or _doc_id_from_url(url)
    result["title"] = get("TI")
    result["description"] = get("RES") or get("CHAP")
    result["keywords"] = _dedup(_split_keywords(get("DE")) + _split_keywords(get("DES")))
    result["date_raw"] = get("DATDIF")
    result["date_iso"] = parse_date_fr(result["date_raw"])
    result["year"] = parse_year(result["date_iso"] or result["date_raw"])
    result["channel"] = get("CH")
    result["genre"] = get("GENRE")
    result["duration_raw"] = get("DUREE")
    result["duration_seconds"] = parse_duration(result["duration_raw"])
    result["collection"] = get("TICOL")
    result["programme"] = get("TIPROG")
    result["geo"] = get("GEO")
    return result


def public_search_allowed() -> bool:
    """Surface B (www.ina.fr public clips) is robots/CGU-restricted — off."""
    return PUBLIC_SEARCH_ALLOWED


class InaConnector(Connector):
    """Normalise INA catalogue notices into :class:`Asset` (metadata-only)."""

    @property
    def section(self) -> str:
        value = self.descriptor.extra.get("section")
        return value if value in SECTIONS else SECTION_DEFAULT

    @property
    def sort(self) -> str:
        value = self.descriptor.extra.get("sort")
        return value if value in SORTS else SORT_DEFAULT

    @property
    def default_nb_rows(self) -> int:
        return _clamp_nb(self.descriptor.extra.get("nb_rows"))

    @property
    def crawl_delay(self) -> float:
        raw = self.descriptor.extra.get("crawl_delay_s", CRAWL_DELAY)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return CRAWL_DELAY
        return value if value >= 0 else CRAWL_DELAY

    async def _pace(self, seconds: float) -> None:
        """Politeness delay (test seam: subclasses may override)."""
        if seconds and seconds > 0:
            await asyncio.sleep(seconds)

    def _row_to_asset(self, row: dict) -> Asset:
        source_asset_id = row.get("doc_id") or row.get("notice_url") or ""
        return Asset.build(
            self.id,
            str(source_asset_id),
            title=row.get("title") or "",
            description="",
            date_text=row.get("date_iso") or row.get("date_raw"),
            year=parse_year(row.get("date_iso") or row.get("date_raw")),
            license=self.descriptor.license or LICENSE,
            rights=self.descriptor.rights,
            page_url=row.get("notice_url"),
            image_url=None,
            thumbnail_url=None,
            tags=[],
            extra={
                "type": NOTICE_TYPE,
                "section": self.section,
                "channel": row.get("channel"),
                "genre": row.get("genre"),
                "collection": row.get("collection"),
                "programme": row.get("programme"),
                "duration": row.get("duration_raw"),
                "duration_seconds": row.get("duration_seconds"),
                "date_display": row.get("date_raw"),
                "image_url": None,
                "media_url": None,
            },
        )

    def notice_to_asset(self, notice: dict) -> Asset:
        source_asset_id = notice.get("id") or notice.get("page_url") or ""
        return Asset.build(
            self.id,
            str(source_asset_id),
            title=notice.get("title") or "",
            description=notice.get("description") or "",
            date_text=notice.get("date_iso") or notice.get("date_raw"),
            year=notice.get("year")
            or parse_year(notice.get("date_iso") or notice.get("date_raw")),
            license=self.descriptor.license or LICENSE,
            rights=self.descriptor.rights,
            page_url=notice.get("page_url"),
            image_url=None,
            thumbnail_url=None,
            tags=list(notice.get("keywords") or []),
            extra={
                "type": NOTICE_TYPE,
                "channel": notice.get("channel"),
                "genre": notice.get("genre"),
                "collection": notice.get("collection"),
                "programme": notice.get("programme"),
                "geo": notice.get("geo"),
                "duration": notice.get("duration_raw"),
                "duration_seconds": notice.get("duration_seconds"),
                "date_display": notice.get("date_raw"),
                "licence": notice.get("licence"),
                "image_url": None,
                "media_url": None,
            },
        )

    async def get_notice(self, url: str) -> dict:
        resp = await self.http.get(url, accept="*/*")
        return parse_notice(resp.text, url=url)

    async def search(self, query: str, limit: int = 20, **filters) -> list[Asset]:
        return await self.search_all(
            query,
            max_results=limit,
            section=filters.get("section"),
            sort=filters.get("sort"),
            n_rows=filters.get("n_rows"),
            enrich=bool(filters.get("enrich", False)),
        )

    async def search_all(
        self,
        query: str,
        max_results: int = 20,
        *,
        section: str | None = None,
        sort: str | None = None,
        n_rows: int | None = None,
        enrich: bool = False,
    ) -> list[Asset]:
        section = section or self.section
        sort = sort if sort in SORTS else self.sort
        n_rows = _clamp_nb(n_rows) if n_rows is not None else self.default_nb_rows

        assets: list[Asset] = []
        seen: set[str] = set()
        seen_rows = 0
        total: int | None = None
        page = 1
        while page <= MAX_PAGES and len(assets) < max_results:
            url = build_search_url(
                query, section=section, sort=sort, n_rows=n_rows, page=page
            )
            resp = await self.http.get(url, accept="*/*")
            page_total, rows = parse_search_page(resp.text)
            if total is None:
                total = page_total
            if not rows:
                break
            added = 0
            for row in rows:
                key = row.get("doc_id") or row.get("notice_url") or row.get("title")
                if not key or key in seen:
                    continue
                seen.add(key)
                assets.append(self._row_to_asset(row))
                added += 1
                if len(assets) >= max_results:
                    break
            seen_rows += len(rows)
            if len(assets) >= max_results:
                break
            if added == 0:
                break
            if total is not None and seen_rows >= total:
                break
            page += 1
            await self._pace(self.crawl_delay)

        assets = assets[:max_results]
        if enrich:
            assets = [await self._enrich(asset) for asset in assets]
        return assets

    async def _enrich(self, asset: Asset) -> Asset:
        if not asset.page_url:
            return asset
        await self._pace(self.crawl_delay)
        return self.notice_to_asset(await self.get_notice(asset.page_url))

    async def fetch(self, asset: Asset) -> bytes | None:
        """INA notices are metadata-only: never download any media."""
        return None

    async def search_public(self, query: str, limit: int = 20, **filters) -> str:
        """Surface B (www.ina.fr) — gated off until written permission is on file."""
        if not public_search_allowed():
            raise PermissionError(
                "www.ina.fr public clip search is robots/CGU-restricted; written "
                "permission from mediaclip / INA mediapro is required before "
                "enabling Surface B (see docs/sources/ina.md)."
            )
        endpoint = (
            self.descriptor.extra.get("public_search_endpoint")
            or PUBLIC_SEARCH_ENDPOINT
        )
        offset = int(filters.get("offset", 0))
        url = endpoint.format(query=quote_plus(query), offset=offset)
        resp = await self.http.get(url, accept="application/json")
        return resp.text  # pragma: no cover - only reachable once enabled
