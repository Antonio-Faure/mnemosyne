"""L'Aventure Peugeot Citroën DS — Centre d'Archives de Terre Blanche (reference).

Discovered & verified live by the navigator agent (Archivist, mnemosyne),
2026-11-25. Source demanded by the adversarial resolver (phrase
yt_01grGKLcVOc_30): Rosalie launched 1932; 300 000 km endurance record in
134 days in 1933 at the Linas-Montlhéry autodrome — needs a PERIOD
(1932-1933) press/promotion photograph of a Citroën Rosalie.

Institution : L'Aventure Peugeot Citroën DS (association, musée de Sochaux).
Archive site : Centre d'Archives de Terre Blanche --
               https://www.archives-terreblanche.fr
               (1 rue du Stade, 25310 Hérimoncourt). ~147 763 documents,
               ~72 989 « documents iconographiques » (figuratif: photos,
               affiches, dessins), across Peugeot / Citroën / DS / Poissy.

This module is the reusable, read-only REFERENCE the coder uses to build
`config/sources/citroen_heritage.yaml` (+ connector/tests/doc/PR). It writes
NOTHING remote and NEVER copies/rehosts an image: it returns public image
URLs served by the institution (hotlink) — mnemosyne points at /upload/... .
Plain `requests` + a descriptive bot UA is enough (no JS, no browser, no key).

=====================================================================
ACCESS PATH  (verified 2026-11-25)
=====================================================================
Programmatic access (IIIF / JSON search API / OAI / sitemap / OpenSearch):
ABSENT. Probed and ALL return the Symfony HTML 404:
    /api, /api/, /api/search, /search.json, /oai, /oai?verb=Identify,
    /iiif, /iiif/, /manifest, /sitemap.xml, /robots.txt
The frontend is a server-rendered Symfony app (build/main/*.js) with NO XHR
search endpoint (bundles contain no /api or fetch to a data route). So the
ONLY search surface is the server-rendered HTML — parse it to DISCOVER items;
the image itself is a direct public asset.

robots.txt -> 404 (none published) => no crawl restriction declared; we still
crawl politely: descriptive UA, small pacing (_PACE), iconographic subset only.

Anti-bot: NONE. `requests` + UA "mnemosyne-research-bot/1.0" gets the real page
(HTTP 200, results present). Images (/upload/documents/*.jpg) answer 200
image/jpeg to the bot UA, with or without a Referer, no cookie. Public access
confirmed (item pages + images load with no login).

RIGHTS: per-item there is no license field. The site's « Mentions légales »
reserve reproduction ("toute reproduction, représentation, utilisation ... ")
=> known rights = « Tous droits réservés » (L'Aventure Peugeot Citroën DS /
Centre d'Archives de Terre Blanche). Same posture as la_contemporaine.py:
mnemosyne hotlinks the public image + shows metadata + links the item page,
never copies/rehosts. Record this in the descriptor's rights field.

=====================================================================
1) SEARCH  (HTML, GET)  — the discovery surface
=====================================================================
    https://www.archives-terreblanche.fr/recherche
      ?search[search]=<query>             free text (AND semantics)
      &search[groupTypeElement]=1         only "Documents iconographiques"
                                          (figuratif = photos/affiches/
                                           dessins; use 1 so hits can have
                                           an image)
      &search[societe]=<exact option>     e.g. "3. Citroën / Automobiles Citroën"
      &search[theme]=<exact option>       optional theme filter
      &search[dateDebut][from]=1932-01-01  item START-date range (yyyy-mm-dd)
      &search[dateDebut][to]=1933-12-31
      &search[dateFin][from]=.. &[to]=..   item END-date range
      &page=<N>                            1-based pagination, 20 results/page
groupTypeElement enum: 1=Documents iconographiques, 2=techniques, 3=textuels,
   4=vidéos, 5=objets.  (Use 1 for image search.)
NOTE: the date filter keys on the item's START date, so an item catalogued
   "1928-1933" is EXCLUDED if you ask dateDebut[from]=1932. To capture
   multi-year period items, search by free text and read the dates rather
   than over-constraining the date filter.

=====================================================================
2) RESULT CARD  (one per `div.result`)  — parse with BeautifulSoup
=====================================================================
Each `div.container.result` holds:
    a[href^="/archive/"]        -> item id + page url (/archive/<id>)
    .result__type               -> type label (Document figuré et icono...)
    .result__description        -> title / description text
    .result__dates              -> date range text
    .result__col--image img     -> tiny 89x120 thumbnail IFF digitized
    .result__error              -> "Cette archive n'a pas encore été
                                   numérisée !" IFF NOT digitized (no <img>)
=> A card is USABLE only if it has an <img> and no .result__error.

=====================================================================
3) ITEM PAGE  (https://www.archives-terreblanche.fr/archive/<id>)
=====================================================================
    img#big-image               -> src = full scan
                                   /upload/documents/<id-hash>.jpg
                                   (~714x960, 0.5-0.6 MB; the image to
                                    display -- NOT the search thumb)
    .archive__details > div     -> each div = <p>LABEL</p><p>VALUE</p>
        labels: Description, Période, Type de document, Auteur, Theme,
                Société, Référence du document (e.g. PI2017FIG-02585)
An item whose body contains "pas encore été numérisée" has NO image
(no img#big-image) -> not digitized, skip it.

=====================================================================
VERIFICATION — PERIOD (1932-1933) Rosalie imagery present (2026-11-25)
=====================================================================
- figuratif "Rosalie", start-date 1928-1934: 548 items, 544 digitized (99%).
- figuratif "record Montlhéry" 1928-1936: p.1 = 11/20 digitized, real period
  photos: "Records, Eyston sur la 35CV des records à Montlhéry" (1932 & 1934),
  Boillot/Miramas 301 24h (1932), etc.
- Samples verified end-to-end (metadata + image 200 image/jpeg):
    92058  / PI2017FIG-02585 / 1934      / "ROSALIE 8 « des records » affiche"
    56110  / PI2013FIG-02458 / 1933      / "Championnat féminin Montlhéry 301."
    115753 / PI2019FIG-01349 / 1928-1933 / "... prises de vues avec une Rosalie"
    142471 / PI2024FIG-01686 / 1930      / "Rosalie entretenue par un agent..."
CAVEAT: the single item titled exactly "Records de la Rosalie Citroën à
  Montlhéry" = id 18779 / PI2010FIG-06201 / 1933 is NOT digitized (no image),
  and "Dessin d'une Petite Rosalie bleue" id 49001 / PI2010FIG-00029 is NOT
  digitized. The phrase is nonetheless well-covered by many digitized period
  Rosalie/Montlhéry photos (above). Report this caveat to the resolver team.
"""

import re
import time
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

BASE = "https://www.archives-terreblanche.fr"
UA = "mnemosyne-research-bot/1.0 (+https://github.com/Antonio-Faure/mnemosyne)"
HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}
RIGHT_TEXT = (
    "Tous droits réservés (L'Aventure Peugeot Citroën DS / "
    "Centre d'Archives de Terre Blanche)"
)
_PACE = 0.4  # seconds between requests (politeness)


def _clean(text):
    """Collapse whitespace; return None for empty."""
    if text is None:
        return None
    return " ".join(text.split()).strip() or None


def _get(url, *, tries=3, timeout=30):
    """GET with a descriptive UA and small retry/pacing."""
    last = None
    for attempt in range(tries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code == 200:
                return resp
            last = resp
        except requests.RequestException as exc:  # pragma: no cover
            last = exc
        time.sleep(_PACE * (attempt + 1))
    if isinstance(last, requests.Response):
        last.raise_for_status()
    raise RuntimeError(f"GET failed: {url} ({last!r})")


def build_search_url(query="", page=1, type_element=1, societe=None,
                     theme=None, date_debut_from=None, date_debut_to=None,
                     date_fin_from=None, date_fin_to=None, **extra):
    """Build a /recherche URL. type_element=1 -> iconographic docs only."""
    params = {}
    if query:
        params["search[search]"] = query
    if type_element is not None:
        params["search[groupTypeElement]"] = str(type_element)
    if societe:
        params["search[societe]"] = societe
    if theme:
        params["search[theme]"] = theme
    if date_debut_from:
        params["search[dateDebut][from]"] = date_debut_from
    if date_debut_to:
        params["search[dateDebut][to]"] = date_debut_to
    if date_fin_from:
        params["search[dateFin][from]"] = date_fin_from
    if date_fin_to:
        params["search[dateFin][to]"] = date_fin_to
    for key, val in extra.items():
        params["search[" + key + "]"] = str(val)
    if page and page > 1:
        params["page"] = str(page)
    return BASE + "/recherche?" + urlencode(params)


def _text(node, selector):
    """Return the stripped text of the first match, or None."""
    found = node.select_one(selector)
    return found.get_text(" ", strip=True) if found else None


def parse_results(html):
    """Parse a /recherche HTML page -> list of result dicts."""
    soup = BeautifulSoup(html, "lxml")
    items = []
    for card in soup.select("div.result"):
        link = card.select_one('a[href^="/archive/"]')
        if not link:
            continue
        href = link.get("href", "")
        match = re.search(r"/archive/(\d+)", href)
        img = card.select_one(".result__col--image img")
        err = card.select_one(".result__error")
        thumb = img.get("src") if img else None
        if thumb and thumb.startswith("/"):
            thumb = BASE + thumb
        items.append({
            "id": match.group(1) if match else None,
            "page_url": BASE + href if href.startswith("/") else href,
            "type": _clean(_text(card, ".result__type")),
            "description": _clean(_text(card, ".result__description")),
            "dates": _clean(_text(card, ".result__dates")),
            "digitized": bool(img) and not err,
            "thumb": thumb,
        })
    return items


def search(query="", page=1, **kwargs):
    """Run one search page -> {'url', 'page', 'count', 'items'}."""
    url = build_search_url(query=query, page=page, **kwargs)
    resp = _get(url)
    items = parse_results(resp.text)
    return {"url": url, "page": page, "count": len(items), "items": items}


def fetch_item(archive_id):
    """Fetch an item page -> full record (image_url None if not digitized)."""
    archive_id = str(archive_id)
    url = BASE + "/archive/" + archive_id
    resp = _get(url)
    soup = BeautifulSoup(resp.text, "lxml")
    body = soup.get_text(" ", strip=True)
    digitized = ("pas encore été numérisée" not in body
                 and "pas encore été numérisé" not in body)
    big = soup.select_one("img#big-image")
    image_url = big.get("src") if big else None
    if image_url and image_url.startswith("/"):
        image_url = BASE + image_url
    if not image_url:
        digitized = False

    details = {}
    for div in soup.select(".archive__details > div"):
        ps = div.find_all("p")
        if len(ps) >= 2:
            label = _clean(ps[0].get_text(" ", strip=True))
            value = _clean(ps[1].get_text(" ", strip=True))
            if label:
                details[label] = value

    title = _clean(_text(soup, "h1")) or details.get("Description")
    return {
        "id": archive_id,
        "page_url": url,
        "digitized": digitized and bool(image_url),
        "image_url": image_url,
        "title": title,
        "reference": details.get("Référence du document"),
        "description": details.get("Description"),
        "periode": details.get("Période"),
        "type_document": details.get("Type de document"),
        "auteur": details.get("Auteur"),
        "theme": details.get("Theme"),
        "societe": details.get("Société"),
        "rights": RIGHT_TEXT,
        "details": details,
    }


def resolve(query, max_items=10, page=1, *, include_undigitized=False, **kwargs):
    """Search + expand digitized items into full hotlinkable records."""
    res = search(query=query, page=page, **kwargs)
    out = []
    for item in res["items"]:
        if not item["id"]:
            continue
        if not item["digitized"] and not include_undigitized:
            continue
        record = fetch_item(item["id"])
        if record["digitized"] or include_undigitized:
            record["dates"] = item.get("dates")
            out.append(record)
        if len(out) >= max_items:
            break
        time.sleep(_PACE)
    return out


if __name__ == "__main__":
    demo = resolve(
        "Rosalie",
        max_items=5,
        date_debut_from="1928-01-01",
        date_debut_to="1934-12-31",
    )
    print("resolved:", len(demo))
    for rec in demo:
        print("-", rec["id"], "|", rec["periode"], "|", rec["description"])
        print("  img:", rec["image_url"])
