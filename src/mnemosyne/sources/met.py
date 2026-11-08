"""The Metropolitan Museum of Art — Open Access (REST, keyless, CC0).

The Met retired its ``/public/collection/v1/search`` endpoint on 2026-10-01
(HTTP 410 Gone). Search now lives under ``/public/collection/v1.1/search`` and
returns ``{"total": ..., "objectIDs": [...]}``; each object is then resolved
one by one via ``/public/collection/v1/objects/<id>``. Only records flagged
``isPublicDomain == true`` *and* carrying a non-empty ``primaryImage`` are kept,
so every normalised :class:`Asset` is a public-domain (CC0) image. Images are
never downloaded here — only their URLs are stored.

A per-object look-up that returns HTTP 404 (the search can surface ids whose
record was withdrawn) is skipped quietly instead of failing the whole source;
any other status (401/403 access, 5xx outage) is a real error and propagates.
"""

from __future__ import annotations

from typing import Any

import httpx

from mnemosyne.connectors.base import Connector
from mnemosyne.logger import get_logger
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

log = get_logger("sources.met")

#: how many object look-ups we are willing to make for ``limit`` public assets
_ATTEMPT_FACTOR = 4


def _is_public_domain(item: dict[str, Any]) -> bool:
    value = item.get("isPublicDomain")
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _description(item: dict[str, Any]) -> str:
    parts = [item.get("medium"), item.get("classification")]
    return " ; ".join(str(p).strip() for p in parts if p and str(p).strip())


def _year(item: dict[str, Any]) -> int | None:
    begin = item.get("objectBeginDate")
    if isinstance(begin, int) and begin > 0:
        return begin
    return parse_year(item.get("objectDate"))


class MetConnector(Connector):
    """Normalizes the Met Open Access API into canonical `Asset`s."""

    def _search_url(self) -> str:
        # base_url points at the ``/v1`` root; the search lives under ``/v1.1``.
        base = self.descriptor.base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        return base + "/v1.1/search"

    def _object_url(self, object_id: Any) -> str:
        return self.descriptor.base_url.rstrip("/") + f"/objects/{object_id}"

    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        if limit <= 0:
            return []
        data = await self.http.get_json(
            self._search_url(), params={"q": query, "hasImages": "true"}
        )
        ids = data.get("objectIDs") if isinstance(data, dict) else None
        if not ids:
            return []

        max_attempts = limit * _ATTEMPT_FACTOR
        assets: list[Asset] = []
        attempts = 0
        for object_id in ids:
            if len(assets) >= limit or attempts >= max_attempts:
                break
            attempts += 1
            try:
                item = await self.http.get_json(self._object_url(object_id))
            except httpx.HTTPStatusError as exc:
                # A withdrawn/absent object id (HTTP 404) is expected — skip it
                # rather than surfacing it as a source error. Any other status
                # (401/403 access, 5xx outage) is a real error: do not mask it.
                if exc.response.status_code == 404:
                    log.debug("met: object %s not found (404); skipping", object_id)
                    continue
                raise
            if not isinstance(item, dict):
                continue
            asset = self._to_asset(item)
            if asset is not None:
                assets.append(asset)

        if len(assets) < limit:
            log.debug(
                "met: collected %d/%d public assets after %d object look-ups",
                len(assets),
                limit,
                attempts,
            )
        return assets

    def _to_asset(self, item: dict[str, Any]) -> Asset | None:
        if not _is_public_domain(item):
            return None
        image_url = _first_text(item.get("primaryImage"))
        if not image_url:
            return None
        object_id = item.get("objectID")
        if object_id is None:
            return None
        thumbnail_url = _first_text(item.get("primaryImageSmall")) or image_url
        return Asset.build(
            self.id,
            str(object_id),
            title=_first_text(item.get("title")) or f"Met object {object_id}",
            creator=_first_text(item.get("artistDisplayName")),
            description=_description(item),
            date_text=_first_text(item.get("objectDate")),
            year=_year(item),
            license=self.descriptor.license,
            rights=_first_text(item.get("creditLine")) or self.descriptor.rights,
            page_url=_first_text(item.get("objectURL")),
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            extra={
                "met_object_id": object_id,
                "department": item.get("department"),
                "classification": item.get("classification"),
                "credit_line": item.get("creditLine"),
            },
        )
