"""Image URL validation for the resolver.

The resolver must never record a dead link, a thumbnail or a non-image page as
the illustration of a sentence. This module fetches only the first bytes of the
image (bounded), lets Pillow identify it, and returns a small preview the agent
can actually look at.
"""

from __future__ import annotations

import io
from typing import Any

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from mnemosyne.http import default_contact
from mnemosyne.logger import get_logger

log = get_logger("resolver.image")

IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "TIFF", "BMP", "AVIF", "HEIF"}
_THUMB_HINTS = ("thumb", "thumbnail", "preview", "vignette", "sprite", "logo")


def normalise_image_url(url: str) -> str:
    """Trim spaces and drop the fragment; keep query parameters (IIIF sizes)."""
    return str(url or "").strip().split("#", 1)[0].strip()


def _valid_url(url: str) -> bool:
    try:
        parsed = httpx.URL(url)
    except (httpx.InvalidURL, ValueError):
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.host)


def _preview(data: bytes, max_dim: int) -> bytes | None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((max_dim, max_dim))
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            out = io.BytesIO()
            image.save(out, format="PNG", optimize=True)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None


async def inspect_image(
    url: str,
    *,
    preview_max: int = 1280,
    min_side: int = 240,
    min_bytes: int = 8000,
    warn_side: int = 500,
    warn_bytes: int = 20000,
    max_fetch_bytes: int = 8_000_000,
    preview: bool = True,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Fetch and inspect an image URL; return metadata, quality flags and preview.

    Only the first ``max_fetch_bytes`` are downloaded. ``ok`` is False on a hard
    failure; warnings do not block the record but are stored with it.
    """
    normalized = normalise_image_url(url)
    result: dict[str, Any] = {
        "ok": False,
        "image_url": normalized,
        "final_url": normalized,
        "content_type": None,
        "image_format": None,
        "width": None,
        "height": None,
        "image_bytes": None,
        "hard_failures": [],
        "warnings": [],
        "preview": None,
    }
    if not _valid_url(normalized):
        result["hard_failures"].append("URL invalide : http(s) attendu")
        return result

    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            timeout=25.0,
            follow_redirects=True,
            headers={
                "User-Agent": default_contact(),
                "Accept": "image/*, */*;q=0.5",
            },
        )
    data = bytearray()
    try:
        headers = {"Range": f"bytes=0-{max(0, max_fetch_bytes - 1)}"}
        async with client.stream("GET", normalized, headers=headers) as response:
            result["final_url"] = str(response.url)
            content_type = (response.headers.get("content-type") or "").split(";")[0]
            result["content_type"] = content_type.strip() or None
            content_length = response.headers.get("content-length")
            if content_length and content_length.isdigit():
                result["image_bytes"] = int(content_length)
            if response.status_code >= 400:
                result["hard_failures"].append(f"HTTP {response.status_code}")
                return result
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) >= max_fetch_bytes:
                    break
    except (httpx.HTTPError, ValueError) as exc:
        result["hard_failures"].append(str(exc) or type(exc).__name__)
        return result
    finally:
        if own_client:
            await client.aclose()

    raw = bytes(data)
    if result["image_bytes"] is None:
        result["image_bytes"] = len(raw)
    if not raw:
        result["hard_failures"].append("réponse vide")
        return result

    image_format = None
    width = height = None
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image_format = image.format
            width, height = image.size
            # Dimensions are often readable even when the download was capped.
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        image_format = None
    result["image_format"] = image_format
    result["width"] = width
    result["height"] = height

    if image_format not in IMAGE_FORMATS:
        content_type = result["content_type"] or ""
        if not content_type.startswith("image/"):
            result["hard_failures"].append("le lien ne renvoie pas une image")
        else:
            result["warnings"].append(
                "content-type image mais format non reconnu par Pillow"
            )
    elif not (result["content_type"] or "").startswith("image/"):
        result["warnings"].append("content-type générique, image reconnue par Pillow")

    if width and height and min(width, height) < min_side:
        result["hard_failures"].append(
            f"image trop petite : {width}×{height} (minimum {min_side} px)"
        )
    elif width and height and min(width, height) < warn_side:
        result["warnings"].append(
            f"image petite : {width}×{height} (confort ≥ {warn_side} px)"
        )
    if result["image_bytes"] and result["image_bytes"] < min_bytes:
        result["hard_failures"].append(
            f"fichier trop petit : {result['image_bytes']} octets "
            f"(minimum {min_bytes})"
        )
    elif result["image_bytes"] and result["image_bytes"] < warn_bytes:
        result["warnings"].append(
            f"fichier léger : {result['image_bytes']} octets "
            f"(confort ≥ {warn_bytes})"
        )
    lowered = normalized.casefold()
    if any(hint in lowered for hint in _THUMB_HINTS):
        result["warnings"].append("URL de vignette ou de logo probable ; vérifier la taille")

    result["preview"] = _preview(raw, preview_max) if preview else None
    if preview and result["preview"] is None:
        result["warnings"].append(
            "aperçu impossible (image tronquée ou format non décodable) ; "
            "dimensions/issues vérifiées sur les en-têtes"
        )
    result["ok"] = not result["hard_failures"]
    return result
