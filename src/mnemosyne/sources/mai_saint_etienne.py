"""Musée d'Art et d'Industrie de Saint-Étienne — Micromusée « opacweb » portal.

The museum's WordPress showcase (``mai.saint-etienne.fr``) links to its online
collection database, a Micromusée « opacweb » portal at
``collections.musee-art-industrie.saint-etienne.fr``. It is an API Platform
(Hydra) JSON API v2 — no OAI-PMH. Plain server-side GETs return
``application/ld+json`` (no bot block, no CORS).

Where the images live
---------------------
The portal never exposes a plain image URL. Each media file is served through a
CloudFront endpoint whose path is the **base64 of a JSON descriptor**
(``{bucket, key, edits}``). We rebuild that URL ourselves, so any requested
width is available (server-side resize of the original) and *every* media file
of a notice is exposed (one URL per ``mediaFiles[]`` entry).

Licence
-------
Every notice carries a site-wide watermark/footer reserving commercial reuse
(« utilisation commerciale des images soumise à autorisation »). There is no
per-record licence field, so the descriptor ships with ``enabled: false``: the
connector is wired and tested but nothing is ingested.

Provider shapes (the Hydra search envelope, the ``zones``/``occurZones``/``fields``
metadata tree and the ``mediaFiles`` list) are normalized into the canonical
:class:`Asset` at this boundary and never leak past it.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

DEFAULT_IMAGE_WIDTH = 1200

#: metadata field codes inside ``zones[].occurZones[].fields[]``
_AUTHOR_CODES = ("PersonneChamp", "Nom", "Auteur")


def cloudfront_url(
    host: str,
    bucket: str,
    key: str,
    width: int = DEFAULT_IMAGE_WIDTH,
) -> str:
    """Build a CloudFront media URL for a Micromusée media file.

    The path is ``base64(JSON)`` where ``JSON`` is::

        {"bucket": ..., "key": ...,
         "edits": {"resize": {"width": W, "height": W, "fit": "inside"}}}

    The portal escapes ``/`` as ``\\/`` inside the base64 payload; our
    ``json.dumps`` does not, so the bytes differ but both decode to the same
    object and load identically.
    """
    payload = {
        "bucket": bucket,
        "key": key,
        "edits": {
            "resize": {
                "width": int(width),
                "height": int(width),
                "fit": "inside",
            }
        },
    }
    raw = json.dumps(payload).encode("utf-8")
    token = base64.b64encode(raw).decode("ascii")
    return f"{host.rstrip('/')}/{token}"


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _field_values(notice: dict[str, Any], code: str) -> list[str]:
    """Collect the ``content`` of every field matching ``code`` in the notice."""
    out: list[str] = []
    for zone in notice.get("zones") or []:
        if not isinstance(zone, dict):
            continue
        for occurrence in zone.get("occurZones") or []:
            if not isinstance(occurrence, dict):
                continue
            for field in occurrence.get("fields") or []:
                if not isinstance(field, dict) or field.get("code") != code:
                    continue
                content = _clean(field.get("content"))
                if content:
                    out.append(content)
    return out


def _first_field(notice: dict[str, Any], *codes: str) -> str | None:
    for code in codes:
        values = _field_values(notice, code)
        if values:
            return values[0]
    return None


class MAISaintEtienneConnector(Connector):
    """Normalizes the MAI « opacweb » Hydra API into canonical ``Asset``s."""

    async def search(self, query: str = "", limit: int = 20, **filters: Any) -> list[Asset]:
        extra = self.descriptor.extra or {}
        api_base = str(extra.get("api_base") or self.descriptor.base_url).rstrip("/")
        search_path = str(extra.get("search_path") or "/notices/search")
        url = f"{api_base}{search_path}"

        pagination = extra.get("pagination") or {}
        page_param = str(pagination.get("page_param") or "page")
        size_param = str(pagination.get("size_param") or "items_per_page")
        page_size = int(pagination.get("page_size") or 100)
        default_params = dict(extra.get("default_params") or {})

        assets: list[Asset] = []
        seen = 0
        page = 1
        max_pages = int(filters.get("max_pages") or 1000)
        while page <= max_pages:
            params = dict(default_params)
            params[size_param] = str(page_size)
            params[page_param] = str(page)
            params["query"] = query

            data = await self.http.get_json(url, params=params)
            members = data.get("hydra:member") if isinstance(data, dict) else None
            if not members:
                break
            seen += len(members)
            for notice in members:
                if not isinstance(notice, dict):
                    continue
                asset = self._notice_to_asset(notice)
                if asset is not None:
                    assets.append(asset)
            if len(assets) >= limit:
                break
            total = data.get("hydra:totalItems")
            if isinstance(total, int) and seen >= total:
                break
            page += 1
        return assets[:limit]

    def _notice_to_asset(self, notice: dict[str, Any]) -> Asset | None:
        notice_id = notice.get("id")
        if not notice_id:
            return None
        source_asset_id = str(notice_id)

        titles = notice.get("titles") or {}
        title = _clean(titles.get("title")) or ""
        subtitle = _clean(titles.get("subTitle"))
        description = (
            _first_field(notice, "DescriptionAnalytique")
            or _clean(titles.get("text"))
            or ""
        )

        collections = [str(c) for c in (notice.get("noticeCollections") or []) if c]
        images = self._notice_images(notice)
        image_url = images[0] if images else None
        keywords = _field_values(notice, "SujetTheme")
        date_text = _first_field(notice, "EpoqueDatation")

        return Asset.build(
            self.id,
            source_asset_id,
            title=title,
            description=description,
            creator=_first_field(notice, *_AUTHOR_CODES),
            date_text=date_text,
            year=parse_year(date_text),
            license=self.descriptor.license,
            rights=self.descriptor.rights,
            page_url=_clean(notice.get("url")),
            image_url=image_url,
            thumbnail_url=image_url,
            tags=list(dict.fromkeys([*collections, *keywords])),
            extra={
                "native_id": notice.get("nativeId"),
                "slug": notice.get("slug"),
                "subtitle": subtitle,
                "collections": collections,
                "domain": _first_field(notice, "Domaine"),
                "material": _first_field(notice, "Matiere"),
                "technique": _first_field(notice, "Technique"),
                "owner": _first_field(notice, "Proprietaire"),
                "inventory_number": _first_field(notice, "NumeroInventaire"),
                "has_image": bool(notice.get("hasImage")),
                "keywords": keywords,
                "images": images,
            },
        )

    def _notice_images(self, notice: dict[str, Any]) -> list[str]:
        """One CloudFront URL per ``mediaFiles[]`` image entry."""
        extra = self.descriptor.extra or {}
        image_cfg = extra.get("image") or {}
        host = _clean(image_cfg.get("host"))
        bucket = _clean(image_cfg.get("bucket"))
        width = int(image_cfg.get("width") or DEFAULT_IMAGE_WIDTH)
        client = _clean(notice.get("client")) or _clean(extra.get("client"))
        profile = _clean(notice.get("profile")) or _clean(extra.get("profile"))
        if not (host and bucket and client and profile):
            return []

        urls: list[str] = []
        for media in notice.get("mediaFiles") or []:
            if not isinstance(media, dict):
                continue
            if media.get("type") not in (None, "image"):
                continue
            file_name = _clean(media.get("fileName"))
            if not file_name:
                continue
            key = f"{client}/{profile}/{file_name}"
            urls.append(cloudfront_url(host, bucket, key, width))
        return urls
