"""Musée d'Art et d'Industrie de Saint-Étienne (MAI) — collection access helper.

Reconnaissance by the mnemosyne navigator agent (task #46).  Read-only: every
function only GETs and parses; nothing writes to the remote.

Where the images live
---------------------
The museum's vitrine site https://mai.saint-etienne.fr (WordPress) links, via
"Voir les collections", to its online collection database: a **Micromusée
"opacweb"** portal powered by an **API Platform (Hydra) JSON API v2**.  There is
no public OAI-PMH endpoint; images are delivered by a CloudFront distribution
(host ``d2lkryo36aywim.cloudfront.net``).  The portal advertises 2 981 online
notices.

Access path
-----------
Portal : https://collections.musee-art-industrie.saint-etienne.fr/   (www. too)
API    : https://collections.musee-art-industrie.saint-etienne.fr/api/v2
  GET /api/v2/notices/search?onlineFilter=online&items_per_page=N&page=P&query=Q
      -> hydra:Collection {hydra:totalItems, hydra:view{first,last,next},
                            hydra:member:[Notice, ...]}
  GET /api/v2/notices/{id}       -> Notice (full record)
  GET /api/v2/facets/tree?onlineFilter=online&onlyEnabled=true&query=
  GET /api/v2/docs.jsonld        -> Hydra API docs

Search params
  onlineFilter=online   public notices only (2981)
  onlyImage=true        notices that have >=1 image
  items_per_page=N      N >= 200 accepted (default 30 in the SPA)
  page=P                1-based; hydra:view gives first/last/next
  query=Q               free text, e.g. "ruban", "Manufrance", "fusil"

Notice (key fields)
  id, nativeId, slug, url, isEnabled, isArchived, hasImage,
  noticeCollections:["rubans","images-de-soie","la-mecanique-de-l-art", ...],
  titles:{title, subTitle, text, native_title},
  client:"st-etienne01", profile:"mai04opacweb",
  images:{lazy,small,medium,large}, mainImageLazy/Small/Medium/LargeUrl,
  mediaFiles:[{type:"image", name, fileName, position}, ...],
  zones:[{code,label,occurZones:[{fields:[{code,label,content}]}]}]

Image URLs
  CloudFront "thumbor-like" URLs whose path is the base64 of
  ``{"bucket":"opac-prod-media","key":"<client>/<profile>/<fileName>",
  "edits":{"resize":{"width":W,"height":W,"fit":"inside"}}}``.  The portal
  exposes 20/190/360/720 px; the same builder with any width returns a
  server-side resize of the ORIGINAL (verified up to 3000 px), so higher
  resolutions are reachable without the (authorisation-gated) full-res file.

Licence (per notice / site-wide footer)
  Every notice page watermarks the image "© Pôle muséal de Saint-Etienne" and
  its footer states: "©2023 Musée d'Art et d'Industrie de Saint-Etienne —
  Utilisation commerciale des images soumise à autorisation — Merci de contacter
  mai.iconotheque@saint-etienne.fr".  There is NO per-record licence field: the
  rights statement is global and reserves commercial reuse (authorisation
  required).  => restrictive / NonCommercial  => descriptor ``enabled: false``.
"""

from __future__ import annotations

import base64
import json
import time

import requests

UA = (
    "mnemosyne-research-bot/1.0 "
    "(https://github.com/Antonio-Faure/mnemosyne; opensource research aggregator)"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, application/ld+json, */*;q=0.8",
}

PORTAL = "https://collections.musee-art-industrie.saint-etienne.fr"
API = PORTAL + "/api/v2"
CF_HOST = "https://d2lkryo36aywim.cloudfront.net"
BUCKET = "opac-prod-media"

# widths (px) the portal itself exposes
SIZES = {"lazy": 20, "small": 190, "medium": 360, "large": 720}

LICENSE = {
    "holder": ("Musée d'Art et d'Industrie de Saint-Étienne / "
               "Pôle muséal de Saint-Etienne"),
    "statement": ("©2023 Musée d'Art et d'Industrie de Saint-Etienne - "
                  "Utilisation commerciale des images soumise à autorisation - "
                  "Merci de contacter mai.iconotheque@saint-etienne.fr"),
    "url": PORTAL + "/fr/",
    "nc": True,
    "commercial_use": "authorisation required",
    "enabled": False,  # restrictive / NC -> do not ingest
}


def _get_json(url, params=None, timeout=30, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r.json()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1.0 * (i + 1))
    return None


# --------------------------------------------------------------------- search

def search(query="", page=1, per_page=100, only_image=True, online=True):
    """One page of the notices search.

    Returns {"total", "page", "per_page", "members", "view"}.
    """
    params = {"items_per_page": int(per_page), "page": int(page), "query": query}
    if online:
        params["onlineFilter"] = "online"
    if only_image:
        params["onlyImage"] = "true"
    d = _get_json(API + "/notices/search", params=params)
    if not d:
        return {"total": 0, "page": page, "per_page": per_page,
                "members": [], "view": None}
    return {
        "total": d.get("hydra:totalItems", 0),
        "page": page,
        "per_page": per_page,
        "members": d.get("hydra:member", []) or [],
        "view": d.get("hydra:view"),
    }


def iter_notices(query="", per_page=100, max_pages=None, only_image=True):
    """Yield notices across pages (safe: stops on empty page / total reached)."""
    page = 1
    while True:
        res = search(query=query, page=page, per_page=per_page,
                     only_image=only_image)
        members = res["members"]
        if not members:
            return
        for m in members:
            yield m
        if max_pages and page >= max_pages:
            return
        if res["total"] and page * per_page >= res["total"]:
            return
        page += 1


def get_notice(nid):
    """Full notice record by its id (Mongo ObjectId) or nativeId slug."""
    return _get_json(API + "/notices/" + str(nid))


# --------------------------------------------------------------------- images

def cloudfront_url(client, profile, filename, width=720):
    """Build a CloudFront image URL at ``width`` px (server-side resize)."""
    payload = {
        "bucket": BUCKET,
        "key": f"{client}/{profile}/{filename}",
        "edits": {"resize": {"width": int(width), "height": int(width),
                             "fit": "inside"}},
    }
    b64 = base64.b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode()
    return CF_HOST + "/" + b64


def image_urls(notice, width=720):
    """All image URLs of a notice, one per media file, at ``width`` px."""
    client, profile = notice.get("client"), notice.get("profile")
    out = []
    for mf in notice.get("mediaFiles") or []:
        fn = mf.get("fileName")
        if fn and client and profile:
            out.append(cloudfront_url(client, profile, fn, width))
    return out


def main_image(notice, width=720):
    """URL of the notice's main image at ``width`` px."""
    imgs = notice.get("images") or {}
    for key in ("lazy", "small", "medium", "large"):
        if width <= SIZES[key] and imgs.get(key):
            return imgs[key]
    urls = image_urls(notice, width)
    return urls[0] if urls else None


# ----------------------------------------------------------------- normalize

def _zone_fields(notice):
    """Flatten zones -> {field_code: [content, ...]} (ordered)."""
    out = {}
    for z in notice.get("zones") or []:
        for oz in z.get("occurZones") or []:
            for f in oz.get("fields") or []:
                out.setdefault(f.get("code"), []).append(f.get("content"))
    return out


def notice_to_item(notice, width=1200):
    """Normalise a notice into the mnemosyne item shape (for the connector)."""
    t = notice.get("titles") or {}
    f = _zone_fields(notice)
    return {
        "id": notice.get("id"),
        "native_id": notice.get("nativeId"),
        "title": t.get("title") or notice.get("title"),
        "subtitle": t.get("subTitle"),
        "date": t.get("text"),
        "url": notice.get("url"),
        "collections": notice.get("noticeCollections") or [],
        "domain": (f.get("Domaine") or [None])[0],
        "material": f.get("Matiere") or [],
        "technique": f.get("Technique") or [],
        "owner": (f.get("Proprietaire") or [None])[0],
        "inventory_number": (f.get("NumeroInventaire") or [None])[0],
        "description": (f.get("DescriptionAnalytique") or [None])[0],
        "keywords": f.get("SujetTheme") or [],
        "has_image": notice.get("hasImage"),
        "image": main_image(notice, width),
        "images": image_urls(notice, width),
        "license": LICENSE["holder"],
        "license_nc": LICENSE["nc"],
        "enabled": LICENSE["enabled"],
    }


def license_info():
    """The site-wide image rights statement for this source."""
    return dict(LICENSE)


if __name__ == "__main__":  # tiny self-check / demo
    res = search(query="ruban", page=1, per_page=3)
    print("total:", res["total"])
    for n in res["members"][:3]:
        item = notice_to_item(n, width=720)
        print("-", item["title"], "|", item["collections"], "|", item["image"])
    print("licence:", license_info()["statement"])
