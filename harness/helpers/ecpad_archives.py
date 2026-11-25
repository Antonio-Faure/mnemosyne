"""ECPAD — Archives photographiques et audiovisuelles de la Défense (reference).

Discovered and verified live by the navigator agent (mnemosyne), 2026-11.
Source wanted by the adversarial resolver (phrase yt_01grGKLcVOc_13): war
industry / shell (obus) production in France 1914-1918 — the Citroën Javel
works producing 15 000 -> 55 000 shells/day. ECPAD (heir of the army's
Section photographique/cinématographique de l'armée, created 1915) holds and
digitises WWI photographic fonds INCLUDING war industry.

This module is the reusable, read-only *reference* the coder uses to build
`config/sources/ecpad.yaml` and its connector. It performs NO writes and
NEVER re-hosts a copy of an image: image bytes are pulled only from the open
IIIF Image API (v2, level2). Public HTML is parsed only to *discover* metadata
and IIIF identifiers (same posture as ligeo_archives.py).

=====================================================================
PLATFORM
=====================================================================
Arkothèque ("Arko") — a Symfony front (`/_recherche-api/*` JSON endpoints)
over an Elasticsearch search, plus a per-image IIIF Image API v2 server.
Frontend .......... https://archives.ecpad.fr
Search API ....... https://archives.ecpad.fr/_recherche-api/...   (JSON, NO auth)
IIIF Image API ... https://archives.ecpad.fr/iiif/2/<id>/...      (NO auth)
ARK .............. NAAN 39674, path /ark:39674/<hash>/<page>/<pos>
Catalog size ..... ~598 679 records (moteur "Ressources").

Everything below answers ANY User-Agent (verified with a generic research-bot
UA via `requests`, NO cookie, NO key, NO CORS origin needed). Plain-HTTP GET
works; no JS execution, no browser required.

=====================================================================
1) SEARCH  (JSON)  ->  GET /_recherche-api/search/2
=====================================================================
`2` is the moteur id. The whole query travels in bracket-notation query params
prefixed by the moteur refUnique. Free text is a single "groupe" keyed by the
*filter* refUnique arko_default_6989dceb6d3b8 ("Recherche libre"); its value
goes in [q][]. Verified URL for q="obus":

  /_recherche-api/search/2
    ?arko_default_6989dacfef00f--filtreGroupes[mode]=simple
    &arko_default_6989dacfef00f--filtreGroupes[op]=AND
    &...--filtreGroupes[groupes][0][arko_default_6989dceb6d3b8][op]=AND
    &...--filtreGroupes[groupes][0][arko_default_6989dceb6d3b8][q][]=obus
    &...--filtreGroupes[groupes][0][arko_default_6989dceb6d3b8][extras][mode]=input
    &arko_default_6989dacfef00f--from=0                    (offset, pagination)
    &arko_default_6989dacfef00f--resultSize=25             (25 | 50 | 100)
    &arko_default_6989dacfef00f--modeRestit=arko_default_6989e72c9ac2c  (Mosaïque)
    &arko_default_6989dacfef00f--searchMode=strict         (strict = all words)

(The `&...` above is shorthand for the full
`&arko_default_6989dacfef00f` prefix — build_search_url() emits the exact
keys, don't hand-copy.)

Response (application/json):
  {total:int, count:int, results:[stub...], html:str, aggregations:[...],
   queryAggregations:{...}, searchMode, modeRestit, timestamp}
  - results[i] = {id:<idFiche>, intitule:<reference e.g. "SPA 42 B 3332">,
                  refUnique:<arko_fiche_...>, hasChildren, parent, arbre, ...}
  - html  = the rendered Mosaïque cards (see §2) — parse for per-card fields.
  - aggregations = Elasticsearch facets (période, personnes, date min/max...).
  Pagination verified: from=0 vs from=25 return different first ids.

Moteur refUnique .......... arko_default_6989dacfef00f
Mode "Mosaïque" .......... arko_default_6989e72c9ac2c  (Tableau = 69c16081cc0ec)
Free-search filter ....... arko_default_6989dceb6d3b8  (the groupes[] KEY)
Free-search FIELD ........ arko_default_6989d75b027f9  (the indexed field)

Other facet filters (filter refUnique -> its field(s)):
  Photographie ou vidéo    arko_default_6989f16835299
                           (field arko_default_6989f11768f43)
  Visuel en ligne          arko_default_69d51ed5efc04
                           (field arko_default_69d51e46f0678)
  Recherche dans le titre  arko_default_6989dceb75d4a
                           (field arko_default_698454efaa336)
  Date                     arko_default_6989e69505787
                           (fields 6989d71becb13, 6984557e18de3)
  Auteur                   arko_default_6989dceb7caec
                           (fields 6989d874a260b, 6989d72e6cffe)
  Lieu                     arko_default_6989dceb89b72
                           (fields 6989d73f54c7a, 6989d8b682c1a)
  Personnes représentées   arko_default_6989dceb95912
                           (field arko_default_6989d74708a3c)

=====================================================================
2) SEARCH  HTML cards  (parse for a LEAN single-request path)
=====================================================================
The search response's `html` string is the already-rendered Mosaïque grid.
Each card carries, for one record:
  - the reference (cote) text,
  - the IIIF image id in an <img src="/iiif/2/<id>/...">,
  - `detail=<idFiche>` in the permalink (<a href=...?detail=NNN>),
  - data-visionneuse="refUniqueFiche=...&idArkoFile=..."
So a lean connector can map title/reference/IIIF-thumb + record link from the
search response ALONE. Use fetch_detail() only when author/date/place/rights
must be exact per record.

=====================================================================
3) PER-RECORD DETAIL  (JSON)  ->  GET /_recherche-api/render-fiche/...
=====================================================================
  GET /_recherche-api/render-fiche/{moteur}/{refUniqueFiche}/{modeRestit}/detail
Response: {"html": "<dl>...</dl>"}. Parse with data-champ="..." and <dt>/<dd>:
  data-champ="titre"        -> title
  data-champ="leginternet"  -> description
  data-champ="reference"    -> cote/reference (e.g. "SPA 131 M 2716")
  data-champ="lieu"         -> place
  data-champ="copyright"    -> rights / mention obligatoire (e.g.
                               "© Albert Moreau/ECPAD/Défense")
  data-champ="origine"      -> fonds (e.g. "SPA/SPCA")
  data-champ="motcle"       -> keyword(s) (e.g. "Munition (fonction)")
  <dt>Date de début</dt>/<dd>       -> start date (e.g. 26/10/1916)
  <dt>Date de fin</dt>/<dd>         -> end date
  <dt>Photographe(s)</dt>/<dd>      -> author (e.g. "Moreau, Albert")
  <dt>Mention obligatoire</dt>/<dd> -> rights mention

Alt JSON detail (handy — returns IIIF id + info.json + ARK + caption in one
object, no HTML parse needed):
  GET /_recherche-api/visionneuse-infos/{moteur}/{refUniqueFiche}/{field}/image/{idArkoFile}

=====================================================================
4) IIIF Image API v2  (the ONLY image source — never copied/rehosted)
=====================================================================
  info     https://archives.ecpad.fr/iiif/2/<id>/info.json
  thumb    /iiif/2/<id>/full/!400,400/0/default.jpg   (~22 KB jpeg)
  full     /iiif/2/<id>/full/max/0/default.jpg
  square   /iiif/2/<id>/square/200,/0/default.jpg
Profile = level2 (regionByPx, sizeByW/Wh/Pct, rotation, etc.).

IIIF id = "v1." + base64url_NOPAD({"type":"record","fiche":<idFiche>,
                                   "image":<idArkoFile>,"pos":0})
  -> NO padding (padded id 404s). Example id for record 607892:
     v1.eyJ0eXBlIjoicmVjb3JkIiwiZmljaGUiOjYwNzg5MiwiaW1hZ2UiOjU3MzI0MCwicG9zIjowfQ
The id is also present in the card HTML and the detail JSON, so there is no
need to recompute it if you parse the HTML.
NOTE: no IIIF Presentation manifest (iiifManifestUrl = null) -> images come
from the Image API directly.

=====================================================================
5) RECORD PERMALINK / ARK
=====================================================================
Permalink  https://archives.ecpad.fr/archives/consulter-les-archives-en-ligne?detail=<idFiche>
ARK NAAN 39674, path /ark:39674/<hash>/<page>/<pos> resolves (302->200) to
the same page.

=====================================================================
6) RIGHTS  (display verbatim, never reinterpret)
=====================================================================
Per-record rights = "Mention obligatoire" (e.g. "© <author>/ECPAD/Défense",
"© ECPAD/fonds .../..."). Copy it VERBATIM into the item's `rights` field.
Global reuse notice shown site-wide:
  "Toute réutilisation ou diffusion des archives est soumise à autorisation
   préalable."
Mnemosyne only shows metadata + a link + a IIIF thumbnail pointing back to
ECPAD; it copies nothing, hosts nothing, redistributes nothing.

=====================================================================
7) COVERAGE PROOF  (WWI war-industry gap — verified live)
=====================================================================
Totals (free search): "Citroën" 595, "obus" 6171, "usine de guerre" 5135,
"obus usine" 502, "fabrique d'obus" 70, "usine de guerre munitions" 436.
Dated samples (title | place | date | author | rights | idFiche):
  - "Mission ... en visite aux usines Citroën ... emprunt" | Paris | 26/10/1916
    | Moreau, Albert | © Albert Moreau/ECPAD/Défense | 607892  [kw Munition]
  - "Ex exposition de Lyon - Fabrique d'obus" | Lyon | 01/01/1915
    | Bertrand, Georges | © ECPAD/fonds Georges Bertrand/... | 559106
  - "Saint-Chamond ... outils pour le forgeage ... des obus" | Rhône-Alpes
    | 14/01/1916 | Aubert, Isidore | © Isidore Aubert/ECPAD/Défense | 666852
  - "Lyon - Sortie de la fabrique des munitions (I)" | Lyon | 01/01/1915
    | Bertrand, Georges | © ECPAD/fonds Georges Bertrand/... | 559104
  - "Cartoucherie de Vincennes. Recuit partiel des étuis" | Paris-IdF
    | 15/07/1915 | Aubert, Isidore | © Isidore Aubert/ECPAD/Défense | 665815

=====================================================================
DEONTOLOGY
=====================================================================
No auth bypass, no Cloudflare/WAF circumvention, no proxy/mirror/rehosting.
This is documented OPEN access (JSON + IIIF), fetched with a plain bot UA.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.parse
from typing import Any

import requests

BASE = "https://archives.ecpad.fr"
SEARCH_PATH = "/_recherche-api/search/2"
DETAIL_PATH = "/_recherche-api/render-fiche/{moteur}/{fiche}/{mode}/detail"
IIIF_PATH = "/iiif/2/{iid}/{region}/{size}/{rot}/{quality}.jpg"
INFO_PATH = "/iiif/2/{iid}/info.json"
PERMALINK = ("https://archives.ecpad.fr/archives/"
             "consulter-les-archives-en-ligne?detail={fiche}")

MOTEUR = "arko_default_6989dacfef00f"
MODE_RESTIT = "arko_default_6989e72c9ac2c"        # Mosaïque
FREE_SEARCH_FILTER = "arko_default_6989dceb6d3b8"  # the groupes[] KEY

UA = "Mozilla/5.0 (compatible; mnemosyne-research-bot; +github.com/Antonio-Faure/mnemosyne)"
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}


# ---------------------------------------------------------------------------
# IIIF id helpers
# ---------------------------------------------------------------------------
def iiif_id(fiche: int | str, image: int | str, pos: int = 0) -> str:
    """Build the IIIF Image API id for one record image (NO base64 padding)."""
    payload = json.dumps(
        {"type": "record", "fiche": int(fiche), "image": int(image), "pos": int(pos)},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    token = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return "v1." + token


def decode_iiif_id(iid: str) -> dict[str, Any]:
    """Inverse of iiif_id(): recover {type, fiche, image, pos} from an id."""
    body = iid[3:] if iid.startswith("v1.") else iid
    pad = "=" * (-len(body) % 4)
    return json.loads(base64.urlsafe_b64decode(body + pad).decode("utf-8"))


def iiif_urls(iid: str) -> dict[str, str]:
    """Return the four standard IIIF v2 URLs for an image id."""
    def u(region: str, size: str) -> str:
        return BASE + IIIF_PATH.format(
            iid=iid, region=region, size=size, rot=0, quality="default"
        )
    return {
        "info": BASE + INFO_PATH.format(iid=iid),
        "thumb": u("full", "!400,400"),
        "full": u("full", "max"),
        "square": u("square", "200"),
    }


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def build_search_url(
    query: str, offset: int = 0, size: int = 25, strict: bool = True
) -> str:
    """Build the Arkothèque search URL for a free-text query."""
    m = MOTEUR
    g = f"{m}--filtreGroupes[groupes][0][{FREE_SEARCH_FILTER}]"
    params = [
        (f"{m}--filtreGroupes[mode]", "simple"),
        (f"{m}--filtreGroupes[op]", "AND"),
        (f"{g}[op]", "AND"),
        (f"{g}[q][]", query),
        (f"{g}[extras][mode]", "input"),
        (f"{m}--from", str(offset)),
        (f"{m}--resultSize", str(size)),
        (f"{m}--modeRestit", MODE_RESTIT),
        (f"{m}--searchMode", "strict" if strict else "large"),
    ]
    return BASE + SEARCH_PATH + "?" + urllib.parse.urlencode(params)


def search(query: str, offset: int = 0, size: int = 25, strict: bool = True,
           session: requests.Session | None = None) -> dict[str, Any]:
    """Run one search page; returns the parsed JSON (total/count/results/html)."""
    s = session or requests
    r = s.get(build_search_url(query, offset, size, strict),
              headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def parse_cards(html: str) -> list[dict[str, Any]]:
    """Extract lean per-card data from the search HTML (no per-record call).

    Each returned dict: {iiif_id, detail_id}. Pairing is best effort by order;
    use fetch_detail() for guaranteed per-record metadata.
    """
    iiif_ids = re.findall(r'/iiif/2/([^/"?]+)/', html)
    detail_ids = re.findall(r"detail=(\d+)", html)
    out: list[dict[str, Any]] = []
    for i, iid in enumerate(iiif_ids):
        out.append({
            "iiif_id": iid,
            "detail_id": detail_ids[i] if i < len(detail_ids) else None,
        })
    return out


# ---------------------------------------------------------------------------
# Per-record detail (metadata + rights)
# ---------------------------------------------------------------------------
def _field(html: str, name: str) -> str | None:
    pattern = rf'data-champ="{re.escape(name)}"[^>]*>(.*?)</'
    m = re.search(pattern, html, re.S)
    return _clean(m.group(1)) if m else None


def _dt(html: str, label: str) -> str | None:
    pattern = rf"<dt[^>]*>\s*{re.escape(label)}\s*</dt>\s*<dd[^>]*>(.*?)</dd>"
    m = re.search(pattern, html, re.S)
    return _clean(m.group(1)) if m else None


def _clean(fragment: str) -> str:
    txt = re.sub(r"<[^>]+>", " ", fragment)
    txt = txt.replace("&amp;", "&").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", txt).strip()


def fetch_detail(ref_unique_fiche: str, id_fiche: int | str,
                 session: requests.Session | None = None) -> dict[str, Any]:
    """Fetch and parse one record's detail into a normalised dict."""
    s = session or requests
    url = BASE + DETAIL_PATH.format(
        moteur=MOTEUR, fiche=ref_unique_fiche, mode=MODE_RESTIT
    )
    r = s.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    html = r.json().get("html", "")
    return {
        "id_fiche": str(id_fiche),
        "reference": _field(html, "reference"),
        "title": _field(html, "titre"),
        "description": _field(html, "leginternet"),
        "place": _field(html, "lieu"),
        "rights": _field(html, "copyright"),
        "fonds": _field(html, "origine"),
        "keyword": _field(html, "motcle"),
        "date_start": _dt(html, "Date de début"),
        "date_end": _dt(html, "Date de fin"),
        "author": _dt(html, "Photographe(s)"),
        "rights_mention": _dt(html, "Mention obligatoire"),
        "pipe_url": PERMALINK.format(fiche=id_fiche),
    }


def enrich(query: str, offset: int = 0, size: int = 25,
           session: requests.Session | None = None) -> list[dict[str, Any]]:
    """Search then fetch full detail per record. Convenience helper.

    Prefer the lean path (search -> parse_cards) for latency-sensitive use and
    reserve enrich() for when exact per-record author/date/place/rights matter.
    """
    s = session or requests.Session()
    data = search(query, offset, size, session=s)
    items: list[dict[str, Any]] = []
    for res in data.get("results", []):
        items.append(fetch_detail(res["refUnique"], res["id"], session=s))
    return items


# ---------------------------------------------------------------------------
# Self-test (python -m harness.helpers.ecpad_archives, or run this file)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    q = "Citroën obus usine"
    print("search url:", build_search_url(q, 0, 3))
    d = search(q, 0, 3)
    print("  total:", d.get("total"), "count:", d.get("count"))
    for res in d.get("results", [])[:3]:
        print("  -", res.get("intitule"), "| id", res.get("id"))
    cards = parse_cards(d.get("html", ""))
    if cards:
        print("  cards parsed:", len(cards), "first iiif:", cards[0]["iiif_id"])
        print("  iiif urls:", iiif_urls(cards[0]["iiif_id"]))
    first = d["results"][0]
    det = fetch_detail(first["refUnique"], first["id"])
    print("  detail title:", det["title"])
    print("  date:", det["date_start"], "| author:", det["author"],
          "| rights:", det["rights"])
    print("  permalink:", det["pipe_url"])
