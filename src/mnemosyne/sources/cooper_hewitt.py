"""Cooper Hewitt, Smithsonian Design Museum — public GraphQL collections API.

Open access: no key, no account. The GraphQL endpoint answers GET requests with
the query url-encoded in the ``query`` parameter and returns ``application/json``.
``HttpClient`` has no POST, so we use ``get_json(base_url, params={"query": ...})``.

The provider returns ``summary``, ``date``, ``legal``, ``identifier``,
``department``, ``classification`` and ``multimedia`` as JSON scalars (selected
bare, they come back complete), while ``maker`` is ``[Agent]`` and needs
subfields. We normalize everything into the canonical :class:`Asset` here and
keep only media flagged ``multimedia[].cc0 == True`` with a non-empty image URL
(those media, and the objects carrying them, are CC0). Each qualifying media
becomes one Asset, so one object may yield several Assets.
"""

from __future__ import annotations

from typing import Any

from mnemosyne.connectors.base import Connector
from mnemosyne.logger import get_logger
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

log = get_logger("sources.cooper_hewitt")

#: hard server-side cap on ``size`` (a larger value returns a GraphQL error)
MAX_PAGE_SIZE = 250

#: default bound on how many pages a single search walks (politeness)
DEFAULT_MAX_PAGES = 3

#: fields selected on ``object``. Depth stays <= 2; ``maker`` is ``[Agent]`` and
#: therefore needs its own sub-selection.
_OBJECT_FIELDS = (
    "id summary date maker { id summary } legal identifier "
    "department classification multimedia"
)


def _gql_string(value: str) -> str:
    """Escape a value for embedding inside a GraphQL double-quoted string."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _titles(items: Any) -> list[str]:
    """Titles from a JSON-scalar list of ``{"summary": {"title": ...}}`` entries."""
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        summary = item.get("summary")
        if isinstance(summary, dict):
            title = summary.get("title")
            if title is not None and str(title).strip():
                out.append(str(title).strip())
    return out


def _creator(maker: Any) -> str | None:
    titles = _titles(maker)
    return "; ".join(titles) if titles else None


def _date_text(dates: Any) -> str | None:
    """Display date from the ``[{from, to, value}]`` JSON-scalar list."""
    if not isinstance(dates, list):
        return None
    for entry in dates:
        if isinstance(entry, dict):
            value = entry.get("value")
            if value is not None and str(value).strip():
                return str(value).strip()
    return None


def _media_url(media: dict[str, Any], key: str) -> str | None:
    """URL of a media rendition (``original``/``large``/``preview``).

    Each rendition is an object carrying a ``url``; tolerate a bare string too.
    """
    value = media.get(key)
    if isinstance(value, dict):
        url = value.get("url")
    elif isinstance(value, str):
        url = value
    else:
        url = None
    if url is not None and str(url).strip():
        return str(url).strip()
    return None


class CooperHewittConnector(Connector):
    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        if limit <= 0 or not str(query).strip():
            return []

        q = _gql_string(str(query).strip())
        # A search returns many objects without CC0 media; fetching only `limit`
        # objects can yield zero assets after filtering. Ask for a wider page
        # (still polite: one request) and cap the normalized assets at `limit`.
        page_size = max(1, min(max(limit, 10), MAX_PAGE_SIZE))
        max_pages = max(1, int(filters.get("max_pages", DEFAULT_MAX_PAGES)))

        assets: list[Asset] = []
        # The public API is 0-indexed despite the docs example showing "page: 1"
        # for the first rows: page 0 returns the first page (page 1 is empty).
        page = 0
        while len(assets) < limit and page < max_pages:
            gql = (
                f'{{ object(general: "{q}", hasImages: true, size: {page_size}, '
                f"page: {page}) {{ {_OBJECT_FIELDS} }} }}"
            )
            data = await self.http.get_json(
                self.descriptor.base_url, params={"query": gql}
            )
            objects = self._objects(data)
            if not objects:
                break
            for obj in objects:
                if isinstance(obj, dict):
                    assets.extend(self._object_to_assets(obj))
                if len(assets) >= limit:
                    break
            pagination = (data.get("extensions") or {}).get("pagination") or {}
            total_pages = pagination.get("number_of_pages")
            if total_pages is not None:
                # the API exposes a real page count: stop at the last page
                if page + 1 >= int(total_pages):
                    break
            elif len(objects) < page_size:
                # no metadata: a short page means the result set is exhausted
                break
            page += 1

        return assets[:limit]

    @staticmethod
    def _objects(data: Any) -> list[Any]:
        if not isinstance(data, dict):
            return []
        payload = data.get("data")
        if not isinstance(payload, dict):
            return []
        objects = payload.get("object")
        return objects if isinstance(objects, list) else []

    def _object_to_assets(self, obj: dict[str, Any]) -> list[Asset]:
        """One Asset per CC0 media carrying an image URL (0..n per object)."""
        multimedia = obj.get("multimedia")
        if not isinstance(multimedia, list) or not multimedia:
            return []

        cooper_id = str(obj.get("id") or "").strip()
        numeric_id = cooper_id.split("-", 1)[1] if "-" in cooper_id else cooper_id
        page_url = (
            f"https://collection.cooperhewitt.org/objects/{numeric_id}/"
            if numeric_id
            else None
        )
        title = self._summary_title(obj.get("summary"))
        creator = _creator(obj.get("maker"))
        date_text = _date_text(obj.get("date"))
        department = _titles(obj.get("department"))
        classification = _titles(obj.get("classification"))
        legal = obj.get("legal") if isinstance(obj.get("legal"), dict) else None
        credit = legal.get("credit") if legal else None

        assets: list[Asset] = []
        for media in multimedia:
            if not isinstance(media, dict):
                continue
            if media.get("cc0") is not True:
                continue
            image_url = _media_url(media, "original") or _media_url(media, "large")
            if not image_url:
                continue
            thumbnail = _media_url(media, "preview") or image_url
            media_id = str(media.get("id") or "").strip()

            assets.append(
                Asset.build(
                    self.id,
                    media_id or cooper_id,
                    title=title,
                    creator=creator,
                    date_text=date_text,
                    year=parse_year(date_text),
                    license="CC0-1.0",
                    rights=self.descriptor.rights,
                    page_url=page_url,
                    image_url=image_url,
                    thumbnail_url=thumbnail,
                    tags=classification,
                    extra={
                        "cooper_id": cooper_id,
                        "media_id": media_id or None,
                        "legal": legal,
                        "credit": credit,
                        "department": department,
                        "classification": classification,
                    },
                )
            )
        return assets

    @staticmethod
    def _summary_title(summary: Any) -> str:
        if isinstance(summary, dict):
            title = summary.get("title")
            if title is not None and str(title).strip():
                return str(title).strip()
        return ""
