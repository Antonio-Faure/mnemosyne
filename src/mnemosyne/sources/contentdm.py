"""CONTENTdm cross-collection search (keyless, JSON) into canonical assets.

One generic connector serving every CONTENTdm host (TeVA, SCDL, Indiana
Memory, BYU, ...). Only the official JSON API is used — never HTML scraping:

* search:      GET {base}/digital/api/search/searchterm/<query>?maxRecords=10&start=<n>
* single item: GET {base}/digital/api/singleitem/collection/<alias>/id/<id>

Each search hit is resolved through its single-item record to read
``contentType``/``imageUri`` (image filter) and the ``fields`` list (metadata)
where the rights statements actually live. A single item returning 404 or a
non-image is skipped without failing the whole connector.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

#: rights-bearing fields. CONTENTdm keys are truncated to six chars, so
#: "copyright" shows up as "copyri", "rights" as "rights"/"righta", etc.
_RIGHTS_HINTS = ("right", "copyri", "licen", "usage", "access")

#: markers proving a clear, per-record open licence.
_OPEN_MARKERS = (
    "public domain",
    "no copyright",
    "noc-us",
    "no known copyright restrictions",
    "cc0",
    "creativecommons.org/publicdomain/zero",
    "cc by",
    "creativecommons.org/licenses/by/",
)

#: markers that must win over any open marker (checked first). Keep these
#: specific: generic words like "contact" or "permission" also appear in open
#: statements ("Public Domain ... please contact ...", "without permission").
_BAD_MARKERS = (
    "not evaluated",
    "undetermined",
    "all rights reserved",
    "may be protected",
    "permission required",
    "contact host",
    "contact for permission",
    "contact us for permission",
    "educational purposes only",
    "not-for-profit purposes",
    "personal, educational",
    "in copyright",
    "inc/",
    "by-nc",
    "by-nd",
)

_URL_RE = re.compile(r"https?://[^\s;]+")

_DESCRIPTION_MAX = 600


def _as_str(value: Any) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    text = str(value)
    return text if text.strip() else None


def _field(fields: list[dict], keys: set[str], label_contains: tuple[str, ...]) -> str | None:
    """First non-empty field value whose (lowered) key or label matches."""
    for entry in fields or []:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "").lower()
        label = str(entry.get("label") or "").lower()
        if key in keys or any(hint in label for hint in label_contains):
            value = _as_str(entry.get("value"))
            if value is not None:
                return value
    return None


def _rights_values(fields: list[dict]) -> list[str]:
    """Values of every field whose key or label looks like a rights statement."""
    out: list[str] = []
    for entry in fields or []:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "").lower()
        label = str(entry.get("label") or "").lower()
        if any(hint in key or hint in label for hint in _RIGHTS_HINTS):
            value = _as_str(entry.get("value"))
            if value is not None:
                out.append(value)
    return out


def _rights_text(fields: list[dict]) -> str:
    return " ; ".join(_rights_values(fields))


def _is_open(fields: list[dict]) -> bool:
    """Accept a record only when its rights text is explicitly open."""
    text = _rights_text(fields).lower()
    if not text:
        return False
    if any(marker in text for marker in _BAD_MARKERS):
        return False
    return any(marker in text for marker in _OPEN_MARKERS)


def _license_for(rights_text: str) -> str:
    text = rights_text.lower()
    if "cc0" in text or "publicdomain/zero" in text:
        return "CC0-1.0"
    if "creativecommons.org/licenses/by/" in text:
        if "/3.0" in text:
            return "CC-BY-3.0"
        return "CC-BY-4.0"
    return "PDM-1.0"


def _first_url(text: str) -> str | None:
    match = _URL_RE.search(text or "")
    return match.group(0) if match else None


def _absolute(base: str, uri: str) -> str:
    # CONTENTdm sometimes returns http:// image URLs even when the host serves
    # https; upgrade to avoid mixed-content failures in the UI.
    if uri.startswith("http://") and base.startswith("https://"):
        uri = "https://" + uri[len("http://") :]
    if uri.startswith("http://") or uri.startswith("https://"):
        return uri
    if uri.startswith("/"):
        return base + uri
    return base + "/" + uri


def _size_variant(image_url: str, size: str) -> str | None:
    """Rewrite a IIIF ``/full/full/0/`` segment to a bounded size, if present."""
    if "/full/full/0/" in image_url:
        return image_url.replace("/full/full/0/", f"/full/{size}/0/")
    return None


def _digital_url(base: str, relative: str | None) -> str | None:
    if not relative:
        return None
    if relative.startswith("http://") or relative.startswith("https://"):
        return relative
    if relative.startswith("/digital"):
        return base + relative
    if relative.startswith("/"):
        return base + relative
    return base + "/digital/" + relative.lstrip("/")


class ContentDmConnector(Connector):
    """Generic CONTENTdm connector driven by ``self.descriptor.base_url``."""

    PAGE_SIZE = 10

    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        max_pages = int(filters.get("max_pages", 3))
        base = self.descriptor.base_url.rstrip("/")
        search_url = f"{base}/digital/api/search/searchterm/{quote(query, safe='')}"

        assets: list[Asset] = []
        seen: set[tuple[str, str]] = set()
        start = 0

        for _ in range(max_pages):
            if len(assets) >= limit:
                break
            try:
                data = await self.http.get_json(
                    search_url, params={"maxRecords": self.PAGE_SIZE, "start": start}
                )
            except Exception:  # noqa: BLE001 — a failed page must not abort the run
                break
            items = (data or {}).get("items") or []
            if not items:
                break

            for item in items:
                if len(assets) >= limit:
                    break
                if not isinstance(item, dict):
                    continue
                alias = _as_str(item.get("collectionAlias"))
                item_id = _as_str(item.get("itemId"))
                if alias is None or item_id is None:
                    continue
                key = (alias, item_id)
                if key in seen:
                    continue
                seen.add(key)
                asset = await self._item_to_asset(item, alias, item_id, base)
                if asset is not None:
                    assets.append(asset)

            total = data.get("totalResults") if isinstance(data, dict) else None
            start += self.PAGE_SIZE
            if isinstance(total, int) and start >= total:
                break

        return assets[:limit]

    async def _item_to_asset(
        self, item: dict, alias: str, item_id: str, base: str
    ) -> Asset | None:
        """Resolve one search hit through its single-item record, or ``None``."""
        detail_url = (
            f"{base}/digital/api/singleitem/collection/{quote(alias, safe='')}"
            f"/id/{quote(item_id, safe='')}"
        )
        try:
            detail = await self.http.get_json(detail_url)
        except Exception:  # noqa: BLE001 — 404/unreadable item: skip it
            return None
        if not isinstance(detail, dict):
            return None

        content_type = str(detail.get("contentType") or "")
        if not content_type.lower().startswith("image/"):
            return None

        image_uri = _as_str(detail.get("imageUri"))
        if image_uri is None:
            return None
        if not (
            image_uri.startswith("http://")
            or image_uri.startswith("https://")
            or image_uri.startswith("/")
        ):
            return None

        fields = detail.get("fields") or []
        if not isinstance(fields, list):
            fields = []
        if not _is_open(fields):
            return None

        image_full = _absolute(base, image_uri)
        image_url = _size_variant(image_full, "!1200,1200") or image_full
        thumb_source = _as_str(detail.get("thumbnailUri")) or _as_str(item.get("thumbnailUri"))
        thumbnail_url = (
            _size_variant(image_full, "!400,400")
            or _digital_url(base, thumb_source)
            or image_url
        )

        title = (
            _field(fields, {"title"}, ("title",))
            or _as_str(detail.get("title"))
            or _as_str(item.get("title"))
            or f"ContentDM {alias}:{item_id}"
        )
        creator = _field(
            fields,
            {"creato", "autho", "artis", "photo", "contr"},
            ("creator", "author", "artist", "photographer", "contributor"),
        )
        description = _field(
            fields, {"descri", "descrip", "description"}, ("description", "notes")
        ) or ""
        if len(description) > _DESCRIPTION_MAX:
            description = description[:_DESCRIPTION_MAX]
        date_text = _field(fields, {"date", "datea", "issued"}, ("date",))
        rights_text = _rights_text(fields) or None
        collection = _field(fields, {"collec"}, ("collection",)) or alias

        item_link = _as_str(item.get("itemLink"))
        if item_link:
            link = item_link[len("/digital") :] if item_link.startswith("/digital") else item_link
            page_url = base + "/digital" + link
        else:
            page_url = f"{base}/digital/collection/{alias}/id/{item_id}"

        return Asset.build(
            self.id,
            f"{alias}:{item_id}",
            title=title,
            description=description,
            creator=creator,
            date_text=date_text,
            year=parse_year(date_text),
            license=_license_for(rights_text or ""),
            rights=rights_text,
            page_url=page_url,
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            extra={
                "alias": alias,
                "item_id": item_id,
                "collection": collection,
                "content_type": content_type,
                "rights_uri": _first_url(rights_text or ""),
            },
        )
