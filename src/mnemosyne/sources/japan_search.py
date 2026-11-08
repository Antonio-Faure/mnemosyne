"""Japan Search (ジャパンサーチ) — national cross-database aggregator (jps-cross REST API).

The public endpoint is keyless. We only keep image records flagged as openly
licensed (public domain / CC0 / CC BY) and reachable on the internet. Images are
referenced by URL only — nothing is downloaded here.
"""

from __future__ import annotations

from typing import Any

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

_SEARCH_PATH = "/item/search/jps-cross"

#: rights code reported by Japan Search -> SPDX-style licence identifier
_LICENSE_BY_CODE = {
    "pdm": "PDM-1.0",
    "cc0": "CC0-1.0",
    "ccby": "CC-BY-4.0",
}

#: rights codes requested via repeated ``f-rights`` params (the leading ``+``
#: makes the API OR the values together)
_RIGHTS_FILTERS = ("+pdm", "+cc0", "+ccby")

#: descriptions are trimmed to keep the canonical record light
_DESCRIPTION_MAX = 600


def _first_str(value: Any) -> str | None:
    """First non-empty string of a str or list field, else ``None``."""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


def _http_url(value: Any) -> str | None:
    """First ``http(s)`` URL found in a str or list field, else ``None``."""
    items = value if isinstance(value, list) else [value]
    for item in items:
        if isinstance(item, str) and item.strip().startswith(("http://", "https://")):
            return item.strip()
    return None


class JapanSearchConnector(Connector):
    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        page_size = min(max(limit * 2, 10), 100)
        max_pages = int(filters.get("max_pages", 3))
        url = self.descriptor.base_url.rstrip("/") + _SEARCH_PATH

        assets: list[Asset] = []
        seen: set[str] = set()
        offset = 0
        hit_total: int | None = None

        for _ in range(max_pages):
            # A list of tuples is required: ``f-rights`` is repeated (OR filter),
            # which a plain dict cannot express.
            params: list[tuple[str, str]] = [
                ("keyword", query),
                ("size", str(page_size)),
                ("from", str(offset)),
                ("f-contents", "image"),
                ("f-caccess", "internet"),
            ]
            params.extend(("f-rights", code) for code in _RIGHTS_FILTERS)

            resp = await self.http.get(url, params=params)
            try:
                payload = resp.json()
            except Exception:
                break
            if not isinstance(payload, dict):
                break

            hit_total = payload.get("hit")
            records = payload.get("list") or []
            if not records:
                break

            for record in records:
                common = record.get("common") if isinstance(record, dict) else None
                if not isinstance(common, dict):
                    continue
                asset = self._build_asset(common)
                if asset is None or asset.source_asset_id in seen:
                    continue
                seen.add(asset.source_asset_id)
                assets.append(asset)
                if len(assets) >= limit:
                    return assets

            offset += page_size
            if isinstance(hit_total, int) and offset >= hit_total:
                break

        return assets

    def _build_asset(self, common: dict[str, Any]) -> Asset | None:
        contents_type = str(common.get("contentsType") or "").strip().lower()
        if contents_type != "image":
            return None
        access = str(common.get("contentsAccess") or "").strip().lower()
        if access != "internet":
            return None

        raw_code = common.get("contentsRightsType")
        rights_code = raw_code.strip().lower() if isinstance(raw_code, str) else ""
        if rights_code not in _LICENSE_BY_CODE:
            return None

        image_url = _http_url(common.get("contentsUrl"))
        thumbnail_url = _http_url(common.get("thumbnailUrl"))
        if not image_url and not thumbnail_url:
            return None
        image_url = image_url or thumbnail_url
        thumbnail_url = thumbnail_url or image_url

        jpsearch_id = common.get("id")
        if not jpsearch_id:
            return None
        jpsearch_id = str(jpsearch_id)

        page_url = (
            _first_str(common.get("linkUrl"))
            or _first_str(common.get("providerUrl"))
            or f"https://jpsearch.go.jp/item/{jpsearch_id}"
        )

        title = _first_str(common.get("title")) or _first_str(common.get("titleEn")) or ""

        contributors = common.get("contributor")
        if isinstance(contributors, list):
            names = [c.strip() for c in contributors[:3] if isinstance(c, str) and c.strip()]
            creator = ", ".join(names) or None
        else:
            creator = _first_str(contributors)

        description = (
            _first_str(common.get("description")) or _first_str(common.get("descriptionEn")) or ""
        )
        if len(description) > _DESCRIPTION_MAX:
            description = description[:_DESCRIPTION_MAX].rstrip() + "…"

        temporal = common.get("temporal")
        if isinstance(temporal, list):
            date_text = ", ".join(
                t.strip() for t in temporal if isinstance(t, str) and t.strip()
            ) or None
        else:
            date_text = _first_str(temporal)

        license_code = _LICENSE_BY_CODE[rights_code]
        rights = f"Japan Search — contenu marqué {rights_code} ; vérifier par notice"

        return Asset.build(
            self.id,
            jpsearch_id,
            title=title,
            description=description,
            creator=creator,
            date_text=date_text,
            year=parse_year(date_text),
            license=license_code,
            rights=rights,
            page_url=page_url,
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            extra={
                "jpsearch_id": jpsearch_id,
                "database": common.get("database"),
                "provider": common.get("provider"),
                "ownerOrg": common.get("ownerOrg"),
                "rights_code": rights_code,
                "contents_type": common.get("contentsType"),
            },
        )
