"""Archives départementales du Nord — platform reference & read-only client.

Base:  https://archivesdepartementales.lenord.fr
NAAN:  33518  (ARK: /ark:/33518/<arkName>)
CMS:   Arkothèque-style front ("Mnesys"), SPA viewer, hCaptcha on forms.

Why this file exists (task #50): the Nord platform exposes NO IIIF
(`app.toolbar.isIIIFEnabled == false`, every `location.iiif == null`) and NO
OAI-PMH (`/oai-pmh` -> 404). Programmatic access is:

  * SEARCH  -> server-rendered HTML  GET /search/results?q=&page=&resultsPerPage=
  * VIEWER  -> JSON API              GET /visualizer/api?arkName=...&group=...
  * IMAGES  -> static JPEG           /images/<uuid>.jpg  (+ _thumbnail.jpg)
  * PDFs    -> static PDF            /media/<uuid>.pdf   (thumb /pdf-preview/...)

All three are reachable with a plain HTTP client (descriptive User-Agent), no
captcha and no cookies: hCaptcha only guards POST forms (contact, report,
collaborative indexing, bookmarks). Verified 2026-10-XX from a clean session.

Endpoints
---------
GET /search/results
    q             free text (also `mode=search`); example q=textile
    page          1-based; resultsPerPage in {20,40,80} (default 20)
    -> HTML: <li class="element-list"> items, "N résultats" counter,
       page N/M pagination links (?q=..&page=N).
    Each item is EITHER
       (a) a record with images:
           <a href="/ark:/33518/<arkName>/<mediaUuid>"> ... <h2>title</h2>
           <p class="info-list-picture">N medias</p>
       (b) a PDF document (finding aid):
           <a href="/media/<uuid>.pdf"> ... <h2>title</h2>
           <p class="info-list-picture">Document PDF (N pages)</p>
           thumb: /pdf-preview/<uuid>_search_result_thumbnail

GET /visualizer/api   (JSON; the viewer SPA calls it)
    arkName=<arkName>              record id (required)
    group=<g>                      0-based group index (REQUIRED for lists)
    start=<s>&end=<e>              media slice, end INCLUSIVE, max = media-1
    uuid=<mediaUuid>               single-media view (adds counts + app config)
    -> group call:  {"counts":{"media":N,"group":G},"positions":{...},
                     "group":{...},"media":[Media,...]}
    -> uuid call:   same + "app" (site config + licence) + "tableOfContents"
    -> range call:  bare JSON array of Media
    Errors (plain text, HTTP 400): "Unable to handle this request" (missing
    group), "Invalid request: group index or ArkName or start/end boundaries
    values are not valid" (bad ark / end > media-1).

Media
-----
{
 "url": "https://archivesdepartementales.lenord.fr/ark:/33518/<ark>/<uuid>",
 "record": {"arkId": {"arkName": "...", "naan": 33518},
            "url": ".../ark:/33518/<ark>", "title": ["..."],
            "referenceCode": ["..."], "description": null,
            "period": {"boundaries": ["YYYY-MM-DD","..."], "certainty": null},
            "locationKeywords": ["..."]},
 "uuid": "<mediaUuid>",
 "location": {"original": ".../images/<uuid>.jpg",
              "thumb":    ".../images/<uuid>_thumbnail.jpg",
              "iiif": null},
 "type": "image", "format": "jpg", "title": null
}

GET /api/classificationPlan/v1/tree/<nodeId>     cadre de classement (JSON)
    -> {id,title,dataType,data:{childrenUrl,children,url,contentUrl}}
       childrenUrl: /api/classificationPlan/v1/children/<nodeId>
GET /ark:/33518/<arkName>                         record notice (HTML)
GET /ark:/33518/<arkName>/<mediaUuid>             viewer (SPA shell)

Rights / licence  (app.licenses.visualizer, uuid b6bad2e5-96d0-4166-ae0b-f01ebe0ab972)
---------------------------------------------------------------------------------
"Dans le cadre légal, et en application de la délibération du Conseil
départemental du Nord du 27 mars 2017. La réutilisation COMMERCIALE des
informations publiques issues d'opérations de numérisation des archives ...
est soumise au paiement d'une redevance et à la souscription d'une licence.
Une demande écrite est à effectuer. Toute autre réutilisation est gratuite,
avec obligation: de citer la source (Archives départementales du Nord, cote)
...; de ne pas altérer ces informations."

=> digitised image files are NOT openly reusable for commercial use: paid fee
   + written licence. This is RESTRICTIVE -> source descriptor enabled: false.

Normalization notes for the connector
-------------------------------------
- asset id:        media["uuid"]
- source record:   media["record"]["url"]  (notice /ark:/33518/<ark>)
- title:           media["record"]["title"][0]  (fallback media["title"])
- cote:            media["record"]["referenceCode"][0]
- thumbnail:       media["location"]["thumb"]   (/images/<uuid>_thumbnail.jpg)
- full image:      media["location"]["original"] (/images/<uuid>.jpg)
- date:            media["record"]["period"]["boundaries"]
- places/keywords: media["record"]["locationKeywords"]
- license:         "Restrictive — AD Nord, délibération 27/03/2017
                    (commercial reuse of scans = fee + licence)"
- enabled:         false
"""

from __future__ import annotations

import html as _html
import re

import requests

BASE = "https://archivesdepartementales.lenord.fr"
UA = (
    "mnemosyne-research-bot/1.0 "
    "(https://github.com/Antonio-Faure/mnemosyne; opensource research aggregator)"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.6",
}

_S = requests.Session()
_S.headers.update(HEADERS)

_ITEM_RE = re.compile(r'<li class="element-list">(.*?)(?=<li class="element-list">|\Z)', re.S)
_HREF_RE = re.compile(r'<a\s[^>]*href="([^"]+)"')
_H2_RE = re.compile(r"<h2>\s*(.*?)\s*</h2>", re.S)
_INFO_RE = re.compile(r'<p class="info-list-picture">\s*(.*?)\s*</p>', re.S)
_IMG_RE = re.compile(r'<img\s[^>]*src="([^"]+)"')
_COUNT_RE = re.compile(r"(\d[\d\s\u00a0]*)\s*résultats?", re.I)
_REC_RE = re.compile(r"/ark:/33518/([A-Za-z0-9]+)/([0-9a-fA-F\-]{36})")
_PDF_RE = re.compile(r"/media/([0-9a-fA-F\-]{36})\.pdf")


def _strip(s: str) -> str:
    return _html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def _abs(u: str) -> str:
    if not u:
        return u
    return u if u.startswith("http") else BASE + u


def search(query: str, page: int = 1, per_page: int = 20, timeout: int = 30) -> dict:
    """GET /search/results?q=... -> {"total": int, "items": [dict, ...]}.

    Each item: {kind, href, title, media_count|pages, record_id, media_uuid,
    pdf_uuid, thumb}.  kind is "record" (has images) or "document" (PDF).
    """
    r = _S.get(
        BASE + "/search/results",
        params={"q": query, "page": page, "resultsPerPage": per_page},
        timeout=timeout,
    )
    r.raise_for_status()
    text = r.text
    m = _COUNT_RE.search(text)
    total = int(re.sub(r"\D", "", m.group(1))) if m else 0

    items: list[dict] = []
    for block in _ITEM_RE.findall(text):
        href_m = _HREF_RE.search(block)
        if not href_m:
            continue
        href = _abs(href_m.group(1))
        title = _strip(_H2_RE.search(block).group(1)) if _H2_RE.search(block) else ""
        info = _strip(_INFO_RE.search(block).group(1)) if _INFO_RE.search(block) else ""
        img = _IMG_RE.search(block)
        thumb = _abs(img.group(1)) if img else None
        rec = _REC_RE.search(href)
        pdf = _PDF_RE.search(href)
        if rec:
            mc = re.search(r"(\d+)\s*medias?", info)
            items.append({
                "kind": "record", "href": href, "title": title,
                "record_id": rec.group(1), "media_uuid": rec.group(2),
                "media_count": int(mc.group(1)) if mc else None,
                "pdf_uuid": None, "thumb": thumb,
            })
        elif pdf:
            pg = re.search(r"(\d[\d\s\u00a0]*)\s*pages?", info)
            items.append({
                "kind": "document", "href": href, "title": title,
                "record_id": None, "media_uuid": None, "media_count": None,
                "pdf_uuid": pdf.group(1),
                "pages": int(re.sub(r"\D", "", pg.group(1))) if pg else None,
                "thumb": thumb,
            })
    return {"total": total, "page": page, "per_page": per_page, "items": items}


def record_group(ark_name: str, group: int = 0, timeout: int = 40) -> dict:
    """GET /visualizer/api?arkName=<id>&group=<g>.

    Returns {"counts": {"media": N, "group": G}, "group": {...},
    "media": [Media, ...]} (first page).  Raises on a 400 (bad ark/group).
    """
    r = _S.get(BASE + "/visualizer/api",
               params={"arkName": ark_name, "group": group}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def record_media(ark_name: str, start: int = 0, end: int | None = None,
                 group: int = 0, timeout: int = 60) -> list[dict]:
    """GET /visualizer/api?arkName=&start=&end=&group= -> [Media, ...].

    `end` is INCLUSIVE; if None it is resolved to counts.media-1 via a group
    call.  (end must be <= counts.media-1 or the API answers 400.)
    """
    if end is None:
        end = record_group(ark_name, group=group, timeout=timeout)["counts"]["media"] - 1
    if end < start:
        return []
    r = _S.get(BASE + "/visualizer/api",
               params={"arkName": ark_name, "start": start, "end": end,
                       "group": group},
               timeout=timeout)
    r.raise_for_status()
    return r.json()


def all_media(ark_name: str, group: int = 0, page_size: int = 100,
              timeout: int = 60) -> list[dict]:
    """Enumerate every Media of a record, paging to stay polite."""
    out: list[dict] = []
    total = record_group(ark_name, group=group, timeout=timeout)["counts"]["media"]
    for start in range(0, total, page_size):
        end = min(start + page_size - 1, total - 1)
        out.extend(record_media(ark_name, start=start, end=end, group=group,
                                timeout=timeout))
    return out


def media_detail(ark_name: str, uuid: str, timeout: int = 40) -> dict:
    """GET /visualizer/api?arkName=&uuid= -> single-media payload.

    Adds "counts" and "app" (site config incl. the licence text).
    """
    r = _S.get(BASE + "/visualizer/api",
               params={"arkName": ark_name, "uuid": uuid}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def image_urls(uuid: str) -> dict:
    """Static image URLs for a media uuid (no IIIF on this platform)."""
    return {
        "original": f"{BASE}/images/{uuid}.jpg",
        "thumb": f"{BASE}/images/{uuid}_thumbnail.jpg",
        "iiif": None,
    }


def classification_tree(node_id: str, timeout: int = 40) -> dict:
    """GET /api/classificationPlan/v1/tree/<nodeId> (cadre de classement)."""
    r = _S.get(BASE + f"/api/classificationPlan/v1/tree/{node_id}", timeout=timeout)
    r.raise_for_status()
    return r.json()


def license_text() -> str:
    """Global reuse licence shown on every notice (app.licenses.visualizer)."""
    # any record+uuid call embeds the app config; reuse a stable sample record
    payload = media_detail("j0h8xbmd3tkn", "284c50a2-dd55-417e-8a09-980bdab78f80")
    return payload.get("app", {}).get("licenses", {}).get("visualizer", {}).get("text", "")


if __name__ == "__main__":  # tiny smoke test
    res = search("mines", page=1)
    print("total:", res["total"])
    for it in res["items"][:3]:
        print(" ", it["kind"], it["title"][:50], it.get("media_count") or it.get("pages"))
    rec = next((i for i in res["items"] if i["kind"] == "record"), None)
    if rec:
        media = all_media(rec["record_id"])
        print("media:", len(media), "| first:", media[0]["location"]["original"])
