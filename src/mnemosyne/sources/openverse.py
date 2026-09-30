"""Openverse aggregated CC image search."""

from __future__ import annotations

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year


class OpenverseConnector(Connector):
    async def search(self, query: str, limit: int = 20, **filters) -> list[Asset]:
        params = {"q": query, "page_size": str(min(limit, 50))}
        data = await self.http.get_json(f"{self.descriptor.base_url}/images/", params=params)
        assets: list[Asset] = []
        for item in data.get("results", []):
            created = item.get("created_on") or item.get("indexed_on")
            license_name = item.get("license")
            version = item.get("license_version")
            if license_name and version:
                license_name = f"{license_name} {version}"
            assets.append(
                Asset.build(
                    self.id,
                    str(item.get("id")),
                    title=item.get("title") or "",
                    description=item.get("description") or "",
                    creator=item.get("creator"),
                    date_text=created,
                    year=parse_year(created),
                    license=license_name or self.descriptor.license,
                    rights=self.descriptor.rights,
                    page_url=item.get("foreign_landing_url"),
                    image_url=item.get("url"),
                    thumbnail_url=item.get("thumbnail"),
                    width=item.get("width"),
                    height=item.get("height"),
                    extra={"provider": item.get("provider"), "source": item.get("source")},
                )
            )
        return assets
