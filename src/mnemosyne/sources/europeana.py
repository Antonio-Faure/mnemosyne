"""Europeana aggregate search — Search API v2 (`record/v2/search.json`).

Europeana is a pan-European aggregator of GLAM collections. Its search API is
keyed via a ``wskey`` query parameter; the key is read from the environment
variable named by the descriptor's ``key_env`` (``EUROPEANA_API_KEY``). Without
a key the connector degrades gracefully and returns no results rather than
raising. Provider shapes (multi-valued EDM/Dublin Core fields) are normalized
into the canonical :class:`Asset` at this boundary.
"""

from __future__ import annotations

import os
from typing import Any

from mnemosyne.connectors.base import Connector
from mnemosyne.logger import get_logger
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

log = get_logger("sources.europeana")


def _first(value: Any) -> str | None:
    """Europeana fields are multi-valued (list) or scalar; return the first item."""
    if isinstance(value, list):
        for item in value:
            if item is not None and str(item).strip():
                return str(item).strip()
        return None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if value is not None and str(value).strip():
        return [str(value).strip()]
    return []


class EuropeanaConnector(Connector):
    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        key = self._api_key()
        if not key:
            log.warning(
                "europeana: no API key (%s unset); skipping search",
                self.descriptor.key_env or "EUROPEANA_API_KEY",
            )
            return []

        params = {
            "wskey": key,
            "query": query,
            "rows": str(min(limit, 100)),
            "start": "1",
            "media": "true",
            "qf": "TYPE:IMAGE",
        }
        data = await self.http.get_json(self.descriptor.base_url, params=params)

        assets: list[Asset] = []
        for item in data.get("items", []) or []:
            asset = self._item_to_asset(item)
            if asset is not None:
                assets.append(asset)
            if len(assets) >= limit:
                break
        return assets

    def _api_key(self) -> str | None:
        env_name = self.descriptor.key_env or "EUROPEANA_API_KEY"
        key = os.environ.get(env_name)
        if key and key.strip():
            return key.strip()
        extra = self.descriptor.extra.get("api_key")
        return str(extra).strip() if extra else None

    def _item_to_asset(self, item: dict[str, Any]) -> Asset | None:
        europeana_id = _first(item.get("id")) or ""
        image_url = _first(item.get("edmIsShownBy")) or _first(item.get("edmPreview"))
        if not image_url:
            return None

        thumbnail_url = _first(item.get("edmPreview")) or image_url
        page_url = _first(item.get("guid"))
        if not page_url and europeana_id.startswith("/"):
            page_url = f"https://www.europeana.eu/item{europeana_id}"
        year_text = _first(item.get("year"))

        return Asset.build(
            self.id,
            europeana_id.lstrip("/") or image_url,
            title=_first(item.get("title")) or europeana_id or "",
            description=_first(item.get("dcDescription")) or "",
            creator=_first(item.get("dcCreator")),
            date_text=year_text,
            year=parse_year(year_text),
            license=_first(item.get("rights")) or self.descriptor.license,
            rights=self.descriptor.rights,
            page_url=page_url,
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            extra={
                "europeana_id": europeana_id,
                "data_provider": _first(item.get("dataProvider")),
                "provider": _first(item.get("provider")),
                "country": _as_list(item.get("country")),
            },
        )
