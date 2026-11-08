"""INA — Institut national de l'audiovisuel — access reference (mnemosyne research).

Task #160 (phrase yt_la_france_a_du_petrole_mais_elle_la_oublie_20260925_10).
The adversarial resolver asked for a French audiovisual source for a video essay
on "le pétrole français oublié" (Lacq, Parentis-en-Born, Pechelbronn). INA holds
the filmed news / documentaries / radio programmes on French oil. This module is
the reusable, READ-ONLY *reference* the coder turns into ``config/sources/ina.yaml``
and an ``ina`` connector. It performs NO writes, downloads NO media, and NEVER
scrapes an HTML surface that a site's robots.txt forbids.

There are TWO INA surfaces. They are very different in legality — read carefully.

=====================================================================
SURFACE A — catalogue.ina.fr  (Inathèque / OPSIS 3.0.6)  ✅ LAWFUL TO INDEX
=====================================================================
The legal-deposit *catalog* of every programme archived by INA (TV nationale &
régionale, radio, publicités, sources écrites, web-média). Pure BIBLIOGRAPHIC
METADATA + a deep link to the notice. NO media here; the actual recordings are
consulted on-site at Inathèque partner libraries. robots.txt is PERMISSIVE
(only GPTBot / ChatGPT-User blocked) -> an index/build over the notices is OK.

Platform: OPSIS 3.0.6 (Prototype/jQuery app). Server renders HTML; there is NO
JSON/XML API (``&xml_liste=docListe.xml`` is XSL-transformed back to HTML).

SEARCH LIST (GET) — this is the connector's search entry point
    https://catalogue.ina.fr/docListe/{SECTION}/?<query>
    SECTION ∈ {TV-RADIO, ECRIT, WEB-MEDIA}     (TV-RADIO = audiovisual, the one we need)
    Query params (confirmed live 2026-10):
      base_label  comma list of bases to include. For TV-RADIO the full set is
                  TVNAT,RADIO,TVSAT,PUBTV,TVREG,CLIPTV,DLDON
                  (TV Nationale, Radio, TV Satellite & TNT, Messages publicitaires,
                   TV Régionale, Clips, Autres Fonds). Pick a subset to narrow.
      itoustext   free-text query (the "Saisissez un mot clé" field; FT on itoustext)
      sujets_filter=Sujet
      bool_operator=AND
      tri         score1 (relevance, default) | datdif (date ascending).
                  NB: no descending date variant; sort client-side if needed.
                  Undated items default to 01/01/1900 and cluster first under datdif.
      nbLignes   20 | 50 | 100 | 500   (page size)
      page        1-based page number (omitted => page 1)

    Example (verified live, returns 50 rows of real 1950s-2020s oil footage):
      https://catalogue.ina.fr/docListe/TV-RADIO/?base_label=TVNAT,RADIO,TVSAT,PUBTV,TVREG,CLIPTV,DLDON&itoustext=Lacq+pétrole&sujets_filter=Sujet&bool_operator=AND&tri=score1&nbLignes=50&page=1

    Total count is rendered as:  Enregistrements <a> à <b> sur <TOTAL>
    Results are an HTML table ``table.tableau-header-gris``; each data row is
    ``<tr class="result_line_a|result_line_b">`` with <td>s in this order:
      [0] indice | [1] chaîne de diffusion | [2] date de diffusion (DD/MM/YYYY)
      [3] heure (HH:MM:SS:FF) | [4] durée (HH:MM:SS:FF)
      [5] titre propre  -> holds <a href="...">TITRE</a>  (the notice link)
      [6] titre collection | [7] titre programme | [8] genre
    NOTE: cells may be genuinely EMPTY (e.g. chaîne blank / 00:00:00:00 duration
    for some archive/photo notices). That is missing data, not a parse failure —
    keep the raw string or null it, do not crash.
    The notice link is:  https://catalogue.ina.fr/doc/{SECTION}/{DOC_ID}/{slug}
    DOC_ID carries a TYPE prefix, e.g. DA_ / DO_ / RD_ / RE_ / PI_ / PH_ / SXC...
      (DA/DO = Archives TV Pro document, RD = radio doc, RE = reportage,
       PI = pièce/élément, PH = photo, ...). Keep it opaque.

NOTICE DETAIL (GET) — full record for one DOC_ID
    https://catalogue.ina.fr/doc/{SECTION}/{DOC_ID}/{slug}      (?rang=NN harmless, strip it)
    The page is a field table:  <td class="... label_champs_form">LABEL</td>
                                <td id="CODE" class="... val_champs_form">VALUE</td>
    Extract by the *code* (the <td id="CODE">), falling back to the label. The set
    of fields DIFFERS by base; the union observed live (2026-10) is:

      Code     Label (fr)                       Notes / example
      -------  -------------------------------  ----------------------------------
      NO       ID Notice                        AFE85003518 / 913264.001.003
      TI       Titre propre                     "Le pétrole d'Aquitaine"
      TICOL    Titre collection                 "Journal Les Actualités Françaises"
      TIPROG   Titre programme                  "... : émission du 4 mai 1950"
      CH       Chaîne de diffusion              TV/radio channel (e.g. "Radio Bleue",
                                                 "Antenne 2"). Often absent on DA_ presse filmée.
      DATDIF   Date de diffusion                DD/MM/YYYY  -> normalise to ISO
      JOUR     Jour                             weekday
      DATENG   Date d'enregistrement            DD/MM/YYYY (radio)
      STADIF   Statut de diffusion              "Première diffusion"
      HEURE    Heure de diffusion               HH:MM:SS(:FF)
      HEUREFIN Heure de fin de diffusion
      DUREE    Durée                            HH:MM:SS(:FF) -> seconds
      THEMAT   Thématique                       (radio)
      GENRE    Genre                            "Presse filmée", "Magazine", "Journal télévisé"
      TYPDESCR Type de description              "Sujet"
      GEN      Générique                        credits, "FONCTION,Nom ; FONCTION,Nom"
      DE       Descripteurs                     PRIMARY keywords, " ; " separated
      DES      Descripteurs secondaires         EXTRA keywords (TV archive)
      RES      Résumé documentaire              ★ BEST abstract for TV archive (DA_)
      CHAP     Chapeau                          ★ BEST abstract for radio (RD_)
      SEQ      Dispositifs                      shot-by-shot description (TV archive)
      GEO      Extension géographique           "National" / region
      NATPRO   Nature de production             "Production propre"
      SP       Société de programmes
      PROD     Producteurs
      SELDL / DL / FONDS / TIDL                 legal-deposit admin fields
      BASE     Base                             "Archives TV Pro", "Dépôt Légal Radio"

    ⚠ DESCRIPTION unification: the abstract lives in **RES ("Résumé documentaire")**
    for TV-archive notices but in **CHAP ("Chapeau")** for radio notices — read
    ``RES or CHAP`` (in that order) for a single description field.
    ⚠ KEYWORDS: take DE ("Descripteurs") and, when present, append DES
    ("Descripteurs secondaires") — both are " ; " separated.

=====================================================================
SURFACE B — www.ina.fr public clips ("L'INA éclaire l'actu")  ⚠️ RESTRICTED
=====================================================================
The showcase site's streamable clips (with thumbnails). DO NOT SCRAPE/INDEX:
  * robots.txt (www.ina.fr) has ``Disallow: /*q=`` (blocks the search URLs),
    ``Crawl-delay: 5`` and a large AI-bot ``User-agent`` list with ``Disallow: /``.
  * CGU: streaming only — no download / reproduction / reuse.
  * Licensing: "Tous droits réservés © INA". Reuse is commercial via **mediaclip**
    (https://mediaclip.ina.fr/) or **INA mediapro** (https://www.inamediapro.com/).
So Surface B must ship in the descriptor as ``enabled: false`` and be reachable
ONLY by a human looking up a clip, or after WRITTEN permission from mediaclip.
For completeness the mechanism is documented below (reference only, gated by
``public_search_allowed()`` which always returns False):
  AJAX search (HTML cards, 12/pg, ``offset`` paginates):
    https://www.ina.fr/ajax/recherche?q=<q>&media=2&espace=1&offset=N
    media: 1=Articles 2=Vidéos 3=Audios 4=Publicités
  card thumbnail: https://cdn-hub.ina.fr/notice/{360x270|450x450|690x517}/{hash}/{ID}.jpeg
    (the {hash} directory is REQUIRED and NOT derivable from the ID)
  detail page: /ina-eclaire-actu/video/{id}/{slug} with schema.org JSON-LD VideoObject
    {name, description, thumbnailUrl, uploadDate, duration}.

LICENSING / POLICY SUMMARY
    reuse_allowed  = False    (no media download; metadata + deep link only)
    media_download = False
    attribution_required = True   ("Source : INA — Institut national de l'audiovisuel")
    robots_ok_surface_a = True    (catalogue.ina.fr)
    robots_ok_surface_b = False   (www.ina.fr search disallowed)
    api_key_required = False      (open catalogue; nothing in the vault).

The functions below are pure/read-only reference logic (urllib + regex only, no
third-party deps) so they can be lifted almost verbatim into the connector.
"""

from __future__ import annotations

import html as _html
import re
import time
import urllib.parse
import urllib.request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 MnemosyneBot/1.0"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"}

CATALOGUE = "https://catalogue.ina.fr"
PUBLIC = "https://www.ina.fr"

SECTIONS = ("TV-RADIO", "ECRIT", "WEB-MEDIA")
TV_RADIO_BASES = ("TVNAT", "RADIO", "TVSAT", "PUBTV", "TVREG", "CLIPTV", "DLDON")
SORT = {"relevance": "score1", "date_asc": "datdif"}
DEFAULT_NB = 50
PUBLIC_MEDIA = {"articles": 1, "videos": 2, "audios": 3, "ads": 4}

LICENSE = {
    "name": "INA — Institut national de l'audiovisuel",
    "rights": "Tous droits réservés © INA",
    "reuse_allowed": False,          # no media download / reproduction
    "media_download": False,
    "attribution_required": True,
    "attribution_text": "Source : INA — Institut national de l'audiovisuel",
    "reuse_contact": "https://mediaclip.ina.fr/",
    "api_key_required": False,
}

ROBOTS = {
    "surface_a_catalogue": {"disallow": [], "crawl_delay": 5, "indexable": True},
    "surface_b_public": {
        "disallow": ["/*q=", "/"],   # /*q= plus AI-bot Disallow:/
        "crawl_delay": 5,
        "indexable": False,
    },
}

# Field code -> canonical name used by the connector's normaliser.
FIELD_MAP = {
    "NO": "id", "TI": "title", "TICOL": "collection", "TIPROG": "programme",
    "CH": "channel", "DATDIF": "date", "JOUR": "weekday",
    "DATENG": "record_date", "STADIF": "diffusion_status",
    "HEURE": "time", "HEUREFIN": "time_end", "DUREE": "duration",
    "THEMAT": "theme", "GENRE": "genre", "TYPDESCR": "desc_type",
    "GEN": "credits", "DE": "keywords", "DES": "keywords2",
    "RES": "abstract", "CHAP": "abstract", "SEQ": "shotlist",
    "GEO": "geo", "NATPRO": "production_nature", "SP": "program_company",
    "PROD": "producers", "BASE": "base",
}


# --------------------------------------------------------------------------- #
# Surface A — catalogue search
# --------------------------------------------------------------------------- #
def build_search_url(query, section="TV-RADIO", bases=TV_RADIO_BASES,
                     sort="relevance", nb=DEFAULT_NB, page=1):
    """Build a catalogue.ina.fr docListe search URL (Surface A).

    ``query`` is the free text (itoustext). ``sort`` is 'relevance' (score1)
    or 'date_asc' (datdif). ``nb`` ∈ {20,50,100,500}; ``page`` 1-based.
    """
    if section not in SECTIONS:
        raise ValueError(f"section must be one of {SECTIONS}")
    if sort not in SORT:
        raise ValueError(f"sort must be one of {tuple(SORT)}")
    params = {
        "base_label": ",".join(bases),
        "itoustext": query,
        "sujets_filter": "Sujet",
        "bool_operator": "AND",
        "tri": SORT[sort],
        "nbLignes": str(nb),
        "page": str(page),
    }
    qs = urllib.parse.urlencode(params, safe=",")
    return f"{CATALOGUE}/docListe/{section}/?{qs}"


def _strip_tags(s):
    return _html.unescape(re.sub(r"<[^>]+>", " ", s or "")).strip()


def _squash(s):
    return re.sub(r"\s+", " ", _strip_tags(s)).strip()


_TOTAL_RE = re.compile(r"Enregistrements\s+.*?\s+sur\s+([\d\s\u00a0]+)", re.S)
_ROW_RE = re.compile(
    r'<tr class="result_line_[ab]">(.*?)</tr>', re.S | re.I)
_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_HREF_RE = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)


def total_from(page_html):
    """Return the integer total from 'Enregistrements X à Y sur TOTAL'."""
    m = _TOTAL_RE.search(page_html or "")
    if not m:
        return None
    return int(re.sub(r"[^\d]", "", m.group(1)) or 0)


def _parse_rows(page_html, section="TV-RADIO"):
    """Parse the results table into a list of dicts (Surface A list page)."""
    rows = []
    for raw in _ROW_RE.findall(page_html or ""):
        tds = _TD_RE.findall(raw)
        if len(tds) < 6:
            continue
        href = None
        title_html = tds[5]
        m = _HREF_RE.search(title_html)
        if m:
            href = m.group(1)
            title = _squash(m.group(2))
        else:
            title = _squash(title_html)
        if href and href.startswith("/"):
            href = CATALOGUE + href
        doc_id = None
        if href:
            mm = re.search(r"/doc/[^/]+/([^/?#]+)", href)
            if mm:
                doc_id = mm.group(1)
        rows.append({
            "indice": _squash(tds[0]),
            "channel": _squash(tds[1]) or None,
            "date": _squash(tds[2]) or None,
            "time": _squash(tds[3]) or None,
            "duration": _squash(tds[4]) or None,
            "title": title,
            "collection": _squash(tds[6]) if len(tds) > 6 else None,
            "programme": _squash(tds[7]) if len(tds) > 7 else None,
            "genre": _squash(tds[8]) if len(tds) > 8 else None,
            "notice_url": href,
            "doc_id": doc_id,
        })
    return rows


def _fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def search_catalogue(query, section="TV-RADIO", page=1, nb=DEFAULT_NB,
                     sort="relevance", bases=TV_RADIO_BASES, fetch=None):
    """Search the catalogue; returns {'url','total','page','results'}.

    Pass ``fetch=my_http_get`` to reuse the connector's HTTP layer instead of
    urllib. Read-only, single GET.
    """
    url = build_search_url(query, section, bases, sort, nb, page)
    body = (fetch or _fetch)(url)
    return {
        "url": url,
        "section": section,
        "page": page,
        "total": total_from(body),
        "results": _parse_rows(body, section),
    }


def search_all(query, max_pages=5, nb=DEFAULT_NB, sort="relevance",
               section="TV-RADIO", bases=TV_RADIO_BASES, fetch=None,
               crawl_delay=5.0, _sleep=time.sleep):
    """Paginate all result pages, honouring the 5 s crawl-delay. Read-only."""
    out, page, total = [], 1, None
    while page <= max_pages:
        res = search_catalogue(query, section, page, nb, sort, bases, fetch)
        total = res["total"]
        out.extend(res["results"])
        if not res["results"]:
            break
        if total is not None and page * nb >= total:
            break
        page += 1
        _sleep(crawl_delay)   # respect robots.txt Crawl-delay: 5
    return {"query": query, "total": total, "results": out}


# --------------------------------------------------------------------------- #
# Surface A — notice detail
# --------------------------------------------------------------------------- #
_LABEL_ROW_RE = re.compile(
    r'<td[^>]*class="[^"]*label_champs_form[^"]*"[^>]*>(.*?)</td>\s*'
    r'<td[^>]*id="([^"]+)"[^>]*>(.*?)</td>',
    re.S | re.I,
)


def parse_notice(page_html):
    """Parse an OPSIS notice detail page into a dict.

    Returns ``{'by_code': {CODE: value}, 'fields': {canonical: value}}`` where
    ``fields`` uses FIELD_MAP. ``abstract`` reads RES then CHAP; ``keywords``
    joins DE and DES. Robust to missing fields (never raises on a valid page).
    """
    by_code = {}
    for _label_m, code, val_m in _LABEL_ROW_RE.findall(page_html or ""):
        code = (code or "").strip().upper()
        value = _squash(val_m)
        if code:
            by_code[code] = value
    fields = {}
    for code, value in by_code.items():
        canon = FIELD_MAP.get(code)
        if canon and canon not in fields:
            fields[canon] = value
    # description: TV archive -> RES, radio -> CHAP
    abstract = by_code.get("RES") or by_code.get("CHAP") or None
    # keywords: DE primary + (optionally) DES secondary
    kw = [k.strip() for k in re.split(r"\s*;\s*", by_code.get("DE", "")) if k.strip()]
    kw2 = [k.strip() for k in re.split(r"\s*;\s*", by_code.get("DES", "")) if k.strip()]
    return {
        "by_code": by_code,
        "fields": fields,
        "id": by_code.get("NO"),
        "title": by_code.get("TI"),
        "abstract": abstract,
        "keywords": kw,
        "keywords_secondary": kw2,
        "channel": by_code.get("CH"),
        "date": by_code.get("DATDIF"),
        "duration": by_code.get("DUREE"),
        "genre": by_code.get("GENRE"),
    }


def get_notice(doc_url_or_id, section="TV-RADIO", slug=None, fetch=None):
    """Fetch + parse one notice. Accepts a full URL or a bare DOC_ID (+slug)."""
    if doc_url_or_id.startswith("http"):
        url = doc_url_or_id.split("?")[0]
    else:
        url = f"{CATALOGUE}/doc/{section}/{doc_url_or_id}/{slug or ''}".rstrip("/")
    body = (fetch or _fetch)(url)
    data = parse_notice(body)
    data["url"] = url
    return data


# --------------------------------------------------------------------------- #
# Surface B — public clips (RESTRICTED — gated, reference only)
# --------------------------------------------------------------------------- #
def public_search_allowed():
    """Surface B (www.ina.fr clips) is NOT permitted for automated indexing:
    robots.txt Disallow: /*q= + Disallow: / for AI bots, CGU forbid reuse.
    Kept as a hard gate so no caller can accidentally scrape it.
    """
    return False


def search_public_clips(query, media="videos", offset=0, fetch=None):
    """Reference-only (DISABLED) helper for the www.ina.fr AJAX search.

    Raises unless ``public_search_allowed()`` is True (it never is without a
    code change + written permission from mediaclip). Preserved so the coder
    sees the exact endpoint if a permission is ever obtained.
    """
    if not public_search_allowed():
        raise PermissionError(
            "Surface B (www.ina.fr/ajax/recherche) is robots-disallowed "
            "(Disallow: /*q=, Disallow: /) and CGU-restricted; reuse requires "
            "written permission from mediaclip (https://mediaclip.ina.fr/)."
        )
    url = (f"{PUBLIC}/ajax/recherche?q={urllib.parse.quote(query)}"
           f"&media={PUBLIC_MEDIA[media]}&espace=1&offset={offset}")
    return (fetch or _fetch)(url)
