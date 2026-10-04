"""Smithsonian Open Access — search across Smithsonian collections.

The Smithsonian Open Access API (EDAN) is keyed via the ``api_key`` query
parameter; the key is read from the environment variable named by the
descriptor's ``key_env`` (``SMITHSONIAN_API_KEY``). Without a key the API
returns a plain-text ``API_KEY_MISSING`` body, so this connector degrades
gracefully: it returns no results and never issues an HTTP request.

Provider shapes (``response.rows[]`` with nested ``content.freetext`` and
``content.descriptiveNonRepeating.online_media.media[]``) are normalized into
the canonical :class:`Asset` at this boundary.
"""

from __future__ import annotations

import os
from typing import Any

from mnemosyne.connectors.base import Connector
from mnemosyne.logger import get_logger
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

log = get_logger("sources.smithsonian")


def _freetext_values(freetext: Any, field: str) -> list[str]:
    """Extract the ``content`` of every entry of a freetext field."""
    if not isinstance(freetext, dict):
        return []
    entries = freetext.get(field)
    if not isinstance(entries, list):
        return []
    values: list[str] = []
    for entry in entries:
        if isinstance(entry, dict):
            content = entry.get("content")
            if content is not None and str(content).strip():
                values.append(str(content).strip())
    return values


def _first(values: list[str]) -> str | None:
    return values[0] if values else None


class SmithsonianConnector(Connector):
    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        key = self._api_key()
        if not key:
            log.warning(
                "smithsonian: no API key (%s unset); skipping search",
                self.descriptor.key_env or "SMITHSONIAN_API_KEY",
            )
            return []

        params: dict[str, Any] = {
            "api_key": key,
            "q": query,
            "start": str(filters.get("start", 0)),
            "rows": str(min(limit, 1000)),
        }
        data = await self.http.get_json(self.descriptor.base_url + "/search", params=params)
        if not isinstance(data, dict):
            return []

        rows = (data.get("response") or {}).get("rows") or []
        assets: list[Asset] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            asset = self._row_to_asset(row)
            if asset is not None:
                assets.append(asset)
            if len(assets) >= limit:
                break
        return assets

    def _api_key(self) -> str | None:
        env_name = self.descriptor.key_env or "SMITHSONIAN_API_KEY"
        key = os.environ.get(env_name)
        if key and key.strip():
            return key.strip()
        extra = self.descriptor.extra.get("api_key")
        return str(extra).strip() if extra else None

    def _row_to_asset(self, row: dict[str, Any]) -> Asset | None:
        content = row.get("content") or {}
        dnr = content.get("descriptiveNonRepeating") or {}
        freetext = content.get("freetext") or {}

        media = self._first_media(dnr)
        if media is None:
            return None
        image_url = media.get("content")
        if not image_url or not str(image_url).strip():
            return None
        image_url = str(image_url).strip()
        thumbnail_url = media.get("thumbnail") or image_url

        title = self._title(row, dnr)
        source_asset_id = str(row.get("id") or dnr.get("record_ID") or image_url)

        date_values = _freetext_values(freetext, "date")
        date_text = _first(date_values)

        return Asset.build(
            self.id,
            source_asset_id,
            title=title,
            description=_first(_freetext_values(freetext, "notes")) or "",
            creator=_first(_freetext_values(freetext, "name")),
            date_text=date_text,
            year=parse_year(date_text),
            license=self._license(media, dnr),
            rights=self.descriptor.rights,
            page_url=dnr.get("record_link") or row.get("url") or None,
            image_url=image_url,
            thumbnail_url=str(thumbnail_url).strip() if thumbnail_url else None,
            tags=_freetext_values(freetext, "topic"),
            extra={
                "unit_code": row.get("unitCode") or dnr.get("unit_code"),
                "data_source": dnr.get("data_source"),
                "media_type": media.get("type"),
                "place": _freetext_values(freetext, "place"),
                "object_type": _freetext_values(freetext, "objectType"),
            },
        )

    @staticmethod
    def _first_media(dnr: dict[str, Any]) -> dict[str, Any] | None:
        online_media = dnr.get("online_media") or {}
        media_list = online_media.get("media") or []
        if isinstance(media_list, list):
            for media in media_list:
                if isinstance(media, dict):
                    return media
        return None

    @staticmethod
    def _title(row: dict[str, Any], dnr: dict[str, Any]) -> str:
        title = row.get("title")
        if title and str(title).strip():
            return str(title).strip()
        dnr_title = dnr.get("title")
        if isinstance(dnr_title, dict) and dnr_title.get("content"):
            return str(dnr_title["content"]).strip()
        return ""

    @staticmethod
    def _license(media: dict[str, Any], dnr: dict[str, Any]) -> str | None:
        usage = media.get("usage") or {}
        if usage.get("access"):
            return str(usage["access"]).strip()
        metadata_usage = dnr.get("metadata_usage") or {}
        if metadata_usage.get("access"):
            return str(metadata_usage["access"]).strip()
        return None
