"""Helpers to gather free 'Affiches de la Belle Époque (1890-1914)' from
open archives: Wikimedia Commons, Gallica (BnF), Internet Archive.

Politeness: a descriptive User-Agent for Wikimedia, a browser User-Agent for
Gallica (which rejects bot UAs and rate-limits), maxlag=5, and paced retries.
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET

import requests

UA = (
    "mnemosyne-research-bot/1.0 "
    "(https://github.com/Antonio-Faure/mnemosyne; opensource research aggregator)"
)
CHROME_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
S = requests.Session()
S.headers.update({"User-Agent": UA})
G = requests.Session()
G.headers.update({"User-Agent": CHROME_UA,
                  "Accept": "application/xml,text/xml,*/*;q=0.8",
                  "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"})

COMMONS = "https://commons.wikimedia.org/w/api.php"
GALLICA = "https://gallica.bnf.fr/SRU"
IA_SEARCH = "https://archive.org/advancedsearch.php"
IA_META = "https://archive.org/metadata/"

_LAST = {"t": 0.0}


def _pace(min_gap: float = 1.2) -> None:
    dt = time.time() - _LAST["t"]
    if dt < min_gap:
        time.sleep(min_gap - dt)
    _LAST["t"] = time.time()


def _get(url, params=None, retries=6, base=1.5, min_gap=1.2, stream=False, sess=S):
    last = None
    for i in range(retries):
        _pace(min_gap)
        try:
            r = sess.get(url, params=params, timeout=45, stream=stream)
            if r.status_code == 200:
                return r
            last = (r.status_code, r.headers.get("Retry-After"))
        except Exception as e:  # noqa: BLE001
            last = repr(e)[:120]
        time.sleep(base * (i + 1))
    print("  !! HTTP fail", url, last)
    return None


def _get_json(url, params=None, retries=6, base=1.5, min_gap=1.2, sess=S):
    r = _get(url, params=params, retries=retries, base=base, min_gap=min_gap, sess=sess)
    if r is None:
        return None
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- Wikimedia

def commons_catfiles(cat: str, limit: int = 1000) -> list[str]:
    titles: list[str] = []
    cont = None
    while True:
        p = {
            "action": "query", "list": "categorymembers", "cmtitle": cat,
            "cmtype": "file", "cmlimit": "500", "format": "json", "maxlag": "5",
        }
        if cont:
            p["cmcontinue"] = cont
        j = _get_json(COMMONS, p)
        if not j:
            break
        titles += [x["title"] for x in j.get("query", {}).get("categorymembers", [])]
        cont = j.get("continue", {}).get("cmcontinue")
        if not cont or len(titles) >= limit:
            break
    return titles


def commons_imageinfo(titles: list[str]) -> dict:
    out: dict = {}
    for k in range(0, len(titles), 50):
        chunk = titles[k:k + 50]
        p = {
            "action": "query", "titles": "|".join(chunk), "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiextmetadatafilter": (
                "LicenseShortName|LicenseUrl|Artist|DateTimeOriginal|ObjectName|"
                "ImageDescription|UsageTerms|Copyrighted|Credit|Restrictions|Attribution"
            ),
            "format": "json", "maxlag": "5",
        }
        j = _get_json(COMMONS, p)
        if j:
            for _pid, pg in j.get("query", {}).get("pages", {}).items():
                out[pg.get("title")] = (pg.get("imageinfo") or [{}])[0]
    return out


# ---------------------------------------------------------------- Gallica

_DC_ELEM = "{http://www.openarchives.org/OAI/2.0/oai_dc/}dc"
_DC = "{http://purl.org/dc/elements/1.1/}"
_SRW = "{http://www.loc.gov/zing/srw/}"


def gallica_search(query: str, n: int = 50, start: int = 1) -> list[dict]:
    r = _get(GALLICA, sess=G, min_gap=1.8, retries=5, params={
        "operation": "searchRetrieve", "version": "1.2", "query": query,
        "startRecord": str(start), "maximumRecords": str(n)})
    if r is None:
        return []
    try:
        root = ET.fromstring(r.text)
    except ET.ParseError:
        return []
    recs = []
    for rec in root.iter(f"{_SRW}record"):
        dc = next((e for e in rec.iter() if e.tag == _DC_ELEM), None)
        if dc is None:
            continue

        def vals(tag, _dc=dc):
            return [e.text for e in _dc.findall(f"{_DC}{tag}") if e.text]

        d = {
            "title": (vals("title") or [""])[0],
            "creators": vals("creator"), "dates": vals("date"),
            "descriptions": vals("description"), "ids": vals("identifier"),
            "rights": vals("rights"), "subjects": vals("subject"),
            "publishers": vals("publisher"), "types": vals("type"),
            "formats": vals("format"),
        }
        ark = None
        for i in d["ids"]:
            m = re.search(r"ark:/12148/([0-9a-z]+)", i)
            if m:
                ark = m.group(1)
                break
        d["ark"] = ark
        recs.append(d)
    return recs


def gallica_image_url(ark: str, size: str = "full") -> str:
    return f"https://gallica.bnf.fr/iiif/ark:/12148/{ark}/f1/{size}/full/0/native.jpg"


def gallica_page_url(ark: str) -> str:
    return f"https://gallica.bnf.fr/ark:/12148/{ark}"


# ---------------------------------------------------------------- Internet Archive

def ia_search(query: str, rows: int = 50, page: int = 1, fields=None) -> dict:
    fields = fields or ["identifier", "title", "date", "creator",
                        "licenseurl", "rights", "mediatype", "description"]
    params = [("q", query), ("rows", str(rows)), ("page", str(page)), ("output", "json")]
    for f in fields:
        params.append(("fl[]", f))
    j = _get_json(IA_SEARCH, params=params)
    return j or {}


def ia_metadata(identifier: str) -> dict:
    return _get_json(IA_META + identifier) or {}


# ---------------------------------------------------------------- verification

IMG_MAGIC = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG": "image/png",
             b"GIF8": "image/gif", b"RIFF": "image/webp",
             b"II*\x00": "image/tiff", b"MM\x00*": "image/tiff"}


def check_image(url: str) -> dict:
    r = _get(url, stream=True, min_gap=0.3, retries=4)
    if r is None:
        return {"ok": False, "status": None}
    ct = (r.headers.get("content-type") or "").lower()
    try:
        head = next(r.iter_content(2048))
    except Exception:  # noqa: BLE001
        head = b""
    finally:
        r.close()
    magic = next((n for sig, n in IMG_MAGIC.items() if head.startswith(sig)), None)
    return {"ok": ct.startswith("image") and bool(magic), "status": r.status_code,
            "content_type": ct, "magic": magic, "bytes": len(head)}


def check_page(url: str) -> dict:
    r = _get(url, min_gap=0.5, retries=4)
    if r is None:
        return {"ok": False, "status": None}
    return {"ok": r.status_code == 200, "status": r.status_code,
            "content_type": (r.headers.get("content-type") or "")[:40]}
