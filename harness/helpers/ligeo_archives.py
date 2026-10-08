"""Ligeo-Archives / Boscop reference (ANMT Roubaix) — mnemosyne browser research.

Source: Archives nationales du monde du travail (ANMT, Roubaix)
        https://archives-nationales-travail.culture.gouv.fr
Online search UI: https://recherche-anmt.culture.gouv.fr
Platform: Ligeo-Archives (Boscop). Viewer: Monocle (IIIF). ARK NAAN = 60879.
Content: ~630k digitised business-archive documents (mines, textile, metal,
rail, factory photographs).

This module is the reusable, read-only *reference* the coder uses to build the
`config/sources/anmt.yaml` descriptor and its connector. It performs NO writes
and NEVER scrapes HTML for images: image data comes only from the open IIIF
endpoints. (The search HTML is parsed only to *discover* ARKs.)

=====================================================================
ACCESS PATH  (verified 2026-10)
=====================================================================
1) SEARCH (HTML) — the *discovery* surface. It is an HTML page rendered by the
   Ligeo/Boscop app; there is NO JSON/RSS/OpenSearch search API.
       SEARCH   https://recherche-anmt.culture.gouv.fr/archive/recherche/simple/n:19
                ?RECH_S=<query>&RECH_TYP=and&RECH_images=1
       RESULTS  /archive/resultats/simple/lineaire/<FONDS>/n:19?RECH_S=...&type=simple
   Results are grouped BY FONDS (one tab per fonds, each with a count
   "N résultat(s)"). The cards carry `/ark:/60879/<ark>` links (the fonds
   notices). Pagination inside the app is JS-driven (`&pagination=N`, fed from a
   hidden `#ArchivesPagination` input), so simple URL paging is unreliable.
   NOTE: this HTML is served by an "Anubis" proof-of-work anti-bot that
   *intermittently* challenges plain HTTP (any UA, even Chrome/Googlebot). When
   challenged you get an Anubis page, not results -> detect with `is_anubis()`
   and fall back to the browser. (In 2026-10 the bot UA passed without a
   challenge, but treat it as fragile.)

2) NOTICE + VIEWER (per record, keyed by ARK) — *NOT* behind Anubis.
       NOTICE   https://recherche-anmt.culture.gouv.fr/ark:/60879/<ark>
       VIEWER   https://recherche-anmt.culture.gouv.fr/ark:/60879/<ark>/daogrp/0
   The viewer link in results looks like
       /ark:/60879/<ark>/daogrp/0/layout:linear/idsearch:RECH_internet_<hash>

3) IIIF Presentation manifest (v2) — OPEN, no Anubis, works with a bot UA.
       MANIFEST https://recherche-anmt.culture.gouv.fr/ark:/60879/<ark>/manifest
   The manifest is the connector's reliable programmatic entry point. Each
   fonds/notice manifest lists ALL its digitised canvases (1..250+ images).

4) IIIF Image API (v3) — OPEN, no Anubis.
   Service base comes from each canvas:
       sequences[0].canvases[i].images[0].resource.service.@id
       e.g. https://recherche-anmt.culture.gouv.fr/iiif/2015_51_Num//FRANMT_2015_51_2.jpg
       <svc>/info.json                    -> IIIF v3 info (NOTE: served with a
                                             *wrong* Content-Type text/html, but
                                             the body IS valid JSON -> json.loads)
       <svc>/full/full/0/default.jpg      -> full JPEG  (200 image/jpeg)
       <svc>/full/max/0/default.jpg       -> full JPEG  (200 image/jpeg)
       <svc>/full/!200,200/0/default.jpg  -> bounded JPEG
       <svc>/square/200,/0/default.jpg    -> square thumbnail
   The size/format separator is a DOT: `.../0/default.jpg`. The slash form
   `.../0/default/jpg` returns 404 — do not use it.
   info.json also advertises an alternate id `/iiif/pool2/anmt/<path>/FOND.TIF`
   (both ids serve images). The manifest's service @id is authoritative.

5) IIIF Content Search (v1, per-document) — <ark>/iiif/search?q=... -> AnnotationList.

6) OAI-PMH  /archive/oai  EXISTS BUT IS DISABLED for every verb
   ("Configuration OAI introuvable") -> dead end.
7) Download  /archive/download?file=...  and  /archive/fullSizeImage?file=...
   return empty / are unreliable -> do NOT use.

DISCOVERY CONCLUSION: no JSON/RSS/OpenSearch, no IIIF collection, OAI off.
The only open programmatic *image* path is: IIIF manifest per ARK + IIIF Image
API. Enumerate ARKs from the search HTML (or a curated seed list) and expand
each with its manifest.

=====================================================================
MANIFEST STRUCTURE (IIIF v2)
=====================================================================
Top keys: @context, @id, @type, label, attribution, logo, metadata,
          ligeoReUseProfil, ligeoIsIndexable, service, sequences
Canvas fields: @id, @type, label, width, height, rendering, ligeoIsprintable,
          ligeoPermalink, thumbnail, images, ligeoRestrictedAccess,
          ligeoIsSearchable, ligeoClasseur, ligeoMediaPath
   NOTE: canvas["thumbnail"] here is a *plain string* (an IIPServer URL), not a
   dict — handle both shapes. `rendering` may also be a dict or list.
metadata = list of {"label": ..., "value": ...} with labels:
   Cote, Contexte, Présentation du contenu, Date, Présentation du producteur,
   Description matérielle, Importance matérielle, Modalités d'acquisition,
   Modalités d'accès, Organisme, Type de document, Identifiant ARK

LICENSE / REUSE (verified uniform across 29 manifests from many fonds;
identical md5 of ligeoReUseProfil.content):
   "Les reproductions numériques ... sont librement communicables au sens de
    l'article L.213-1 du code du patrimoine ... la réutilisation des
    reproductions numériques des documents d'archives privées ... est gratuite.
    L'utilisateur dispose d'un droit non exclusif et gratuit de libre
    réutilisation à des fins commerciales ou non, dans le monde entier et pour
    une durée illimitée. Chaque rediffusion ou réutilisation doit être
    accompagnée des informations suivantes : indication précise de l'origine et
    du lieu de conservation du document « Archives nationales du monde du
    travail (Roubaix) », sa cote et l'intitulé exact du fonds dont il est
    extrait ..."
   -> FREE reuse, COMMERCIAL AND NON-COMMERCIAL, worldwide, unlimited duration.
      Requires attribution (origin + cote + fonds title).
   -> NOT restrictive / NOT NC  =>  descriptor `enabled: true`.
   Source of the decision: French decision of 21 Aug 2017 + art. L.213-1.
   `attribution` = "Archives nationales du monde du travail".
   ligeoReUseProfil.download = 2, ligeoReUseProfil.manifestDownloadable = True.
   ligeoReUseProfil.content is *HTML* (<p>...</p> + a logo <img>); `parse_manifest`
   strips it to clean text in `license` and keeps the raw HTML in `license_html`.

PER-NOTICE RESTRICTION: some notices/canvases carry
   `ligeoRestrictedAccess: true` (UI label "Document numérisé non affichable").
   The connector MUST skip these canvases (and, if every canvas is restricted,
   skip the record). Use `is_restricted()` / `records_from_manifest()`.

=====================================================================
NORMALIZATION NOTES FOR THE CONNECTOR
=====================================================================
- source id:      ark, e.g. "110324.1083809"
- record url:     notice_url(ark)
- asset url:      canvas["@id"] (fallback: canvas ligeoPermalink / rendering)
- image service:  canvas.images[0].resource.service["@id"]  -> image_url(...)
- title:          manifest["label"] (+ canvas label if multi-canvas)
- thumbnail:      image_url(svc, size="!200,200") (IIIF) or canvas thumbnail str
- license:        manifest["ligeoReUseProfil"]["content"] (reuse text) ; also
                  manifest["attribution"]
- date / cote:    from metadata (labels "Date", "Cote")
- restricted:     any canvas ligeoRestrictedAccess == True
- graceful:       manifest fetch uses a descriptive bot UA + paced retries;
                  if no 200 -> return None (no crash, no retry storm).

=====================================================================
GENERIC CONNECTOR SHAPE (Ligeo-Archives / Boscop)
=====================================================================
This platform powers many French archives; keep the connector generic and put
the ANMT specifics in `config/sources/anmt.yaml`:
  base_url, ark_naan ("60879"), search_path, manifest pattern, attribution,
  license text, robots crawl_delay (5).
Connector flow:
  1. discover ARKs  : search_html(query) -> extract_arks(html)  (skip is_anubis)
                      [or use a curated `seeds` list of ARKs]
  2. per ARK        : fetch_manifest(ark) -> records_from_manifest(manifest)
  3. emit records   : one per displayable canvas (restricted ones skipped),
                      image_url = <svc>/full/max/0/default.jpg
  4. politeness     : 1 req / >= crawl_delay (robots: Crawl-delay: 5); bot UA.
"""

from __future__ import annotations

import html as _html
import json
import re
import time
from typing import Any

try:  # requests is the house default; absent only in exotic sandboxes.
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore

UA = (
    "mnemosyne-research-bot/1.0 "
    "(https://github.com/Antonio-Faure/mnemosyne; opensource research aggregator)"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, application/ld+json, */*;q=0.8",
}
HTML_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

BASE = "https://recherche-anmt.culture.gouv.fr"
ARK_NAAN = "60879"
MANIFEST_URL = BASE + "/ark:/{naan}/{ark}/manifest"
NOTICE_URL = BASE + "/ark:/{naan}/{ark}"
VIEWER_URL = BASE + "/ark:/{naan}/{ark}/daogrp/0"
SEARCH_PATH = "/archive/recherche/simple/n:19"
SEARCH_URL = BASE + SEARCH_PATH
RESULTS_URL = BASE + "/archive/resultats/simple/lineaire/{fonds}/n:19"
OAI_URL = BASE + "/archive/oai"
ROBOTS_CRAWL_DELAY = 5

# Verdict: free reuse (commercial + non-commercial) -> descriptor enabled: true.
LICENSE_VERDICT = "free_reuse_commercial_ok"
LICENSE_ATTRIBUTION = "Archives nationales du monde du travail"
LICENSE_NOTICE_FRAGMENT = (
    "droit non exclusif et gratuit de libre réutilisation à des fins "
    "commerciales ou non, dans le monde entier et pour une durée illimitée"
)

# metadata labels -> normalized keys
_META_MAP = {
    "cote": "cote",
    "date": "date",
    "contexte": "contexte",
    "présentation du contenu": "content",
    "type de document": "doc_type",
    "organisme": "organisme",
    "identifiant ark": "ark",
}

_ARK_RE = re.compile(r"/ark:/" + re.escape(ARK_NAAN) + r"/([^/\"'?#\s]+)")
_TAG_RE = re.compile(r"<[^>]+>")
_ANUBIS_RE = re.compile(r"anubis|proof[-\s]?of[-\s]?work|making sure you", re.I)


# --------------------------------------------------------------- URL builders

def manifest_url(ark: str, naan: str = ARK_NAAN) -> str:
    """IIIF Presentation manifest URL for an ARK suffix (e.g. '110324.1083809')."""
    ark = str(ark).strip().lstrip("/")
    return MANIFEST_URL.format(naan=naan, ark=ark)


def notice_url(ark: str, naan: str = ARK_NAAN) -> str:
    ark = str(ark).strip().lstrip("/")
    return NOTICE_URL.format(naan=naan, ark=ark)


def viewer_url(ark: str, naan: str = ARK_NAAN) -> str:
    ark = str(ark).strip().lstrip("/")
    return VIEWER_URL.format(naan=naan, ark=ark)


def search_url(query: str, images_only: bool = True, page: int | None = None,
               base: str = BASE) -> str:
    """Build a Ligeo search URL. `images_only` -> RECH_images=1 (digitised only)."""
    from urllib.parse import quote_plus

    url = base + SEARCH_PATH + "?RECH_S=" + quote_plus(str(query)) + "&RECH_TYP=and"
    if images_only:
        url += "&RECH_images=1"
    if page is not None:
        url += f"&page:{int(page)}"
    return url


def _svc_base(service_id: str) -> str:
    svc = str(service_id).strip()
    if svc.startswith("http"):
        return svc.rstrip("/")
    return BASE + "/iiif/" + svc.lstrip("/")


def image_info_url(service_id: str) -> str:
    """info.json URL for a IIIF image service base (@id or relpath)."""
    return _svc_base(service_id) + "/info.json"


def image_url(
    service_id: str,
    region: str = "full",
    size: str = "full",
    rot: Any = 0,
    quality: str = "default",
    fmt: str = "jpg",
) -> str:
    """Build a IIIF Image API request URL (v3 syntax: region/size/rot/quality.fmt).

    e.g. image_url(svc)                       -> .../full/full/0/default.jpg
         image_url(svc, size="max")           -> .../full/max/0/default.jpg
         image_url(svc, size="!200,200")      -> .../full/!200,200/0/default.jpg
         image_url(svc, region="square", size="200,") -> .../square/200,/0/default.jpg
    """
    return f"{_svc_base(service_id)}/{region}/{size}/{rot}/{quality}.{fmt}"


def thumb_url(service_id: str, size: str = "!200,200") -> str:
    """IIIF thumbnail URL for a service base."""
    return image_url(service_id, size=size)


# ------------------------------------------------------------------- fetching

def _requests_json(url: str, session=None, timeout: int = 30):
    if requests is None:
        return None
    try:
        sess = session or requests
        r = sess.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code != 200:
            return None
        # info.json is served as text/html by mistake; parse the body anyway.
        try:
            return r.json()
        except Exception:  # noqa: BLE001
            return json.loads(r.text)
    except Exception:  # noqa: BLE001
        return None


def fetch_manifest(ark_or_url: str, timeout: int = 30, retries: int = 3,
                   session=None) -> dict | None:
    """GET + JSON-parse an ANMT manifest. Accepts an ARK suffix or a full URL.

    Uses a descriptive bot UA with paced retries. Returns the parsed dict, or
    None on hard failure (never raises, never scrapes).
    """
    url = ark_or_url if str(ark_or_url).startswith("http") else manifest_url(ark_or_url)
    for attempt in range(max(1, retries)):
        data = _requests_json(url, session=session, timeout=timeout)
        if data is not None:
            return data
        time.sleep(1.0 * (attempt + 1))
    return None


def fetch_info(service_id: str, timeout: int = 30, session=None) -> dict | None:
    """GET + parse a IIIF Image API info.json (works despite text/html CT)."""
    return _requests_json(image_info_url(service_id), session=session, timeout=timeout)


def search_html(query: str, images_only: bool = True, page: int | None = None,
                timeout: int = 30, session=None) -> str | None:
    """GET the Ligeo search results HTML for *discovery only*.

    Returns the HTML text, or None on hard failure. Check `is_anubis()` on the
    result: if True, the anti-bot challenged us and the caller should use the
    browser instead.
    """
    if requests is None:
        return None
    url = search_url(query, images_only=images_only, page=page)
    try:
        sess = session or requests
        r = sess.get(url, headers=HTML_HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            return r.text
    except Exception:  # noqa: BLE001
        return None
    return None


# ------------------------------------------------------------------- parsing

def _strip_html(text: str) -> str:
    txt = _TAG_RE.sub(" ", str(text or ""))
    txt = _html.unescape(txt)
    return re.sub(r"\s+", " ", txt).strip()


def is_anubis(text: str) -> bool:
    """True if the response body is an Anubis anti-bot challenge page."""
    return bool(_ANUBIS_RE.search(str(text or "")[:4000]))


def extract_arks(text: str) -> list[str]:
    """Pull unique ARK suffixes out of an HTML page (e.g. a search result page).

    Deduplicated, order-preserving. Enumeration of the *search* page itself may
    need the browser when Anubis challenges; this only parses the HTML.
    """
    seen: dict[str, None] = {}
    for m in _ARK_RE.finditer(str(text)):
        seen.setdefault(m.group(1), None)
    return list(seen)


def parse_fonds(text: str) -> list[dict]:
    """Parse the fonds tabs of a search page: [{fonds_id, title, count}, ...].

    `fonds_id` is the Ligeo/EAD id (e.g. 'FRANMT_IR_PII'); `count` is the
    "N résultat(s)" figure, or None.
    """
    out: list[dict] = []
    for m in re.finditer(r'id="arc_songlet_([^"]+)"[^>]*>(.*?)</a>', str(text), re.S):
        fid = m.group(1)
        inner = m.group(2)
        cm = re.search(r"(\d+)\s*r[ée]sultat", inner, re.I)
        title = _strip_html(inner)
        title = re.sub(r"-?\s*\d+\s*r[ée]sultat\(s\)\s*$", "", title).strip(" -")
        out.append({
            "fonds_id": fid,
            "title": title,
            "count": int(cm.group(1)) if cm else None,
        })
    return out


def _metadata(manifest: dict) -> dict:
    out: dict = {}
    for entry in manifest.get("metadata", []) or []:
        label = str(entry.get("label", "")).strip().lower()
        value = entry.get("value")
        if isinstance(value, list):
            value = " ".join(str(v) for v in value)
        if label in _META_MAP:
            out[_META_MAP[label]] = value
    return out


def _canvases(manifest: dict) -> list[dict]:
    seqs = manifest.get("sequences")
    if isinstance(seqs, list) and seqs:
        return list(seqs[0].get("canvases", []) or [])
    items = manifest.get("items")  # IIIF v3 fallback
    return list(items or [])


def _canvas_service(canvas: dict) -> str | None:
    for img in canvas.get("images", []) or []:
        res = img.get("resource", img)
        svc = res.get("service")
        if isinstance(svc, list):
            svc = svc[0] if svc else None
        if isinstance(svc, dict) and svc.get("@id"):
            return svc["@id"]
    # IIIF v3 shape
    for img in canvas.get("items", []) or []:
        for body in img.get("items", []) or []:
            for it in body.get("items", []) or []:
                if it.get("body", {}).get("id"):
                    return it["body"]["id"]
    return None


def _thumb_id(canvas: dict) -> str | None:
    thumb = canvas.get("thumbnail")
    if isinstance(thumb, list):
        thumb = thumb[0] if thumb else None
    if isinstance(thumb, dict):
        return thumb.get("@id")
    if isinstance(thumb, str):
        return thumb
    return None


def _ark_from_id(canvas_or_manifest_id: str) -> str | None:
    m = _ARK_RE.search(str(canvas_or_manifest_id))
    return m.group(1) if m else None


def parse_manifest(manifest: dict) -> dict:
    """Normalize a manifest into a flat dict the connector can consume.

    Keys: ark, label, attribution, license (clean text), license_html,
    license_verdict, reusable, restricted, restricted_count, canvas_count,
    images (list of dicts), permalink, metadata.
    """
    meta = _metadata(manifest)
    canvases = _canvases(manifest)
    reuse = manifest.get("ligeoReUseProfil") or {}
    license_html = reuse.get("content") if isinstance(reuse, dict) else None
    license_text = _strip_html(license_html) if license_html else (
        manifest.get("license") or manifest.get("attribution")
    )

    images: list[dict] = []
    restricted_count = 0
    for i, canvas in enumerate(canvases):
        svc = _canvas_service(canvas)
        restricted = bool(canvas.get("ligeoRestrictedAccess"))
        if restricted:
            restricted_count += 1
        thumb = _thumb_id(canvas)
        if svc:
            thumb = thumb_url(svc)  # prefer IIIF over the IIPServer URL
        render = canvas.get("rendering")
        if isinstance(render, list):
            render = render[0] if render else None
        images.append({
            "index": i,
            "canvas_id": canvas.get("@id"),
            "label": canvas.get("label"),
            "service_id": svc,
            "width": canvas.get("width"),
            "height": canvas.get("height"),
            "thumbnail": thumb,
            "full_image": image_url(svc, size="max") if svc else None,
            "restricted": restricted,
            "searchable": bool(canvas.get("ligeoIsSearchable")),
            "permalink": canvas.get("ligeoPermalink")
            or (render.get("@id") if isinstance(render, dict) else None),
        })

    return {
        "ark": meta.get("ark") or _ark_from_id(manifest.get("@id", "")),
        "label": manifest.get("label"),
        "attribution": manifest.get("attribution"),
        "license": license_text,
        "license_html": license_html,
        "license_verdict": LICENSE_VERDICT if is_reusable(manifest) else "restricted",
        "reusable": is_reusable(manifest),
        "restricted": restricted_count > 0,
        "restricted_count": restricted_count,
        "canvas_count": len(canvases),
        "images": images,
        "permalink": manifest.get("@id"),
        "metadata": meta,
    }


def records_from_manifest(manifest: dict, naan: str = ARK_NAAN) -> list[dict]:
    """Flatten a manifest into one record per *displayable* canvas.

    Skips `ligeoRestrictedAccess: true` canvases (not displayable/reusable).
    Returns [] if every canvas is restricted or none is displayable.
    """
    parsed = parse_manifest(manifest)
    out: list[dict] = []
    for img in parsed["images"]:
        if img["restricted"] or not img["service_id"]:
            continue
        title = parsed["label"]
        if parsed["canvas_count"] > 1 and img.get("label"):
            title = f"{parsed['label']} — {img['label']}"
        out.append({
            "id": f"{parsed['ark']}#{img['index']}" if parsed["ark"] else img["canvas_id"],
            "ark": parsed["ark"],
            "source_url": img.get("permalink") or notice_url(parsed["ark"], naan),
            "title": title,
            "image_url": img["full_image"],
            "thumbnail": img["thumbnail"],
            "service_id": img["service_id"],
            "width": img["width"],
            "height": img["height"],
            "license": parsed["license"],
            "attribution": parsed["attribution"] or LICENSE_ATTRIBUTION,
            "cote": parsed["metadata"].get("cote"),
            "date": parsed["metadata"].get("date"),
            "restricted": False,
        })
    return out


# ------------------------------------------------------------------- verdicts

def is_restricted(manifest: dict) -> bool:
    """True if ANY canvas is non-displayable (ligeoRestrictedAccess)."""
    return any(bool(c.get("ligeoRestrictedAccess")) for c in _canvases(manifest))


def is_reusable(manifest: dict) -> bool:
    """True if the manifest's reuse profile grants free (incl. commercial) reuse.

    ANMT reuse text is uniform: non-exclusive, free, commercial or not,
    worldwide, unlimited duration. Absence of the profile => not reusable.
    """
    reuse = manifest.get("ligeoReUseProfil") or {}
    raw = (reuse.get("content") if isinstance(reuse, dict) else "") or ""
    if not raw:
        raw = str(manifest.get("license") or "")
    low = _strip_html(raw).lower()
    if "non affichable" in low or "restrict" in low:
        return False
    return "commerciales ou non" in low or "libre réutilisation" in low


def summary(manifest: dict) -> dict:
    """Tiny human-readable summary (ark, label, canvases, restricted, reusable)."""
    p = parse_manifest(manifest)
    return {
        "ark": p["ark"],
        "label": p["label"],
        "canvas_count": p["canvas_count"],
        "restricted": p["restricted"],
        "restricted_count": p["restricted_count"],
        "reusable": p["reusable"],
    }


__all__ = [
    "BASE", "ARK_NAAN", "MANIFEST_URL", "NOTICE_URL", "VIEWER_URL",
    "SEARCH_PATH", "SEARCH_URL", "RESULTS_URL", "OAI_URL", "ROBOTS_CRAWL_DELAY",
    "LICENSE_VERDICT", "LICENSE_ATTRIBUTION", "LICENSE_NOTICE_FRAGMENT",
    "manifest_url", "notice_url", "viewer_url", "search_url",
    "image_info_url", "image_url", "thumb_url",
    "fetch_manifest", "fetch_info", "search_html",
    "is_anubis", "extract_arks", "parse_fonds",
    "parse_manifest", "records_from_manifest",
    "is_restricted", "is_reusable", "summary",
]
