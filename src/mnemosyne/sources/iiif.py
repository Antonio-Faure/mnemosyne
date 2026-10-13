"""Generic IIIF connector — one code path for every IIIF host.

IIIF has no universal search endpoint, so a descriptor must point at an entry
point in `extra`:

* `collection`: a IIIF Collection manifest URL (enumerate its manifests), or
* `manifest`: a single IIIF manifest URL.

For each manifest we normalize the label/metadata/rights and the first canvas
image (served by the IIIF Image API) into the canonical `Asset`. Works with both
Presentation v2 (`sequences`/`canvases`/`images`/`resource`) and v3
(`items`/`body`).
"""

from __future__ import annotations

import re
from typing import Any

from mnemosyne.connectors.base import Connector
from mnemosyne.logger import get_logger
from mnemosyne.models import Asset
from mnemosyne.sources.iiif_common import label as _label
from mnemosyne.sources.iiif_common import metadata as _metadata
from mnemosyne.util import parse_year

log = get_logger("sources.iiif")

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_MAX_MANIFESTS = 40
_MAX_NESTED_COLLECTIONS = 5
#: Safety net: never follow more than this many `next` pages per collection.
_MAX_COLLECTION_PAGES = 10


def _image_service(manifest: dict) -> tuple[str | None, str | None, str]:
    """Return (image_service_id, fallback_image_url, full_size) for the first canvas.

    ``full_size`` is the IIIF Image API size parameter for the full-resolution
    image: Image API 3.0 spells it ``max`` (``full`` is v2-only syntax), so a v3
    service would otherwise get a 400 on every image fetch.
    """
    # v2: sequences -> canvases -> images -> resource
    try:
        body = manifest["sequences"][0]["canvases"][0]["images"][0]["resource"]
    except (KeyError, IndexError, TypeError):
        body = None
    # v3: items -> items -> items[0] -> body
    if body is None:
        try:
            body = manifest["items"][0]["items"][0]["items"][0]["body"]
        except (KeyError, IndexError, TypeError):
            body = None
    if not isinstance(body, dict):
        return None, None, "full"
    if body.get("type") == "Choice" and isinstance(body.get("items"), list):
        body = body["items"][0]
    service = body.get("service")
    if isinstance(service, list) and service:
        service = service[0]
    if isinstance(service, dict):
        sid = service.get("id") or service.get("@id")
        if sid:
            return sid, None, _service_size(service)
    image = body.get("id") or body.get("@id")
    return None, image, "full"


def _service_size(service: dict) -> str:
    """The full-resolution size parameter for a service (v3 -> ``max``)."""
    if "ImageService3" in str(service.get("type") or ""):
        return "max"
    if "image/3" in str(service.get("profile") or ""):
        return "max"
    return "full"


def _manifest_urls(collection: dict) -> list[str]:
    urls: list[str] = []
    # v2
    for item in collection.get("manifests", []) or []:
        if isinstance(item, dict):
            url = item.get("@id") or item.get("id")
            if url:
                urls.append(url)
    # v3
    for item in collection.get("items", []) or []:
        if isinstance(item, dict) and item.get("type") != "Collection":
            url = item.get("id") or item.get("@id")
            if url:
                urls.append(url)
    return urls


def _nested_collection_urls(collection: dict) -> list[str]:
    urls: list[str] = []
    for item in collection.get("collections", []) or []:  # v2
        if isinstance(item, dict):
            url = item.get("@id") or item.get("id")
            if url:
                urls.append(url)
    for item in collection.get("items", []) or []:  # v3
        if isinstance(item, dict) and item.get("type") == "Collection":
            url = item.get("id") or item.get("@id")
            if url:
                urls.append(url)
    return urls


def _next_page_url(collection: dict) -> str | None:
    """The pagination link of a collection page (v2/v3 ``next``)."""
    nxt = collection.get("next")
    if isinstance(nxt, str) and nxt:
        return nxt
    if isinstance(nxt, dict):
        url = nxt.get("@id") or nxt.get("id")
        if isinstance(url, str) and url:
            return url
    return None


class IIIFConnector(Connector):
    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        extra = self.descriptor.extra or {}
        collection_url = extra.get("collection")
        manifest_url = extra.get("manifest")
        if collection_url:
            urls = await self._collection_manifests(str(collection_url), limit=_MAX_MANIFESTS)
        elif manifest_url:
            urls = [str(manifest_url)]
        else:
            log.warning("iiif %s: no 'collection' or 'manifest' in extra", self.id)
            return []

        tokens = [t.lower() for t in _TOKEN_RE.findall(query or "") if len(t) > 2]
        assets: list[Asset] = []
        for url in urls:
            asset = await self._manifest_to_asset(url)
            if asset is None:
                continue
            if tokens and not _matches(asset, tokens):
                continue
            assets.append(asset)
            if len(assets) >= limit:
                break
        return assets

    async def _collection_manifests(self, url: str, limit: int) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        fetched: set[str] = set()
        queue = [url]
        depth = 0
        while queue and len(urls) < limit and depth <= _MAX_NESTED_COLLECTIONS:
            next_queue: list[str] = []
            for coll in queue:
                page: str | None = coll
                pages = 0
                # follow the v2/v3 `next` pagination of this collection
                while page and len(urls) < limit and pages < _MAX_COLLECTION_PAGES:
                    if page in fetched:
                        break
                    fetched.add(page)
                    try:
                        data = await self.http.get_json(
                            page, headers={"Accept": "application/json"}
                        )
                    except Exception as exc:  # noqa: BLE001
                        log.debug("iiif collection %s failed: %s", page, exc)
                        break
                    if not isinstance(data, dict):
                        log.debug("iiif collection %s: unexpected payload", page)
                        break
                    for u in _manifest_urls(data):
                        if u not in seen:
                            seen.add(u)
                            urls.append(u)
                    next_queue.extend(_nested_collection_urls(data))
                    page = _next_page_url(data)
                    pages += 1
            queue = next_queue
            depth += 1
        return urls[:limit]

    async def _manifest_to_asset(self, url: str) -> Asset | None:
        try:
            manifest = await self.http.get_json(url, headers={"Accept": "application/json"})
        except Exception as exc:  # noqa: BLE001
            log.debug("iiif manifest %s failed: %s", url, exc)
            return None
        if not isinstance(manifest, dict):
            return None

        service, fallback, full_size = _image_service(manifest)
        image_url = f"{service}/full/{full_size}/0/default.jpg" if service else fallback
        thumbnail = f"{service}/full/512,/0/default.jpg" if service else fallback
        if not image_url:
            return None

        date_text = (
            _metadata(manifest, "date", "date of creation", "created", "période", "datation")
            or _metadata(manifest, "publication date")
            or _metadata(manifest, "date issued")
        )
        identifier = manifest.get("id") or manifest.get("@id") or url
        return Asset.build(
            self.id,
            str(identifier),
            title=_label(manifest.get("label")) or "Sans titre",
            description=_metadata(manifest, "description", "summary") or "",
            creator=_metadata(manifest, "creator", "artist", "author"),
            date_text=date_text,
            year=parse_year(date_text),
            license=manifest.get("rights") or manifest.get("license") or self.descriptor.license,
            rights=self.descriptor.rights,
            page_url=str(identifier),
            image_url=image_url,
            thumbnail_url=thumbnail,
            iiif_id=service,
            extra={"manifest": url, "provider": _label(manifest.get("provider"))},
        )


def _matches(asset: Asset, tokens: list[str]) -> bool:
    haystack = " ".join(
        [asset.title or "", asset.description or "", asset.creator or "", asset.date_text or ""]
    ).lower()
    return any(token in haystack for token in tokens)
