"""NASA Image and Video Library: keyword search over the public REST API."""

from __future__ import annotations

from urllib.parse import quote

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

_SEARCH = "/search"
_DETAILS = "https://images.nasa.gov/details/{nasa_id}"


class NasaConnector(Connector):
    async def search(self, query: str, limit: int = 20, **filters) -> list[Asset]:
        max_pages = int(filters.get("max_pages", 3))
        # ``limit`` may undercount usable items (some have no links), so request
        # at least 10 per page and clamp to the API maximum of 100.
        page_size = min(max(limit, 10), 100)
        url = f"{self.descriptor.base_url.rstrip('/')}{_SEARCH}"

        assets: list[Asset] = []
        page = 1
        while len(assets) < limit and page <= max_pages:
            data = await self.http.get_json(
                url,
                params={
                    "q": query,
                    "media_type": "image",
                    "page_size": page_size,
                    "page": page,
                },
            )
            if not isinstance(data, dict):
                break
            collection = data.get("collection") or {}
            items = collection.get("items") or []
            if not items:
                break
            for item in items:
                asset = self._item_to_asset(item)
                if asset is not None:
                    assets.append(asset)
                    if len(assets) >= limit:
                        break
            total_hits = (collection.get("metadata") or {}).get("total_hits")
            if isinstance(total_hits, int) and page * page_size >= total_hits:
                break
            page += 1
        return assets[:limit]

    def _item_to_asset(self, item: dict) -> Asset | None:
        data_list = item.get("data") or []
        if not data_list:
            return None
        data = data_list[0] or {}
        if data.get("media_type") != "image":
            return None
        hrefs = [
            link.get("href")
            for link in (item.get("links") or [])
            if isinstance(link, dict) and link.get("href")
        ]
        if not hrefs:
            return None
        image_url = self._pick_image(hrefs)
        thumbnail_url = self._pick_thumb(hrefs) or image_url
        nasa_id = data.get("nasa_id") or ""
        return Asset.build(
            self.id,
            nasa_id,
            title=data.get("title") or f"NASA {nasa_id}",
            description=(data.get("description") or "")[:600],
            creator=(
                data.get("photographer")
                or data.get("secondary_creator")
                or data.get("center")
            ),
            date_text=data.get("date_created"),
            year=parse_year(data.get("date_created")),
            license=self.descriptor.license,
            rights=self.descriptor.rights,
            page_url=_DETAILS.format(nasa_id=quote(str(nasa_id))),
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            extra={
                "nasa_id": nasa_id,
                "center": data.get("center"),
                "keywords": data.get("keywords"),
                "location": data.get("location"),
                "photographer": data.get("photographer"),
                "secondary_creator": data.get("secondary_creator"),
            },
        )

    @staticmethod
    def _pick_image(hrefs: list[str]) -> str:
        for marker in ("~large", "~medium", "~orig"):
            for href in hrefs:
                if marker in href:
                    return href
        return hrefs[0]

    @staticmethod
    def _pick_thumb(hrefs: list[str]) -> str | None:
        for href in hrefs:
            if "~thumb" in href:
                return href
        return None
