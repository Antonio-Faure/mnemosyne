
"""
Archives de Paris (archives.paris.fr) — public programmatic access reference.

Platform: Arkotheque (instance "ad75").  The public JSON API lives under
`/_recherche-api/*` and the image server exposes IIIF Image API v2 (level 2).

IMPORTANT (verified live, read-only):
  * The `/_arkotheque/*` routes (oai, async/detail, ...) are CAPTCHA-gated and
    robots.txt-disallowed -> NOT usable. The real public API is `/_recherche-api/*`.
  * No login, no captcha, no WAF bypass needed. Plain HTTPS GET works.
  * There is NO free-text "recherche libre" field on the PHOTOGRAPHIES moteur;
    keyword search is done via the "Edifice ou site represente" input filter
    (spans texte_court + texte_long) or the "Arrondissement" input filter.
  * Images: IIIF Image API v2 level 2, served through a public proxy. The
    info.json @id reveals an INTERNAL host (cmp.paris.mdp:8182) — always use
    the public `/_recherche-images/show/...` base, never the internal host.
  * Rights: no per-record licence field (`licence`="" / `licencesClic`=[]).
    Per-image `allowDownload` is True. Site-wide legal notice at
    https://archives.paris.fr/mentions-legales : "Les photos ... proviennent
    de sources differentes ... Par defaut, elles proviennent des Archives de
    Paris." -> default credit = "Archives de Paris". No explicit public-domain
    or open-licence statement in the API; display credit + link to notice.

This module is a REFERENCE for the coder building the product connector. It is
pure URL-building + parsing; network access is via a pluggable `get(url)->str`
that defaults to the harness `http_get` (UTF-8 -> JSON only, not binary JPEG).
"""

import json
import re
import urllib.parse as _up


# Resolve a default HTTP getter that works both inside browser-harness exec
# (where http_get is a global) and when imported as a plain module.
def _resolve_default_get():
    g = globals().get("http_get")
    if callable(g):
        return g
    try:
        from browser_harness.helpers import http_get as _hg  # type: ignore
        return _hg
    except Exception:
        return None


BASE = "https://archives.paris.fr"

# --- Instance IDs (PHOTOGRAPHIES moteur) -----------------------------------
MOTEUR = "arko_default_67d426d4c0eab"   # refUnique of the PHOTOGRAPHIES moteur
MOTEUR_ID = 41                          # numeric id used in /search-simple/{id}
MODE_RESTIT = "arko_default_67d42cbbe4d8f"  # "Mosaique" (only restit)
VISIONNEUSE_FIELD = "arko_default_68a2fde625b3d"  # image field key for visionneuse

# --- Facet filters (refUnique) ---------------------------------------------
FILT_EDIFICE = "arko_default_67d42ab10bf33"   # "Edifice ou site represente" (input / full-text)
FILT_ARRONDISSEMENT = "arko_default_68d558ad62719"  # "Arrondissement" (input)
FILT_NOM_VOIE = "arko_default_67d42ab0a5eaa"  # "Nom de la voie" (select)
FILT_COTE = "arko_default_67d427caafc67"      # "Cote" (select)
FILT_THEMES = "arko_default_67d42ab08a1e0"    # "Themes" (facet)
FILT_AUTEUR = "arko_default_67d42ab09837f"    # "Auteur de la photographie"
FILT_TYPE_PHOTO = "arko_default_67d42ab0d8249"  # "Type de photographie"
# Date/période range slider
FILT_DATE = "arko_default_67d42ab0ca60b"
DATE_FIELD_MIN = "arko_default_649aa8875ae37"
DATE_FIELD_MAX = "arko_default_67d4268a35362"


# ===========================================================================
# SEARCH
# ===========================================================================
def build_search_url(query,
                     filt=FILT_EDIFICE,
                     offset=0,
                     size=25,
                     moteur=MOTEUR,
                     mode=MODE_RESTIT,
                     simple=True):
    """Build a public search URL.

    `query` is matched against the chosen facet's full-text (for FILT_EDIFICE
    this is the practical keyword search). Returns a `/_recherche-api/search[-simple]/41`
    URL. `search-simple` returns lean stubs (~11 KB); `search` adds rendered
    HTML cards (~370 KB) and is not needed for a connector.
    """
    g = f"{moteur}--filtreGroupes[groupes][0][{filt}]"
    params = [
        (f"{moteur}--filtreGroupes[mode]", "simple"),
        (f"{moteur}--filtreGroupes[op]", "AND"),
        (f"{g}[op]", "AND"),
        (f"{g}[q][]", query),
        (f"{g}[extras][mode]", "input"),
        (f"{moteur}--from", str(offset)),
        (f"{moteur}--resultSize", str(size)),   # 25 | 50 | 100
        (f"{moteur}--modeRestit", mode),
        (f"{moteur}--searchMode", "strict"),
    ]
    path = "search-simple" if simple else "search"
    return f"{BASE}/_recherche-api/{path}/{MOTEUR_ID}?" + _up.urlencode(params)


def parse_search(data):
    """From search-simple JSON -> list of stubs {cote, refUnique, key, id}.

    data = {total, results[], count, html, timestamp, ...}
    Each result = {id, intitule (cote, e.g. '11Fi 3546'), refUnique, key,
                   parent, arbre, dernierNiveau}
    """
    out = []
    for r in data.get("results", []):
        out.append({
            "cote": r.get("intitule"),
            "refUnique": r.get("refUnique"),
            "key": r.get("key"),
            "id": r.get("id"),
        })
    return out


# ===========================================================================
# DETAIL (render-fiche)
# ===========================================================================
def build_detail_url(fiche_ref, moteur=MOTEUR, mode=MODE_RESTIT):
    """fiche_ref = the `refUnique` of a stub (e.g. 'arko_fiche_67d410224c7f6')."""
    return f"{BASE}/_recherche-api/render-fiche/{moteur}/{fiche_ref}/{mode}/detail"


def _clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def parse_detail(detail):
    """Parse a render-fiche JSON -> {fields..., images:[{fiche_id,image_id,pos,base}]}.

    detail = {html, infosResult, categorieFrontFiche, typologies, typologiesCSS}.
    Metadata is in `html` via `data-champ="<name>"` attributes.
    Known champ names: titre, cote, collection, auteur, phototype, date_libre,
    date, lieu_administratif, arrondissement, voie, numero_voie,
    type_ouvrage (+ <dt> labels: Cote, Theme, Auteur, Date libre, Date,
    Arrondissement, Voie, "N dans la voie", "Type d'ouvrage represente").
    """
    html = detail.get("html", "") or ""
    fields = {}
    for name, val in re.findall(r'data-champ="([^"]+)"[^>]*>(.*?)</', html, flags=re.S):
        fields[name] = _clean(val)
    images = get_images_from_html(html)
    return {"fields": fields, "images": images}


def get_images_from_html(html):
    """Image refs appear directly in card/detail HTML as
    `/_recherche-images/show/{fiche_id}/image/{image_id}/{pos}?size=...`
    where fiche_id is NUMERIC (not the arko_ refUnique)."""
    out, seen = [], set()
    for m in re.findall(r'/_recherche-images/show/(\d+)/image/(\d+)/(\d+)', html):
        fiche_id, image_id, pos = m
        if (fiche_id, image_id) in seen:
            continue
        seen.add((fiche_id, image_id))
        out.append({
            "fiche_id": fiche_id,
            "image_id": image_id,
            "pos": pos,
            "base": image_base(fiche_id, image_id, pos),
        })
    return out


# ===========================================================================
# IMAGES — IIIF Image API v2 (level 2), via public proxy
# ===========================================================================
def image_base(fiche_id, image_id, pos="0"):
    """Public IIIF image base (append /info.json or /full/.../.../default.jpg)."""
    return f"{BASE}/_recherche-images/show/{fiche_id}/image/{image_id}/{pos}"


def iiif_info_url(base):
    return f"{base}/info.json"


def iiif_image_url(base, size="!800,800", region="full", rotation=0, quality="default", fmt="jpg"):
    """IIIF v2 image request, e.g. {base}/full/!800,800/0/default.jpg."""
    return f"{base}/{region}/{size}/{rotation}/{quality}.{fmt}"


def build_visionneuse_infos_url(fiche_ref, image_id, moteur=MOTEUR,
                               field=VISIONNEUSE_FIELD, typ="image"):
    """Per-image IIIF info + credit. fiche_ref = arko_ refUnique (NOT numeric).
    Returns {medias:[{sources:[{src, infosImage(IIIF v2 block), details:{url},
    refUniqueFiche, allowDownload, title, metadata}]}], licencesClic:[], ...}.
    `src` = public IIIF base; `allowDownload` True. `licence`/`licencesClic` empty.
    """
    return f"{BASE}/_recherche-api/visionneuse-infos/{moteur}/{fiche_ref}/{field}/{typ}/{image_id}"


# ===========================================================================
# Convenience wrappers
# ===========================================================================
def search(query, filt=FILT_EDIFICE, size=25, get=None):
    """Return (total, stubs)."""
    get = get or _resolve_default_get()
    data = json.loads(get(build_search_url(query, filt=filt, size=size)))
    return data.get("total"), parse_search(data)


def detail(fiche_ref, get=None):
    get = get or _resolve_default_get()
    return parse_detail(json.loads(get(build_detail_url(fiche_ref))))


# ===========================================================================
# Verified live results (2026-11, moteur 41 = 6989 records), for reference:
#   Edifice 'Citroen'/'Citroën' -> 0
#   Edifice 'Javel'             -> 4  (rue de Javel, "Vers 1894-1898", pre-Citroen)
#   Edifice 'quai de Grenelle'  -> 3  (metro ligne 6 construction, 1905-1906)
#   Edifice 'Grenelle'          -> 23 (mostly rue de Grenelle, 7e -> false positives)
#   Edifice 'usine'             -> 27 (generic factories, none Citroen)
#   Arrondissement '15'         -> 318 (15e arrondissement building/street photos)
# => No image is labelled "Citroen"; the 15e + quai de Grenelle photos are
#    place/context illustrations only.
# ===========================================================================
