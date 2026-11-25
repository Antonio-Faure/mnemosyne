"""Image URL validation for the resolver.

The resolver must never record a dead link, a thumbnail or a non-image page as
the illustration of a sentence. This module fetches only the first bytes of the
image (bounded), lets Pillow identify it, and returns a small preview the agent
can actually look at.
"""

from __future__ import annotations

import asyncio
import io
import ipaddress
import time
from typing import Any

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from mnemosyne.logger import get_logger

log = get_logger("resolver.image")

IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "TIFF", "BMP", "AVIF", "HEIF"}
_THUMB_HINTS = ("thumb", "thumbnail", "preview", "vignette", "sprite", "logo")
_RETRY_STATUS = {403, 429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
#: After a 403, stop hammering the same host for a while (burst protection).
_HOST_BLOCK_UNTIL: dict[str, float] = {}
_HOST_BLOCK_SECONDS = 600

#: Standard image-fetch UA. It names the project: not a stealth/browser bypass.
_IMAGE_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
    "Mnemosyne/0.1 (+https://github.com/Antonio-Faure/mnemosyne)"
)


def _referer_for(url: str, page_url: str | None = None) -> str | None:
    """A Referer is not a bypass: institutions use it as a normal hotlink check."""
    if page_url:
        return page_url
    try:
        host = (httpx.URL(url).host or "").lower()
    except (httpx.InvalidURL, ValueError):
        return None
    if "gallica.bnf.fr" in host:
        return "https://gallica.bnf.fr/"
    if "wikimedia.org" in host:
        return "https://commons.wikimedia.org/"
    return None


def _fallback_url(url: str) -> str | None:
    """A smaller/official variant of the same image, for hosts that refuse one URL.

    This is not a mirror or a bypass: it stays on the institution's own server
    and asks for a documented IIIF size (Gallica) or the official file path
    (Wikimedia Commons).
    """
    try:
        parsed = httpx.URL(url)
    except (httpx.InvalidURL, ValueError):
        return None
    host = (parsed.host or "").lower()
    if "gallica.bnf.fr" in host and "/full/full/0/native.jpg" in url:
        return url.replace("/full/full/0/native.jpg", "/full/1024,/0/default.jpg")
    if "upload.wikimedia.org" in host and "/wikipedia/commons/" in url:
        clean = url.split("?", 1)[0].split("#", 1)[0]
        marker = "https://upload.wikimedia.org/wikipedia/commons/"
        if clean.startswith(marker) and "/thumb/" not in clean:
            filename = clean[len(marker):].rsplit("/", 1)[-1]
            return (
                "https://commons.wikimedia.org/wiki/Special:FilePath/"
                f"{filename}?width=1280"
            )
    return None


def normalise_image_url(url: str) -> str:
    """Trim spaces and drop the fragment; keep query parameters (IIIF sizes)."""
    return str(url or "").strip().split("#", 1)[0].strip()


def _valid_url(url: str) -> bool:
    try:
        parsed = httpx.URL(url)
    except (httpx.InvalidURL, ValueError):
        return False
    if parsed.scheme not in ("http", "https") or not parsed.host:
        return False
    host = (parsed.host or "").lower()
    if host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
    )


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
    referer: str | None = None,
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

    host = (httpx.URL(normalized).host or "").lower()
    if host and _HOST_BLOCK_UNTIL.get(host, 0.0) > time.monotonic():
        result["hard_failures"].append(
            "hôte temporairement bloqué après un 403 récent"
        )
        return result

    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            timeout=25.0,
            follow_redirects=True,
            headers={
                "User-Agent": _IMAGE_UA,
                "Accept": "image/*, */*;q=0.5",
            },
        )
    data = bytearray()
    candidates = [normalized]
    fallback = _fallback_url(normalized)
    if fallback and fallback != normalized:
        candidates.append(fallback)
    headers = {
        "Range": f"bytes=0-{max(0, max_fetch_bytes - 1)}",
        "Accept": "image/*, */*;q=0.5",
    }
    referer_value = _referer_for(normalized, referer)
    if referer_value:
        headers["Referer"] = referer_value
    success = False
    last_error: str | None = None
    used_fallback = False
    try:
        for candidate in candidates:
            for attempt in range(_MAX_ATTEMPTS):
                data.clear()
                retryable = False
                attempt_limit = _MAX_ATTEMPTS
                try:
                    async with client.stream("GET", candidate, headers=headers) as response:
                        result["final_url"] = str(response.url)
                        content_type = (response.headers.get("content-type") or "").split(";")[0]
                        result["content_type"] = content_type.strip() or None
                        if response.status_code >= 400:
                            last_error = f"HTTP {response.status_code}"
                            retryable = response.status_code in _RETRY_STATUS
                            if response.status_code == 403:
                                # A denial gets one polite retry, not three.
                                attempt_limit = 2
                        else:
                            content_length = response.headers.get("content-length")
                            if content_length and content_length.isdigit():
                                result["image_bytes"] = int(content_length)
                            async for chunk in response.aiter_bytes():
                                data.extend(chunk)
                                if len(data) >= max_fetch_bytes:
                                    break
                            success = True
                            used_fallback = candidate != normalized
                            break
                except (httpx.HTTPError, ValueError) as exc:
                    last_error = str(exc) or type(exc).__name__
                    retryable = True
                if not retryable or attempt + 1 >= attempt_limit:
                    break
                log.debug(
                    "image fetch %s failed (%s), retry %d/%d",
                    candidate,
                    last_error,
                    attempt + 1,
                    _MAX_ATTEMPTS,
                )
                await asyncio.sleep(min(1.5 * (2**attempt), 8.0))
            if success:
                break
    finally:
        if own_client:
            await client.aclose()

    if not success:
        if last_error == "HTTP 403" and host:
            _HOST_BLOCK_UNTIL[host] = time.monotonic() + _HOST_BLOCK_SECONDS
        result["hard_failures"].append(last_error or "échec de téléchargement")
        return result
    if host:
        _HOST_BLOCK_UNTIL.pop(host, None)
    if used_fallback:
        result["warnings"].append(
            f"URL de repli utilisée : {result['final_url']} "
            "(même image, variante servie par l'institution)"
        )

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
