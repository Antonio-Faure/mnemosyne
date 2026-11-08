"""IWM — Imperial War Museums, WW1 photography collections (source id: iwm_ww1).

Researched by the navigator agent (mnemosyne) to wire an *exploitable* photo
search onto IWM's First World War photographs (the "Q" series). This module is
the reference the coder turns into `config/sources/iwm_ww1.yaml` + a connector.
It also ships a working, tested `search_ww1()` so the descriptor can be
validated before the PR.

=====================================================================================
TL;DR / RECOMMENDATION
=====================================================================================
IWM itself exposes **no usable public JSON search API** and its collections
search page is **robots-disallowed**. The clean, keyless, licence-clean,
programmatic route to the *same* IWM WW1 photographs is **Wikimedia Commons**,
where IWM donated its WW1 official photography (public domain). Build the
`iwm_ww1` connector on the **MediaWiki API** (Part B). Use Part A only as
background / for high-res originals when you already hold a Q-number.

=====================================================================================
PART A — DIRECT IWM (background; NOT used as the source's data path)
=====================================================================================
Host ................ https://www.iwm.org.uk
Collections landing .. https://www.iwm.org.uk/collections
Search (HTML)........ https://www.iwm.org.uk/collections/search
                       ?query=<text>&page=<0-based>&media-records=all-records
                       (+ filters e.g. object category=Photographs,
                        related period=First World War)
Item detail (HTML)... https://www.iwm.org.uk/collections/item/object/<numeric id>
Image IIIF .......... https://media.iwm.org.uk/cantaloupe/iiif/2/<id>/info.json
                       IIIF Image API **2.1** (Cantaloupe).  e.g. an item page's
                       data-zoom holds `.../iiif/2/417||112||super_000000.jpg/info.json`;
                       then `.../<id>/full/max/0/default.jpg` etc. CONFIRMED 200.
Static images ....... https://media.iwm.org.uk/ciim5/<a>/<b>/large_000000.jpg   (full)
                       https://media.iwm.org.uk/ciim5/<a>/<b>/mid_000000.jpg     (thumb)

Why NOT the source's data path:
  * robots.txt (https://www.iwm.org.uk/robots.txt) has an explicit
    `Disallow: /collections/search` (plus the default Drupal block on /search/),
    and a Cloudflare `Content-Signal: search=yes, ai-train=no, use=reference`.
    => Automated fetching of the search page is off-limits; scraping is out.
  * No public JSON/OpenSearch/OAI endpoint:
      - https://www.iwm.org.uk/jsonapi  -> Drupal JSON:API, but only exposes
        branch/event/learning_resource/paragraph/taxonomy_term + media--image /
        file--file. The collection objects (Q series) are NOT in JSON:API.
      - _format=json on the search route -> 406; /collections/search.json -> 404;
        /views/ajax -> 404; /oai, /opensearch.xml -> 404.
      - https://api.iwm.org.uk/** -> HTTP 403 for everything (private/partner
        WAF; not documented publicly).
  * IWM site images are "© IWM" (licensing required), not open — wrong for a
    free/open reuse aggregator.
  Note: urllib with the generic UA gets 403; a full browser UA + Accept headers
  is needed even for the allowed item HTML pages.

=====================================================================================
PART B — WIKIMEDIA COMMONS (the recommended programmatic source)
=====================================================================================
IWM released its WW1 official photography to Commons; these ARE the Q-series
photographs (Western Front, Belgium 1914, refugees, etc.), Public Domain, with
the IWM catalogue number (Qxxxx) in the filename and a "© IWM" credit.

Host .......... https://commons.wikimedia.org/w/api.php   (MediaWiki API)
Auth .......... NONE (no key). Send a descriptive User-Agent (Wikimedia policy).
Response ...... JSON. Use `format=json` (+ `formatversion=2` for a list-shaped
                `pages` and `imageinfo` arrays).

Coverage (direct file counts, confirmed):
  Ministry of Information First World War Official Collection ... 10,508 (Q series)
  The Official Visits To the Western Front, 1914-1918 ..........   358
  IWM First World War Women's War Work Collection photographs .. (WW1)
  First World War Aerial Photographs Collection / ... Panoramas  (WW1)
  Parent: Photographs from the Imperial War Museum (whole archive incl. WW2)

Search recipe (free text -> IWM WW1 photos, paginated) — CONFIRMED:
  GET https://commons.wikimedia.org/w/api.php
    action        = query
    generator     = search
    gsrsearch     = <phrase> incategory:"...First World War Official Collection"
    gsrnamespace  = 6                     # File: namespace
    gsrlimit      = <1..50>               # results per page
    gsroffset     = <0, 50, 100, ...>     # via reply.continue.gsroffset
    prop          = imageinfo
    iiprop        = url|size|mime|extmetadata|user
    iiurlwidth    = 800                   # optional thumb width
    formatversion = 2
    format        = json
  (Full category name for gsrsearch: "Ministry of Information First World War
   Official Collection".)
  Broader (whole IWM photo archive; phrase-driven, includes WW2):
    gsrsearch = <phrase>  deepcat:"Photographs from the Imperial War Museum"
    (deepcat does deep-category search and works on Commons; slower.)
  WW1 union (optional, best coverage): run the incategory query once per WW1
    collection category above and merge, de-duplicating on pageid.

Pagination: reply["continue"]["gsroffset"] + reply["continue"]["continue"].

Normalization mapping (formatversion=2) -> mnemosyne record:
  pageid / title : pages[].pageid / pages[].title  ("File:...")
  catalog_ref    : regex Q\\s?\\d+ on title (or on iwm_credit) -> e.g. "Q9848"
  title_clean    : title without "File:", extension and trailing Q-number
                   (e.g. "The Trench Warfare on the Western Front, 1914-1918")
  description    : extmetadata.ImageDescription (strip HTML)
  creator        : extmetadata.Artist           (photographer, e.g. Ernest Brooks)
  date           : extmetadata.DateTimeOriginal  (e.g. "10 January 1917 (First World War)")
  license        : extmetadata.LicenseShortName  ("Public domain" for ~all WW1)
  image_url      : imageinfo.url with the query-string stripped  (full res)
  thumb_url      : https://commons.wikimedia.org/wiki/Special:FilePath/<urlenc>?width=<W>
                   (Special:FilePath always 302-> a valid thumbnail at any width;
                    more reliable than constructing .../thumb/... paths)
  width/height   : imageinfo.width / imageinfo.height
  mime           : imageinfo.mime
  source_page    : imageinfo.descriptionurl  (the Commons File: page — for reuse/attribution)
  iwm_credit     : extmetadata.Credit  -> contains "This photograph Q xxxx comes
                   from the collections of the Imperial War Museums." + old media URL

Licensing / attribution:
  These WW1 files are Public Domain (sample of 50: 100% "Public domain";
  Copyrighted == False). Attribute as `© IWM (Q xxxx)` and link `source_page`
  (the Commons File page) on reuse. Filter the connector to
  LicenseShortName in {Public domain, CC0, CC BY*, CC BY-SA*, PD-*} to stay
  open-reuse-safe (skip anything Copyrighted == True).

Verified example (live):
  query "trench Western Front"  incategory official -> Q4659 (Lancashire
  Fusiliers, Messines, Jan 1917), Q6421 (sentry at night, Hesdin), etc.;
  image 200 image/jpeg; descriptionurl = the Commons File page.
=====================================================================================
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

MW_API = "https://commons.wikimedia.org/w/api.php"
UA = (
    "mnemosyne-research-bot/1.0 "
    "(https://github.com/Antonio-Faure/mnemosyne; opensource research aggregator)"
)

# WW1 collection categories on Commons (direct file members).
WW1_CATEGORIES = {
    "official": "Ministry of Information First World War Official Collection",  # Q series, 10,508
    "visits": "The Official Visits To the Western Front, 1914-1918",
    "women": "Imperial War Museum First World War Women's War Work Collection photographs",
    "aerial": "First World War Aerial Photographs Collection",
    "panoramas": "First World War Official Panoramas Collection",
    "misc": "Ministry of Information First World War Miscellaneous Collection",
}


def _mw_api(params: dict, timeout: int = 30) -> dict:
    """Low-level MediaWiki API GET -> parsed JSON. No key required."""
    params = dict(params)
    params.setdefault("format", "json")
    url = MW_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _strip_html(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", str(s))
    return re.sub(r"\s+", " ", s).strip()


def _clean_title(page_title: str) -> str:
    t = page_title[len("File:"):] if page_title.startswith("File:") else page_title
    t = re.sub(r"\.(jpe?g|png|tif?f|gif)$", "", t, flags=re.I)
    t = re.sub(r"\s+Q\s?\d+\s*$", "", t)  # drop trailing IWM catalogue number
    return t.strip()


def _thumb_url(page_title: str, width: int) -> str:
    name = page_title[len("File:"):] if page_title.startswith("File:") else page_title
    return (
        "https://commons.wikimedia.org/wiki/Special:FilePath/"
        + urllib.parse.quote(name.replace(" ", "_"))
        + f"?width={int(width)}"
    )


def _normalize(page: dict, width: int = 800) -> dict:
    ii = (page.get("imageinfo") or [{}])[0]
    em = ii.get("extmetadata", {}) or {}
    title = page.get("title", "")
    credit = _strip_html(em.get("Credit", {}).get("value", ""))
    m = re.search(r"Q\s?\d+", title) or re.search(r"Q\s?\d+", credit)
    full = (ii.get("url") or "").split("?")[0]
    return {
        "pageid": page.get("pageid"),
        "page_title": title,
        "catalog_ref": m.group(0).replace(" ", "") if m else None,  # e.g. Q9848
        "title": _clean_title(title),
        "description": _strip_html(em.get("ImageDescription", {}).get("value", "")),
        "creator": _strip_html(em.get("Artist", {}).get("value", "")),
        "date": _strip_html(em.get("DateTimeOriginal", {}).get("value", "")),
        "license": em.get("LicenseShortName", {}).get("value"),
        "copyrighted": em.get("Copyrighted", {}).get("value"),
        "iwm_credit": credit,
        "image_url": full or None,
        "thumb_url": _thumb_url(title, width) if title else None,
        "width": ii.get("width"),
        "height": ii.get("height"),
        "mime": ii.get("mime"),
        "source_page": ii.get("descriptionurl"),
        "categories": " ".join(
            (em.get("Categories", {}).get("value") or "").split("|")
        ),
    }


def search_ww1(query: str, limit: int = 25, offset: int = 0,
               scope: str = "official", width: int = 800) -> dict:
    """Free-text search limited to IWM WW1 photographs on Commons.

    scope: key of WW1_CATEGORIES ("official" = the Q series, default) OR
           "archive" = deepcat over the whole IWM photo tree (phrase-driven).
    Returns {"records": [...], "continue": {...}|None, "query": query}.
    """
    if scope == "archive":
        clause = 'deepcat:"Photographs from the Imperial War Museum"'
    else:
        cat = WW1_CATEGORIES.get(scope, WW1_CATEGORIES["official"])
        clause = f'incategory:"{cat}"'
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"{query} {clause}",
        "gsrnamespace": "6",
        "gsrlimit": str(max(1, min(int(limit), 50))),
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata|user",
        "iiurlwidth": str(int(width)),
        "formatversion": "2",
    }
    if offset:
        params["gsroffset"] = str(int(offset))
    data = _mw_api(params)
    pages = data.get("query", {}).get("pages", []) or []
    return {
        "records": [_normalize(p, width) for p in pages],
        "continue": data.get("continue"),
        "query": query,
    }


def get_file(page_title: str, width: int = 800) -> dict | None:
    """Full normalized metadata for one Commons File: page (by title or pageid)."""
    if not str(page_title).startswith("File:") and str(page_title).isdigit():
        params = {"action": "query", "pageids": str(page_title)}
    else:
        t = page_title if str(page_title).startswith("File:") else f"File:{page_title}"
        params = {"action": "query", "titles": t}
    params.update({
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata|user",
        "iiurlwidth": str(int(width)),
        "formatversion": "2",
    })
    data = _mw_api(params)
    pages = data.get("query", {}).get("pages", []) or []
    if not pages or "missing" in pages[0]:
        return None
    return _normalize(pages[0], width)


if __name__ == "__main__":  # tiny live self-test
    res = search_ww1("trench Western Front", limit=3)
    for rec in res["records"]:
        print(rec["catalog_ref"], "|", rec["creator"], "|", rec["date"],
              "|", rec["license"], "|", rec["image_url"])
