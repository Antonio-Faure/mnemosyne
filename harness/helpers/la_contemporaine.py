"""La Contemporaine (ex-BDIC), Nanterre — fonds photographiques 1914-1918.

Source référence pour mnemosyne, écrite par l'agent navigateur (Archivist).
Bibliothèque numérique : **L'Argonnaute** — https://argonnaute.parisnanterre.fr
Institution : La Contemporaine, 184 cours Nicole Dreyfus, 92001 Nanterre.
Plateforme : appli maison type « Nakalona » (ARK NAAN = 14707). ~200 000
documents numérisés (imprimés, archives, dessins, photographies, affiches).
Fonds clés PGM : « Albums Valois » (Marne/Meuse/Somme/Aisne/thématiques),
presse 1914-1918, affiches. Labellisée **Culture Libre** ; documents du
domaine public sous Licence Ouverte, le reste « tous droits réservés ».

Ce module est la RÉFÉRENCE read-only que le codeur utilise pour bâtir
`config/sources/la_contemporaine.yaml` + son connecteur. Il n'écrit rien sur
le distant, ne copie/réhéberge aucune image : il renvoie des URLs publiques
servies par l'institution (hotlink) — mnemosyne n'héberge pas l'image.

=====================================================================
CHEMIN D'ACCÈS VÉRIFIÉ  (2026-11-25)
=====================================================================
Accès programmatique PROPRE (datasets/IIIF/JSON search) : ABSENT.
  - Pas d'API de recherche JSON, pas de IIIF (Presentation/Image) exposé :
    `/manifest`, `/iiif/...`, `/api/iiif/...` renvoient du HTML 404.
  - OAI-PMH existe à /oai-pmh MAIS (a) interdit aux robots (robots.txt
    `Disallow: /oai-pmh`), (b) inutilisable : completeListSize=131,
    métadonnée `oai_dc` = un simple <dc:identifier> (UUID), `ead` idem.
    -> NE PAS l'utiliser.
  - Sitemaps : /sitemap.xml -> /sitemaps/Search_{1..3}.xml, Editorial_1.xml
    (découverte d'URL, pas de recherche par mot-clé ; non nécessaires ici).
=> La recherche est rendue CÔTÉ SERVEUR (HTML). Seul le HTML de recherche
   permet la recherche par mot-clé. On PARSE ce HTML UNIQUEMENT pour
   DÉCOUVRIR les UUID média ; l'image elle-même est un asset public direct.

robots.txt (User-agent: *) : Disallow /private/, /oai-pmh, /user/ — TOUT LE
RESTE EST AUTORISÉ, dont /search/results, /ark:/14707/..., /images/...
=> lecture des pages publiques + assets publics = conforme. Respecter :
   UA descriptif ci-dessous, cadence (_pace), pas de /oai-pmh, /user, /private.

Anti-bot : PAS d'Anubis/Cloudflare pour ces pages. `requests` + UA bot
(« mnemosyne-research-bot/1.0 ») reçoit la vraie page (200, résultats
présents). ATTENTION : robots.txt bloque nommément GPTBot, OAI-SearchBot,
Applebot, etc. -> NE PAS usurper ces UA ; notre UA descriptif passe.
Un `data-captcha="hcaptcha"` traîne dans le <head> mais ne bloque PAS la
lecture (c'est pour le formulaire de contact).

RECHERCHE (découverte) — HTML, GET
    https://argonnaute.parisnanterre.fr/search/results?q=<requête>&scope=all
      &facet_media=image        # -> seulement les images (recommandé)
      &facet_typology=Photographie   # optionnel, resserre sur photos
      &page=<N>                 # pagination (1-based) -> « page N sur M »
      &resultsPerPage=20|40|80  # 20 par défaut
    - q = phrase pleine, supporte les guillemets ("usine Citroën").
    - SÉMANTIQUE AND : plusieurs mots = tous requis -> une phrase longue
      renvoie PEU/0 résultat (ex. 5 mots -> 2 items). Envoyer des requêtes
      courtes (2–3 mots-clés) ou laisser le moteur formuler.
    - 20 résultats/page par défaut ; `&page=2` change bien de page.
    - « Aucun résultat » => 0 item.
    - Couverture PGM vérifiée : obus≈2280, usine de guerre≈1580,
      Citroën≈120 (Usines Citroën Quai de Javel !), femmes usine (munition-
      nettes à Citroën), tournage obus (Panhard & Levassor), arsenal, etc.

CARTE DE RÉSULTAT (image) — structure HTML (une <li class="element-list">)
    <a href="/ark:/14707/<ARK>/<UUID>" title="Visualiser le media"> ... </a>
    <img src="/images/<UUID>_search_result_thumbnail.jpg" alt="<TITRE>">
    <p class="info-list-picture">1 media</p>
    <a href="https://.../ark:/14707/<ARK>"> <h2><span><TITRE></span></h2> </a>
    <h3>Date</h3><p><span><DATE></span></p>
    <h3>Cote</h3><p class="referenceCodes"><COTE></p>
    <div class="context-content">Contexte : <FONDS/CONTEXTE></div>
  => titre, date, cote, contexte, lien notice, lien média, UUID média.
  NB : les cartes PDF/vidéo n'ont PAS de `_search_result_thumbnail.jpg` ;
  avec `facet_media=image` il n'y a que des images, mais on filtre quand même.

IMAGES (assets publics directs — pas du HTML, on ne re-scrape pas l'image) :
    vignette (mini)   /images/<UUID>_search_result_thumbnail.jpg   (~7 Ko)
    notice  (moyenne) /images/<UUID>_img-notice.jpg                (~65 Ko)
    PLEINE RÉSOLUTION /images/<UUID>.jpg                           (0.2–2 Mo+)
  UUID = hash MD5-like du média (dans l'URL /ark/.../<UUID> et la vignette).
  -> full = strip du suffixe `_search_result_thumbnail.jpg` puis `.jpg`.

NOTICE COMPLÈTE (optionnel, pour auteur/lieu/droits) — HTML
    https://argonnaute.parisnanterre.fr/ark:/14707/<ARK>
  métadonnées en blocs :
    <p class="attribut">LABEL</p> ... <div class="content">VALEUR</div>
  LABEL parmi : Cote/Cotes extrêmes, Date, Conditions d'utilisation,
  Mots clés lieux, Mots clés matières, Mots clés typologiques, Langue, ...
  `record_metadata()` ci-dessous les extrait (best-effort). Créateur usuel
  des « Albums Valois » = Section photographique des Armées (SPA), 1915.

NORMALISATION pour le connecteur
--------------------------------
- external_id : UUID média (stable) ; rattacher à l'ARK/notice.
- title       : <h2><span> (ou alt de la vignette)
- date        : carte « Date » (texte libre, ex. « 13 octobre 1915 »)
- cote        : carte « Cote » (ex. VAL 203/063)
- context/fonds : « Contexte : Albums Valois Meuse »
- creator     : « Section photographique des Armées (SPA) » (Albums Valois) ;
                sinon via record_metadata() si présent.
- place       : record_metadata()["Mots clés lieux"] (ex. « Meuse », « Paris »)
- credit/source : « La Contemporaine (L'Argonnaute) »
- rights      : domaine public => « Licence Ouverte / Open Licence » ;
                sinon « Tous droits réservés » (voir Conditions d'utilisation
                de la notice). mnemosyne AFFICHE l'info et renvoie à la notice.
- thumbnail_url: .../images/<UUID>_search_result_thumbnail.jpg  (grille)
- image_url  : .../images/<UUID>.jpg                             (détail)
- page_url   : .../ark:/14707/<ARK>/<UUID>  (visionneuse) ou .../<ARK> (notice)
"""

from __future__ import annotations

import html as _html
import re
import time
from urllib.parse import quote

import requests

BASE = "https://argonnaute.parisnanterre.fr"
SEARCH_URL = BASE + "/search/results"
IMAGES = BASE + "/images"
OAI_URL = BASE + "/oai-pmh"  # existe mais interdit (robots) + inutile -> NE PAS utiliser

UA = (
    "mnemosyne-research-bot/1.0 "
    "(https://github.com/Antonio-Faure/mnemosyne; opensource archive image search engine)"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}
_ALLOWED_PER_PAGE = (20, 40, 80)
_LAST = {"t": 0.0}
_SESSION = requests.Session()
_SESSION.headers.update(HEADERS)


# ---------------------------------------------------------------- utilitaires

def _pace(min_gap: float = 1.2) -> None:
    """Espacement poli entre deux requêtes (défaut 1,2 s)."""
    dt = time.time() - _LAST["t"]
    if dt < min_gap:
        time.sleep(min_gap - dt)
    _LAST["t"] = time.time()


def _get(url, params=None, retries=4, timeout=45):
    """GET avec cadence + quelques retries. Renvoie Response(200) ou None."""
    last = None
    for i in range(retries):
        _pace()
        try:
            r = _SESSION.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r
            last = r.status_code
        except Exception as e:  # noqa: BLE001
            last = repr(e)[:120]
        time.sleep(1.0 * (i + 1))
    print("  !! HTTP fail", url, last)
    return None


def _clean(x: str | None) -> str:
    if not x:
        return ""
    return _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x)).strip())


def _clamp_per_page(n: int) -> int:
    try:
        n = int(n)
    except Exception:  # noqa: BLE001
        return 20
    return min(_ALLOWED_PER_PAGE, key=lambda v: abs(v - n))


# ---------------------------------------------------------------- requêtes

def build_search_url(q: str, page: int = 1, per_page: int = 20,
                     media_only: bool = True, typology: str | None = None,
                     scope: str = "all") -> str:
    """Construit l'URL de recherche Argonnaute pour une requête et une page."""
    params = [("q", q), ("scope", scope)]
    if media_only:
        params.append(("facet_media", "image"))
    if typology:
        params.append(("facet_typology", typology))
    per_page = _clamp_per_page(per_page)
    if per_page != 20:
        params.append(("resultsPerPage", str(per_page)))
    if page and page > 1:
        params.append(("page", str(page)))
    qs = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params)
    return f"{SEARCH_URL}?{qs}"


def full_image_url(uuid: str) -> str:
    """URL de l'image pleine résolution pour un UUID média."""
    return f"{IMAGES}/{uuid}.jpg"


def thumb_image_url(uuid: str) -> str:
    """URL de la vignette « résultat de recherche » pour un UUID média."""
    return f"{IMAGES}/{uuid}_search_result_thumbnail.jpg"


_CARD_RE = re.compile(r'<li class="element-list">(.*?)</li>', re.S)
_IMG_RE = re.compile(
    r'<img[^>]+src="(/images/([0-9a-fA-F\-]+)_search_result_thumbnail\.jpg)"', re.S)
_MEDIA_RE = re.compile(
    r'<a href="(/ark:/14707/[^"]+/[0-9a-fA-F\-]+)"[^>]*title="Visualiser le media"', re.S)
_RECORD_RE = re.compile(
    r'href="(https://argonnaute\.parisnanterre\.fr/ark:/14707/[0-9a-zA-Z]+)"', re.S)


def _parse_results(page_html: str) -> list[dict]:
    """Extrait les cartes image d'une page de résultats. Ignore PDF/vidéos."""
    out: list[dict] = []
    for card in _CARD_RE.findall(page_html):
        img = _IMG_RE.search(card)
        if not img:           # pas une carte image (PDF/vidéo) -> skip
            continue
        uuid = img.group(2)
        med = _MEDIA_RE.search(card)
        rec = _RECORD_RE.search(card)
        title = re.search(r"<h2>\s*<span>(.*?)</span>", card, re.S)
        date = re.search(r"<h3>Date</h3>\s*<p>\s*<span>(.*?)</span>", card, re.S)
        cote = re.search(r'<h3>Cote</h3>\s*<p[^>]*>(.*?)</p>', card, re.S)
        ctx = re.search(r'Contexte\s*:\s*(.*?)</div>', card, re.S)
        out.append({
            "external_id": uuid,
            "uuid": uuid,
            "title": _clean(title.group(1)) if title else None,
            "date": _clean(date.group(1)) if date else None,
            "cote": _clean(cote.group(1)) if cote else None,
            "context": _clean(ctx.group(1)) if ctx else None,
            "record_url": rec.group(1) if rec else None,
            "media_url": BASE + med.group(1) if med else None,
            "page_url": (BASE + med.group(1)) if med else (rec.group(1) if rec else None),
            "thumb_url": BASE + img.group(1),
            "image_url": full_image_url(uuid),
            "credit": "La Contemporaine (L'Argonnaute)",
        })
    return out


def _pages_from_html(page_html: str) -> int:
    if "Aucun résultat" in page_html and "element-list" not in page_html:
        return 0
    m = re.search(r"page \d+ sur (\d+)", page_html)
    return int(m.group(1)) if m else (1 if "element-list" in page_html else 0)


def search(q: str, page: int = 1, per_page: int = 20,
           media_only: bool = True, typology: str | None = None) -> dict:
    """Recherche sur L'Argonnaute et renvoie les images normalisées.

    Retourne un dict :
      {"items": [ {external_id,title,date,cote,context,record_url,
                   media_url,page_url,thumb_url,image_url,credit}, ... ],
       "page": int, "pages": int, "per_page": int, "total": int,
       "query": str, "url": str}
    0 résultat => items=[], pages=0.
    """
    url = build_search_url(q, page=page, per_page=per_page,
                           media_only=media_only, typology=typology)
    r = _get(url)
    if r is None:
        return {"items": [], "page": page, "pages": 0, "per_page": per_page,
                "total": 0, "query": q, "url": url, "error": "http_fail"}
    items = _parse_results(r.text)
    pages = _pages_from_html(r.text)
    pp = _clamp_per_page(per_page)
    return {
        "items": items,
        "page": page,
        "pages": pages,
        "per_page": pp,
        "total": pages * pp if pages else len(items),
        "query": q,
        "url": url,
    }


# ---------------------------------------------------------------- notice

_ATTR_RE = re.compile(
    r'<p class="attribut">(.*?)</p>.*?<div class="content">(.*?)</div>\s*</div>\s*</div>',
    re.S)


def record_metadata(record_url: str) -> dict:
    """Métadonnées « attribut -> valeur » d'une notice (best-effort, read-only).

    `record_url` = .../ark:/14707/<ARK> (ou la visionneuse .../<ARK>/<UUID>).
    Renvoie par ex. {"Cote/Cotes extrêmes": "...", "Conditions d'utilisation":
    "...", "Mots clés lieux": "...", ...}. Utile pour auteur/lieu/droits.
    """
    url = record_url if record_url.startswith("http") else BASE + record_url
    r = _get(url)
    if r is None:
        return {}
    out: dict = {}
    for label, val in _ATTR_RE.findall(r.text):
        key = _clean(label)
        v = _clean(val)
        if key and v and key not in out:
            out[key] = v
    return out


# ---------------------------------------------------------------- self-test

def self_test() -> dict:
    """Vérifie en lecture seule que les endpoints répondent et parsent.

    Ne lève pas ; renvoie un rapport dict. Pratique pour les tests du codeur.
    """
    report: dict = {"base": BASE, "ok": True, "checks": {}}
    r = _get(build_search_url("Photographie", page=1, per_page=20))
    if r is None:
        report["ok"] = False
        report["checks"]["search"] = {"status": "fail"}
        return report
    items = _parse_results(r.text)
    report["checks"]["search"] = {
        "status": "ok", "status_code": r.status_code, "items": len(items),
        "pages": _pages_from_html(r.text),
    }
    if items:
        it = items[0]
        report["checks"]["first_item"] = {
            "title": it["title"], "date": it["date"], "cote": it["cote"],
            "image_url": it["image_url"], "page_url": it["page_url"],
        }
        ir = _get(it["image_url"])
        report["checks"]["image"] = {
            "status": "ok" if ir is not None else "fail",
            "content_type": ir.headers.get("content-type") if ir is not None else None,
            "bytes": len(ir.content) if ir is not None else 0,
        }
    return report


if __name__ == "__main__":  # pragma: no cover
    import json
    print(json.dumps(self_test(), ensure_ascii=False, indent=2))
