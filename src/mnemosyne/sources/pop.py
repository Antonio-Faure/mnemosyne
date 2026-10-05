"""POP — Plateforme ouverte du patrimoine (ministère de la Culture, France).

POP exposes an open, keyless OpenSearch API over the *Mémoire* (industrial
heritage photographs) and *Joconde* (museum objects) databases, plus per-notice
IIIF Presentation manifests and a IIIF Image API v3 endpoint for the images.

Facts verified live (task #49):

* ``GET  /search/simple``           bracket-notation query -> OpenSearchResult
* ``GET  /search/facets``           term aggregations
* ``POST /search/advanced``         JSON query -> OpenSearchResult
* ``GET  /notices/{db}/{ref}``      raw notice object
* ``GET  /notices/{db}/{ref}/public``      notice + sections
* ``GET  /notices/{db}/{ref}/iiif/manifest``  IIIF Presentation v3 manifest

The *metadata* is reusable under the Licence Ouverte 2.0 (etalab), but the
*images* carry per-notice rights in ``DIFF`` (Mémoire) / ``DIFFU``+``COPY``
(Joconde) and are **predominantly restrictive**. This connector therefore
normalizes every hit into an :class:`Asset` but only surfaces an image URL when
:func:`is_restrictive` is ``False`` for that notice — a restricted image is
never hot-linked. ``is_restrictive`` defaults to ``True`` when there is no
explicit free signal.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

#: API host (open, no auth, any User-Agent, JSON).
API_BASE = "https://api.pop.culture.gouv.fr"
#: IIIF Image API v3 (level 2) endpoint that serves the ``IMG`` paths.
IIIF_IMAGE_BASE = "https://iiif.prd.cloud.culture.fr/iiif/3"
#: S3 bucket that also stores the original ``IMG`` objects.
BUCKET_BASE = "https://popcorn-prd-perf-assets.s3.gra.io.cloud.ovh.net"
#: Public frontend used to build the human-facing notice page URL.
FRONTEND_BASE = "https://pop.culture.gouv.fr"

#: Databases targeted by this connector (photographs / objects).
DEFAULT_DATABASES = ("memoire", "joconde")

#: Free-text terms used when harvesting the industrial-heritage corpus.
INDUSTRIAL_TERMS = (
    "usine",
    "machine",
    "chantier",
    "manufacture",
    "métallurgie",
    "chemin de fer",
    "mine",
)

#: The notice *metadata* is published under the French Open Licence 2.0.
METADATA_LICENSE = "Licence Ouverte 2.0 (etalab)"

#: ``/search/simple`` returns at most 2000 documents per page.
MAX_PAGE_SIZE = 2000
#: Safety net: never walk more than this many pages per (db, term) pair.
MAX_PAGES = 50

#: Substrings that clearly signal a *free* reuse of the image.
_FREE_MARKERS = (
    "domaine public",
    "public domain",
    "licence ouverte",
    "open licence",
    "etalab",
    "cc0",
    "cc-by",
    "cc by",
    "creative commons",
    "libre de droits",
    "sans restriction",
)
#: Substrings that clearly signal a *restrictive* reuse of the image.
_RESTRICTIVE_MARKERS = (
    "tous droits",
    "droits réservés",
    "droits reserves",
    "reproduction interdite",
    "reproduction soumise",
    "soumis à autorisation",
    "soumise à autorisation",
    "autorisation",
    "interdit",
    "copyright",
    "©",
)
#: ``DIFFU`` values meaning "not diffusable" (Joconde).
_NOT_DIFFUSABLE = ("non", "no", "false", "0")


def _enc(path: str) -> str:
    """URL-quote an ``IMG`` path (``safe=""``: the whole path is the id)."""
    return quote(path, safe="")


def iiif_service_id(path: str) -> str:
    """IIIF Image API v3 service id (``.../iiif/3/<enc path>``)."""
    return f"{IIIF_IMAGE_BASE}/{_enc(path)}"


def iiif_info_url(path: str) -> str:
    return f"{iiif_service_id(path)}/info.json"


def iiif_image_url(path: str) -> str:
    """Full-resolution JPEG through the IIIF Image API."""
    return f"{iiif_service_id(path)}/full/max/0/default.jpg"


def iiif_thumb_url(path: str) -> str:
    """200px-wide thumbnail through the IIIF Image API."""
    return f"{iiif_service_id(path)}/full/200,/0/default.jpg"


def bucket_url(path: str) -> str:
    """Direct object URL on the POP assets bucket (slashes kept as path)."""
    return f"{BUCKET_BASE}/{quote(path, safe='/')}"


def notice_image_paths(src: dict[str, Any]) -> list[str]:
    """``IMG`` paths of a notice: a string (Mémoire) or a list (Joconde)."""
    img = src.get("IMG")
    if isinstance(img, str):
        img = img.strip()
        return [img] if img else []
    if isinstance(img, (list, tuple)):
        return [str(item).strip() for item in img if isinstance(item, str) and item.strip()]
    return []


def _rights_text(src: dict[str, Any]) -> str:
    """Concatenate the per-notice rights/credit fields (DIFF / DIFFU / COPY)."""
    parts = []
    for key in ("DIFF", "DIFFU", "COPY", "DROITS", "DROIT"):
        value = src.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return " | ".join(parts)


def is_restrictive(src: dict[str, Any]) -> bool:
    """Whether the notice image must **not** be republished.

    Conservative by design: returns ``True`` unless an explicit free signal is
    present. A ``DIFFU == "non"`` (Joconde) is an immediate restrictive flag;
    a free marker ("Domaine public", "Licence Ouverte"…) always wins.
    """
    diffu = src.get("DIFFU")
    if isinstance(diffu, str) and diffu.strip().lower() in _NOT_DIFFUSABLE:
        return True
    text = _rights_text(src).lower()
    if any(marker in text for marker in _FREE_MARKERS):
        return False
    if any(marker in text for marker in _RESTRICTIVE_MARKERS):
        return True
    return True


def manifest_image_services(manifest: dict[str, Any]) -> list[str]:
    """Extract the ImageService3 ids from a Presentation v3 manifest.

    Path: ``items[].items[].items[].body.service[0].id`` (``service`` may be a
    dict or a list; ``body`` may be a Choice with nested ``items``).
    """
    services: list[str] = []
    for canvas in _as_list(manifest.get("items")):
        for page in _as_list(canvas.get("items")):
            for annotation in _as_list(page.get("items")):
                services.extend(_service_ids(annotation.get("body")))
    return services


def _service_ids(body: Any) -> list[str]:
    if isinstance(body, list):
        out: list[str] = []
        for item in body:
            out.extend(_service_ids(item))
        return out
    if not isinstance(body, dict):
        return []
    service = body.get("service")
    candidates = service if isinstance(service, list) else [service]
    ids: list[str] = []
    for svc in candidates:
        if isinstance(svc, dict):
            sid = svc.get("id") or svc.get("@id")
            if isinstance(sid, str) and sid:
                ids.append(sid)
    return ids


def facet_buckets(data: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    """Normalize ``/search/facets`` aggregations to ``{field: [{key, count}]}``."""
    out: dict[str, list[dict[str, Any]]] = {}
    aggregations = (data or {}).get("aggregations") or {}
    if not isinstance(aggregations, dict):
        return out
    for field, payload in aggregations.items():
        buckets = (payload or {}).get("buckets") if isinstance(payload, dict) else None
        out[field] = [
            {"key": b.get("key"), "count": b.get("doc_count")}
            for b in _as_list(buckets)
            if isinstance(b, dict)
        ]
    return out


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _first_str(src: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = src.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


class PopConnector(Connector):
    """Normalizes POP *Mémoire* / *Joconde* notices into canonical ``Asset``s."""

    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        databases = _as_list(filters.get("bases")) or self._databases()
        if query and query.strip():
            terms = [query.strip()]
        else:
            terms = _as_list(filters.get("terms")) or self._industrial_terms()

        page_size = self._page_size(limit)
        seen: set[tuple[str, str]] = set()
        assets: list[Asset] = []

        for db in databases:
            for term in terms:
                from_ = 0
                for _ in range(MAX_PAGES):
                    data = await self._simple_search(term, db, from_=from_, size=page_size)
                    hits = _as_list(data.get("hits"))
                    if not hits:
                        break
                    for hit in hits:
                        src = hit.get("_source") if isinstance(hit, dict) else None
                        if not isinstance(src, dict):
                            continue
                        ref = str(src.get("REF") or "").strip()
                        if not ref or (db, ref) in seen:
                            continue
                        seen.add((db, ref))
                        assets.append(self._to_asset(db, src))
                        if len(assets) >= limit:
                            return assets[:limit]
                    from_ += len(hits)
                    if from_ >= _to_int(data.get("total")) or len(hits) < page_size:
                        break
        return assets[:limit]

    # ── POP endpoints ─────────────────────────────────────────────────────
    async def _simple_search(self, term: str, db: str, *, from_: int, size: int) -> dict[str, Any]:
        params: dict[str, Any] = {
            "text": term,
            "from": from_,
            "size": size,
            "bases[0]": db,
            "filters[hasImage]": "true",
        }
        data = await self.http.get_json(self._api_url("/search/simple"), params=params)
        return data if isinstance(data, dict) else {}

    async def facets(self, term: str, db: str | None = None) -> dict[str, list[dict[str, Any]]]:
        params: dict[str, Any] = {"text": term}
        if db:
            params["bases[0]"] = db
        data = await self.http.get_json(self._api_url("/search/facets"), params=params)
        return facet_buckets(data if isinstance(data, dict) else {})

    async def get_notice(self, db: str, ref: str) -> dict[str, Any]:
        data = await self.http.get_json(self._api_url(f"/notices/{db}/{ref}"))
        return data if isinstance(data, dict) else {}

    async def fetch_manifest(self, db: str, ref: str) -> dict[str, Any]:
        data = await self.http.get_json(self._api_url(f"/notices/{db}/{ref}/iiif/manifest"))
        return data if isinstance(data, dict) else {}

    async def image_services(self, db: str, ref: str) -> list[str]:
        return manifest_image_services(await self.fetch_manifest(db, ref))

    # ── normalization ─────────────────────────────────────────────────────
    def _to_asset(self, db: str, src: dict[str, Any]) -> Asset:
        ref = str(src.get("REF") or "").strip()
        paths = notice_image_paths(src)
        restrictive = is_restrictive(src)
        rights_text = _rights_text(src)
        title = _first_str(src, "TITRE", "LEG", "TITRE_M") or f"{db} {ref}"
        date_text = _first_str(src, "DATE", "DATE_D", "DATPV", "DATE_M")

        image_url = thumbnail_url = iiif_id = bucket = None
        if paths and not restrictive:
            path = paths[0]
            image_url = iiif_image_url(path)
            thumbnail_url = iiif_thumb_url(path)
            iiif_id = iiif_service_id(path)
            bucket = bucket_url(path)

        return Asset.build(
            self.id,
            f"{db}/{ref}",
            title=title,
            description=_first_str(src, "LEG", "DESC", "DESCRIPTION") or "",
            creator=_first_str(src, "AUTR", "AUTP", "AUTEUR"),
            date_text=date_text,
            year=parse_year(date_text),
            license=METADATA_LICENSE,
            rights=rights_text or None,
            page_url=f"{FRONTEND_BASE}/notice/{db}/{ref}",
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            iiif_id=iiif_id,
            extra={
                "db": db,
                "ref": ref,
                "restrictive": restrictive,
                "rights_text": rights_text,
                "credit": src.get("COPY"),
                "image_paths": paths,
                "iiif_info": iiif_info_url(paths[0]) if (paths and not restrictive) else None,
                "bucket_url": bucket,
                "metadata_license": METADATA_LICENSE,
            },
        )

    # ── config helpers ────────────────────────────────────────────────────
    def _api_url(self, path: str) -> str:
        return self.descriptor.base_url.rstrip("/") + path

    def _databases(self) -> list[str]:
        configured = _as_list(self.descriptor.extra.get("databases"))
        return [str(db) for db in configured] or list(DEFAULT_DATABASES)

    def _industrial_terms(self) -> list[str]:
        configured = _as_list(self.descriptor.extra.get("industrial_terms"))
        return [str(term) for term in configured] or list(INDUSTRIAL_TERMS)

    def _page_size(self, limit: int) -> int:
        configured = _to_int(self.descriptor.extra.get("page_size")) or 100
        return max(1, min(configured, MAX_PAGE_SIZE, max(limit, 1)))
