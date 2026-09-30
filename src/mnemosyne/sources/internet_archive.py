"""Internet Archive advanced search (mediatype:image)."""

from __future__ import annotations

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year


def _as_str(value) -> str | None:
    if isinstance(value, list):
        return value[0] if value else None
    return value or None


class InternetArchiveConnector(Connector):
    async def search(self, query: str, limit: int = 20, **filters) -> list[Asset]:
        params = {
            "q": f"({query}) AND mediatype:image",
            "fl[]": [
                "identifier",
                "title",
                "creator",
                "date",
                "licenseurl",
                "description",
            ],
            "rows": str(min(limit, 50)),
            "page": "1",
            "output": "json",
        }
        data = await self.http.get_json(self.descriptor.base_url, params=params)
        docs = data.get("response", {}).get("docs", [])
        assets: list[Asset] = []
        for doc in docs:
            identifier = doc.get("identifier")
            if not identifier:
                continue
            date_text = _as_str(doc.get("date"))
            assets.append(
                Asset.build(
                    self.id,
                    identifier,
                    title=_as_str(doc.get("title")) or identifier,
                    description=_as_str(doc.get("description")) or "",
                    creator=_as_str(doc.get("creator")),
                    date_text=date_text,
                    year=parse_year(date_text),
                    license=_as_str(doc.get("licenseurl")) or self.descriptor.license,
                    rights=self.descriptor.rights,
                    page_url=f"https://archive.org/details/{identifier}",
                    image_url=f"https://archive.org/services/img/{identifier}",
                    thumbnail_url=f"https://archive.org/services/img/{identifier}",
                    extra={"ia_identifier": identifier},
                )
            )
        return assets
