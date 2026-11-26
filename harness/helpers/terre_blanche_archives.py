"""Centre d'archives de Terre Blanche — Conservatoire Citroën heritage (reference).

Source requested by the adversarial resolver (phrase yt_01grGKLcVOc_54):
SOVAC — the credit-sales company created by Citroën (1920s-30s). No current
Mnemosyne source (Wikimedia, Europeana, Paris Musées, Gallica photo agencies,
ANMT, Rijksmuseum) holds epoch Citroën/SOVAC imagery: queries only return
books/periodicals (coverage gap). The manufacturer's own heritage collection is
the specific (company / factory-level) source for factory, dealership,
advertising and credit-sale documents of the period.

WHERE IT LIVES NOW — the Conservatoire Citroën (Aulnay-sous-Bois) closed on
30 June 2024; the Citroën & DS collections are managed by the association
"L'Aventure Peugeot Citroën DS" / "Fonds de dotation Peugeot pour la mémoire de
l'histoire industrielle". The online catalogue of that heritage archive is:

    Centre d'archives de Terre Blanche  —  https://www.archives-terreblanche.fr
    1 rue du Stade, 25310 Hérimoncourt (France)

(The old host archives-laventurepeugeotcitroends.com now redirects here; its old
/fr/... search routes 404. The task's API/docs URL
https://www.stellantis.com/en/heritage also 404s; Stellantis only links a
corporate/financial "FCA | PSA Archives" page — no image catalogue.)

This module is the reusable READ-ONLY *reference* the coder uses to build a
source descriptor + connector. It performs NO writes and NEVER re-hosts an
image copy.

=====================================================================
STATUS  (verified live 2026-11, re-verified on creation)
=====================================================================
PUBLIC HTML COLLECTION — NO PROGRAMMATIC API.  The catalogue is a public,
server-rendered HTML web app (Symfony, built by agency WEB&DESIGN; Matomo
analytics). Verified ABSENT / not usable:
  - /robots.txt /sitemap.xml           -> 404
  - /api, /api/search                  -> 404
  - /oai, /oai-pmh                     -> 404   (no OAI-PMH)
  - /iiif/...                          -> 404   (images are NOT IIIF)
  - /archive/<id>.json                 -> HTTP 500 (Symfony format suffix throws)
  - Accept: application/json           -> still text/html (no negotiation)
  - no JSON / RSS / OpenSearch search endpoint: results are server-rendered HTML
=> There is NO programmatic endpoint. Only HTML pages + direct JPEGs.

=====================================================================
RELEVANCE TO THE SOVAC GAP  (why this source matters)
=====================================================================
The collection is directly relevant to the period, unlike the current sources:
  - search Citroën + groupTypeElement=1 (iconographique) + dates 1920..1939
    -> 28 records  (re-verified). Several are digitised, e.g.:
        /archive/142471  affiche 1930 "services-forfaits de graissage" (has image)
        /archive/11126   "Traction avant Citroën" 1934        (2 images)
        /archive/17178, /archive/17179  Traction Avant 1930-1939 (digitised)
        /archive/11661, /archive/11662, /archive/15391 ... (see search)
  - era-relevant but NOT yet digitised (no image, container records):
        /archive/75971   "Autochenilles Citroën : photographies" 1915-1937
        /archive/66404   "La Croisière Jaune"
        /archive/76921   "André Citroën : portrait" 1928
  - SOVAC: search=SOVAC -> 3 textual dossiers (1981-1997), none digitised.
Overall scale: ~72 989 documents iconographiques, ~14 658 techniques,
~45 822 textuels, ~12 613 vidéo, ~622 objets.

=====================================================================
RIGHTS  (CRITICAL — blocks an unattended connector)
=====================================================================
/mentions-legales states photographs/models/trademarks are protected and that
"toute reproduction, représentation, utilisation ... [est] interdite", plus:
"Il est formellement interdit de copier ou reproduire le Site ou toute partie
du Site ... Pour être autorisé à utiliser le contenu du site Internet, merci
d'adresser votre demande à archives-avpcd@laventureassociation.com".
=> Reserved rights + an EXPLICIT "request authorisation before using content"
   clause. Contact for content use: archives-avpcd@laventureassociation.com
   (MX verified = Microsoft 365, deliverable). General contact:
   contact-avpcd@laventureassociation.com. /contact is only a web form.
Not in data.gouv.fr / FranceArchives / Europeana.

=====================================================================
RECOMMENDATION  (for the coder)
=====================================================================
1) A normal (API/IIIF) connector is NOT possible: there is no programmatic
   endpoint, and the Terms require written authorisation before using the
   content. So do NOT ship an unattended HTML scraper of this site yet.
2) Correct first step = OUTREACH: ask whether a programmatic access is possible
   (API/IIIF/OAI/export) OR whether automatic reading of the public pages is
   authorised. Email target: archives-avpcd@laventureassociation.com.
   (Outreach email/forms require operator validation before sending.)
3) If/once authorised, a connector can search via build_search_url(...) and, for
   each digitised /archive/<id> card, read only the metadata (Description,
   Période, Type de document, Auteur, Thème, Société, Référence) and link to the
   item page — no image copy, no re-host. Images are plain JPEGs under
   /upload/documents/<hash>.jpg (hotlinkable, but do not copy per Terms).

=====================================================================
1) SEARCH  (HTML, GET)  ->  discovery surface
=====================================================================
    GET https://www.archives-terreblanche.fr/recherche
        ?search[search]=<query>              free text
        &search[groupTypeElement]=<1..5>     element-type group (see GROUP_TYPES)
        &search[societe]=<id>                company facet   (optional)
        &search[theme]=<id>                  theme facet      (optional)
        &search[dateDebut][from]=YYYY-MM-DD  &search[dateDebut][to]=...
        &search[dateFin][from]=YYYY-MM-DD    &search[dateFin][to]=...
        &page=<n>                            1-based pagination (~20/page)

  Each result card is a[href^="/archive/"]. Digitised cards carry a thumbnail
  <img> under /upload/...; non-digitised cards instead show the text
  "Cette archive n'a pas encore été numérisée !".
  Result count line: "N archives correspondent à votre recherche".

2) ITEM  (HTML, GET)  ->  metadata + image
=====================================================================
    GET https://www.archives-terreblanche.fr/archive/<id>
  Metadata fields: Description, Période, Type de document, Auteur (sometimes),
  Thème, Société, Référence du document (e.g. PI2024FIG-01686, DOS2016FIG-00090).
  Record kinds: "Dossier..." (container, often no own image) vs
  "...Figuratif / Pièce..." (individual, usually has an image).

3) IMAGES
=====================================================================
  Direct JPEGs, not IIIF:  https://www.archives-terreblanche.fr/upload/documents/<hash>.jpg
  (HEAD -> 200 image/jpeg, hotlinkable). Many records are not digitised yet.

=====================================================================
PURE FUNCTIONS (no network, safe to import)
=====================================================================
"""

from urllib.parse import quote

BASE = "https://www.archives-terreblanche.fr"

# groupTypeElement -> label (verified counts in comments)
GROUP_TYPES = {
    1: "Documents iconographiques",   # ~72 989
    2: "Documents techniques",        # ~14 658
    3: "Documents textuels",          # ~45 822
    4: "Documents video",             # ~12 613
    5: "Objets",                      # ~622
}


def build_search_url(query="", group=None, societe=None, theme=None,
                     date_debut_from=None, date_debut_to=None,
                     date_fin_from=None, date_fin_to=None, page=None):
    """Build a /recherche HTML URL. Brackets are percent-encoded (%5B/%5D),
    which the server accepts. Only provided params are included."""
    params = []
    if query:
        params.append(("search[search]", query))
    if group is not None:
        params.append(("search[groupTypeElement]", str(group)))
    if societe is not None:
        params.append(("search[societe]", str(societe)))
    if theme is not None:
        params.append(("search[theme]", str(theme)))
    if date_debut_from:
        params.append(("search[dateDebut][from]", date_debut_from))
    if date_debut_to:
        params.append(("search[dateDebut][to]", date_debut_to))
    if date_fin_from:
        params.append(("search[dateFin][from]", date_fin_from))
    if date_fin_to:
        params.append(("search[dateFin][to]", date_fin_to))
    if page is not None:
        params.append(("page", str(page)))
    # encode only keys/values, keep '=' and '&' as separators
    qs = "&".join("{}={}".format(quote(k, safe="[]"), quote(str(v), safe=""))
                  for k, v in params)
    return BASE + "/recherche" + ("?" + qs if qs else "")


def build_item_url(archive_id):
    """Build an item page URL from a numeric archive id."""
    return BASE + "/archive/" + str(archive_id)


def parse_result_count(html):
    """Return the integer N from 'N archives correspondent à votre recherche',
    or None. Tolerates non-breaking spaces inside the number."""
    import re
    if not html:
        return None
    m = re.search(r"(\d[\d\s\u00a0]*)\s+archives?\s+correspondent", html, re.I)
    if not m:
        return None
    digits = re.sub(r"[\s\u00a0]", "", m.group(1))
    return int(digits) if digits.isdigit() else None


def parse_item_ids(html):
    """Return the ordered, de-duplicated list of archive ids found as
    a[href^="/archive/<id>"] in a search results page HTML (or a raw text dump
    that contains /archive/<id> links)."""
    import re
    if not html:
        return []
    out = []
    for m in re.finditer(r'/archive/(\d+)', html):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def is_digitized(html):
    """Heuristic: a result card / item page that does NOT carry the 'not yet
    digitised' notice is treated as digitised (has an image)."""
    if not html:
        return False
    return "pas encore été numérisée" not in html


if __name__ == "__main__":
    # self-check
    u = build_search_url("Citroën", group=1,
                         date_debut_from="1920-01-01", date_debut_to="1939-12-31")
    assert u.startswith(BASE + "/recherche?"), u
    assert "search%5BgroupTypeElement%5D=1" in u, u
    assert build_item_url(142471) == BASE + "/archive/142471"
    assert parse_result_count("28 archives correspondent à votre recherche") == 28
    assert parse_result_count("72\u00a0989 archives correspondent") == 72989
    assert parse_item_ids('x <a href="/archive/142471">') == ["142471"]
    print("ok", u)
