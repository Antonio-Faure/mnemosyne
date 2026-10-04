"""Digital Public Library of America search — REST API v2 (`/v2/items`).

DPLA is a US aggregator of GLAM collections (the American counterpart of
Europeana). Its search API is keyed via the ``api_key`` query parameter; the key
is read from the environment variable named by the descriptor's ``key_env``
(``DPLA_API_KEY``). Without a key the connector degrades gracefully and returns
no results rather than raising.

Provider shapes (nested ``sourceResource`` metadata, multi-valued Dublin Core
fields) are normalized into the canonical :class:`Asset` at this boundary; the
raw provider shape never leaks past it.
"""

from __future__ import annotations

import os
from typing import Any

from mnemosyne.connectors.base import Connector
from mnemosyne.logger import get_logger
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

log = get_logger("sources.dpla")


def _first(value: Any) -> str | None:
    """DPLA fields are multi-valued (list), nested, or scalar; return first text."""
    if isinstance(value, list):
        for item in value:
            text = _first(item)
            if text:
                return text
        return None
    if isinstance(value, dict):
        # e.g. sourceResource.date may be {"begin": "1905", "displayDate": "1905"}
        for key in ("displayDate", "begin", "name", "title"):
            text = _first(value.get(key))
            if text:
                return text
        for item in value.values():
            text = _first(item)
            if text:
                return text
        return None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [t for v in value if (t := _first(v))]
    if value is None:
        return []
    text = _first(value)
    return [text] if text else []


class DplaConnector(Connector):
    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        key = self._api_key()
        if not key:
            log.warning(
                "dpla: no API key (%s unset); skipping search",
                self.descriptor.key_env or "DPLA_API_KEY",
            )
            return []

        params = {
            "api_key": key,
            "q": query,
            "page_size": str(min(limit, 100)),
            "page": "1",
        }
        data = await self.http.get_json(self.descriptor.base_url, params=params)

        assets: list[Asset] = []
        for item in data.get("docs", []) or []:
            asset = self._item_to_asset(item)
            if asset is not None:
                assets.append(asset)
            if len(assets) >= limit:
                break
        return assets

    def _api_key(self) -> str | None:
        env_name = self.descriptor.key_env or "DPLA_API_KEY"
        key = os.environ.get(env_name)
        if key and key.strip():
            return key.strip()
        extra = self.descriptor.extra.get("api_key")
        return str(extra).strip() if extra else None

    def _item_to_asset(self, item: dict[str, Any]) -> Asset | None:
        dpla_id = _first(item.get("id")) or ""
        image_url = _first(item.get("object"))
        if not image_url:
            return None

        source_resource = item.get("sourceResource")
        if not isinstance(source_resource, dict):
            source_resource = {}

        title = _first(source_resource.get("title")) or dpla_id or ""
        date_text = _first(source_resource.get("date"))
        page_url = _first(item.get("isShownAt"))

        return Asset.build(
            self.id,
            dpla_id or image_url,
            title=title,
            description=_first(source_resource.get("description")) or "",
            creator=_first(source_resource.get("creator")),
            date_text=date_text,
            year=parse_year(date_text),
            license=_first(item.get("rights")) or self.descriptor.license,
            rights=self.descriptor.rights,
            page_url=page_url,
            image_url=image_url,
            thumbnail_url=_first(item.get("object")) or image_url,
            extra={
                "dpla_id": dpla_id,
                "data_provider": _first(item.get("dataProvider")),
                "provider": _first(item.get("provider")),
                "subjects": _as_list(source_resource.get("subject")),
            },
        )
