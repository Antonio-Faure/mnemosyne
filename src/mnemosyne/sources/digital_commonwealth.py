"""Digital Commonwealth (Massachusetts) search — Blacklight JSON API.

The Massachusetts aggregator of GLAM collections exposes a keyless Blacklight
JSON search endpoint (``/search.json``). Records carry rights metadata per
notice and IIIF images; provider shapes (multi-valued Solr field suffixes such
as ``*_tsim``, ``*_ssi``, ``*_ss``) are normalized into the canonical
:class:`Asset` here so the raw provider shape never leaks past this boundary.

Only notices that are explicitly open are kept (``reuse_allowed_ssi`` == "no
restrictions", or a ``rights_ss`` / ``license_ss`` that starts with a "no known
restrictions" statement, or an explicit CC0 license). Everything else —
"contact host", "Rights status not evaluated", … — is dropped. Images are
referenced through the IIIF Image API at ``iiif.digitalcommonwealth.org``; no
image is ever downloaded here.
"""

from __future__ import annotations

from typing import Any

from mnemosyne.connectors.base import Connector
from mnemosyne.models import Asset
from mnemosyne.util import parse_year

#: IIIF Image API endpoint for Digital Commonwealth (verified 200 image/jpeg).
IIIF_IMAGE_BASE = "https://iiif.digitalcommonwealth.org/iiif/2"

#: Maximum page size accepted by the Blacklight endpoint.
MAX_PER_PAGE = 100


def _scalar(value: Any) -> str | None:
    """Return the first non-empty text from a scalar or (nested) list."""
    if isinstance(value, (list, tuple)):
        for item in value:
            text = _scalar(item)
            if text:
                return text
        return None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _list(value: Any) -> list[str]:
    """Normalize a possibly multi-valued field into a list of non-empty texts."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            text = _scalar(item)
            if text:
                out.append(text)
        return out
    text = _scalar(value)
    return [text] if text else []


def _is_open(attrs: dict[str, Any]) -> bool:
    """Decide, per notice, whether the record is explicitly free to reuse."""
    reuse = _scalar(attrs.get("reuse_allowed_ssi"))
    if reuse and reuse.lower() == "no restrictions":
        return True

    rights = (_scalar(attrs.get("rights_ss")) or "").lower()
    if rights.startswith("no known copyright restrictions"):
        return True

    license_ = (_scalar(attrs.get("license_ss")) or "").lower()
    if license_.startswith("no known restrictions"):
        return True
    # Explicit CC0 only — never guess a license from an ambiguous statement.
    if "cc0" in license_ or "publicdomain/zero" in license_:
        return True

    return False


def _image_id(attrs: dict[str, Any]) -> str | None:
    """Extract the IIIF image id from ``exemplary_image_key_base_ss``.

    The value looks like ``images/commonwealth:qj72pd28f``. Strip the
    ``images/`` prefix to get the IIIF identifier. Keys that do not start with
    ``images/`` (e.g. ``metadata/...``) have no usable image and are refused.
    """
    key = _scalar(attrs.get("exemplary_image_key_base_ss"))
    if not key or not key.startswith("images/"):
        return None
    image_id = key[len("images/") :].strip().strip("/")
    if not image_id or "/" in image_id:
        return None
    return image_id


class DigitalCommonwealthConnector(Connector):
    async def search(self, query: str, limit: int = 20, **filters: Any) -> list[Asset]:
        per_page = min(max(limit * 2, 10), MAX_PER_PAGE)
        max_pages = int(filters.get("max_pages", 3))
        endpoint = f"{self.descriptor.base_url.rstrip('/')}/search.json"

        assets: list[Asset] = []
        page = 1
        while page <= max_pages and len(assets) < limit:
            params = {"q": query, "per_page": str(per_page), "page": str(page)}
            data = await self.http.get_json(endpoint, params=params)

            docs = data.get("data") or []
            if not docs:
                break

            for doc in docs:
                asset = self._doc_to_asset(doc)
                if asset is not None:
                    assets.append(asset)
                    if len(assets) >= limit:
                        break

            meta_pages = (data.get("meta") or {}).get("pages") or {}
            total_pages = meta_pages.get("total_pages")
            if total_pages is not None and page >= int(total_pages):
                break
            page += 1

        return assets[:limit]

    def _doc_to_asset(self, doc: Any) -> Asset | None:
        if not isinstance(doc, dict):
            return None
        attrs = doc.get("attributes")
        if not isinstance(attrs, dict):
            return None

        # Rights gate first: drop anything that is not explicitly open.
        if not _is_open(attrs):
            return None

        image_id = _image_id(attrs)
        if not image_id:
            return None

        doc_id = _scalar(doc.get("id"))
        if not doc_id:
            return None

        institution = _scalar(attrs.get("institution_name_ssi"))
        subjects = _list(attrs.get("subject_name_tsim"))
        creator = ", ".join(subjects[:3]) if subjects else institution

        notes = _list(attrs.get("note_tsim"))
        description = " ; ".join(notes)[:600]

        date_tsim = _list(attrs.get("date_tsim"))
        date_text = " ; ".join(date_tsim) if date_tsim else _scalar(attrs.get("date_edtf_ssm"))
        year = parse_year(_scalar(attrs.get("date_start_dtsi"))) or parse_year(date_text)

        rights = _scalar(attrs.get("rights_ss")) or _scalar(attrs.get("license_ss"))
        identifier_uri = _scalar(attrs.get("identifier_uri_ss"))
        page_url = identifier_uri or f"https://www.digitalcommonwealth.org/search/{doc_id}"

        return Asset.build(
            self.id,
            doc_id,
            title=_scalar(attrs.get("title_info_primary_tsi")) or f"Digital Commonwealth {doc_id}",
            description=description,
            creator=creator,
            date_text=date_text,
            year=year,
            license="PDM-1.0",
            rights=rights,
            page_url=page_url,
            image_url=f"{IIIF_IMAGE_BASE}/{image_id}/full/!1200,1200/0/default.jpg",
            thumbnail_url=f"{IIIF_IMAGE_BASE}/{image_id}/full/!400,400/0/default.jpg",
            iiif_id=image_id,
            extra={
                "ark_id": identifier_uri,
                "institution": institution,
                "collection": _list(attrs.get("collection_name_ssim")),
                "reuse_allowed": _scalar(attrs.get("reuse_allowed_ssi")),
                "iiif_image_id": image_id,
            },
        )
