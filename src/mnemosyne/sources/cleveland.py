"""Cleveland Museum of Art Open Access API (REST, keyless, CC0)."""

from __future__ import annotations

from typing import Any

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year


def _first_creator(item: dict[str, Any]) -> str | None:
    creators = item.get("creators") or []
    if isinstance(creators, list) and creators:
        first = creators[0]
        if isinstance(first, dict):
            return first.get("description") or first.get("name")
    return None


def _image_url(item: dict[str, Any]) -> str | None:
    images = item.get("images") or {}
    if not isinstance(images, dict):
        return None
    for key in ("web", "print", "full"):
        img = images.get(key)
        if isinstance(img, dict) and img.get("url"):
            return img["url"]
    return None


class ClevelandConnector(Connector):
    """Normalizes the Cleveland Open Access API into canonical `Asset`s."""

    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        params = {
            "q": query,
            "limit": str(min(limit, 50)),
            "has_image": "1",
        }
        data = await self.http.get_json(self.descriptor.base_url, params=params)
        items = data.get("data", []) if isinstance(data, dict) else []

        assets: list[Asset] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            cid = item.get("id")
            if cid is None:
                continue
            image_url = _image_url(item)
            if not image_url:
                continue
            date_text = item.get("creation_date")
            assets.append(
                Asset.build(
                    self.id,
                    str(cid),
                    title=item.get("title") or f"Cleveland artwork {cid}",
                    description=item.get("technique") or "",
                    creator=_first_creator(item),
                    date_text=date_text,
                    year=parse_year(date_text),
                    license=self.descriptor.license,
                    rights=item.get("copyright") or self.descriptor.rights,
                    page_url=item.get("url") or f"https://www.clevelandart.org/art/{cid}",
                    image_url=image_url,
                    thumbnail_url=image_url,
                    extra={
                        "cleveland_id": cid,
                        "accession_number": item.get("accession_number"),
                    },
                )
            )
            if len(assets) >= limit:
                break
        return assets
