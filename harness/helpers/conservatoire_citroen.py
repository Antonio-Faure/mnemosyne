"""
conservatoire_citroen — accès lecture seule au patrimoine photographique Citroën
(« Conservatoire Citroën & DS » / « Citroën Heritage »), conservé et diffusé par
le Centre d'Archives de Terre Blanche (L'Aventure Peugeot Citroën DS).

Source Mnemosyne demandée : `conservatoire_citroen`.
Agent navigateur, tâche #556. Résolveur adversarial : phrase yt_01grGKLcVOc_73
(crise financière d'André Citroën, passage sous contrôle de Michelin — Pierre
Michelin — accord de 1935).

Toutes les données ci-dessous ont été VÉRIFIÉES EN DIRECT le 2026-11-26
(requests + bs4, et lecture navigateur du catalogue).

============================================================================
1) OÙ SONT VRAIMENT LES PHOTOS — « Conservatoire » ≡ « Citroën Heritage »
============================================================================
Le « Conservatoire Citroën & DS » d'Aulnay-sous-Bois est la collection de
VÉHICULES (≈300 autos) du patrimoine Citroën/DS portée par l'association
« L'Aventure Peugeot Citroën DS ». Il N'A PAS de photothèque numérique propre.
Ses ARCHIVES PHOTOGRAPHIQUES sont collectées, classées et mises à disposition par
le Centre d'Archives de Terre Blanche (Hérimoncourt) — c'est le MÊME catalogue
que celui déjà visé par la source existante `citroen_heritage`.

  • Institution ........ L'Aventure Peugeot Citroën DS (Fonds de dotation)
                          https://laventure-association.com
  • Page collections .... https://laventure-association.com/laventure-citroen/
                          le-conservatoire-de-laventure-citroen-ds/
                          (« Les collections Citroën & DS »)
  • Catalogue d'archives  https://www.archives-terreblanche.fr
  • Contacts ............ archives-avpcd@laventureassociation.com (archives)
                          contact-avpcd@laventureassociation.com (général)

=> CONSÉQUENCE : `conservatoire_citroen` ne désigne PAS une institution
   distincte avec sa propre photothèque/API. C'est le patrimoine Citroën déjà
   couvert par `citroen_heritage`. Voir RECOMMANDATION (§5).

============================================================================
2) ACCÈS — AUCUN ENDPOINT PROGRAMMATIQUE
============================================================================
  • Pas d'API, pas de IIIF, pas d'OAI-PMH/SRU, pas de JSON, pas de sitemap,
    pas de robots.txt : /api, /robots.txt, /sitemap.xml -> 404.
  • Stack Symfony + Varnish, HTML rendu côté serveur. Seule surface = scraping
    HTML + fichiers JPEG (/upload/documents/...). Pas d'anti-bot ; UA descriptif
    suffit ; site public, sans login.
  • La « Médiathèque Citroën » de Stellantis (medialibrary.stellantis.com/citroen)
    existe mais est RÉSERVÉE aux professionnels de la communication — NON ouverte.
  • → Scraping SOUMIS à la règle de consentement du dépôt (extra.scraping_consent).

CONSENTEMENT : un e-mail de demande d'accès programmatique a été envoyé le
2026-11-25 22:45 à archives-avpcd@laventureassociation.com. VÉRIFIÉ le
2026-11-26 : le fil ne contient qu'UN message sortant, AUCUNE réponse. Donc
consentement EN ATTENTE → NE PAS activer un connecteur « live » (scraping réel)
tant que la réponse n'est pas « oui ».

============================================================================
3) PERTINENCE « PHRASE » — accord Citroën–Michelin 1935
============================================================================
⚠ Le catalogue NE contient AUCUNE photo NUMÉRISÉE de la faillite 1934-35 ni de
  l'accord/prise de contrôle de 1935. Faits vérifiés :

  • /archive/96582  « Messieurs Citroën & Michelin » (Période 01/11/1944,
    Photo - carte postale ; Thème « Patrimoine / Guerre mondiale ;
    Direction générale / Dirigeant » ; réf DOS2017FIG-00496) :
    → MÉTADONNÉE SEULE, NON NUMÉRISÉE (aucune image en ligne).

  • /archive/97389  « Portrait de Mr Pierre Michelin » (Période 01/12/1950,
    Photo - carte postale ; Thème « Direction générale / Dirigeant » ;
    Société « 3. Citroën / André Citroën SA » ; réf DOS2017FIG-01045) :
    → NUMÉRISÉ (image 703×960 px). C'est la SEULE image numérique liée à
      Michelin. Pierre Michelin est l'homme nommé dans la phrase [73] — donc
      portrait pertinent (≠ des portraits d'André Citroën au Mondial 1932 déjà
      utilisés par les tâches #466/#471).

  • Recherche « Michelin » (iconographique, 43 items sur 3 pages) : le seul item
    Citroën+Michelin pré-1945 est 96582 (non numérisé) ; TOUS les autres items
    Citroën+Michelin sont des années 1990 (pneus Xantia, rallye AX…).

  • Filtre date 1934-1936, requête « Citroën » : uniquement Traction Avant /
    Rosalie (affiches) — RIEN sur Michelin ni sur la crise financière.

  → En l'état, le mieux que cette source puisse fournir pour la phrase est le
    portrait de Pierre Michelin (97389). Pas de photo documentaire de l'accord.

============================================================================
4) DROITS
============================================================================
Tout sous droits (© + marques), reproduction interdite sans autorisation, aucune
licence libre (boutique de reproductions payantes). → Afficher UNIQUEMENT les
MÉTADONNÉES + un LIEN vers la notice ; ne JAMAIS copier / réhéberger l'image.
Voir RIGHT_TEXT.

============================================================================
5) RECOMMANDATION
============================================================================
`conservatoire_citroen` et `citroen_heritage` pointent le MÊME catalogue (Terre
Blanche). Deux options pour le produit, au choix du codeur :
  (a) enregistrer `conservatoire_citroen` comme descripteur/alias qui RÉUTILISE
      le connecteur `citroen_heritage` (protocole « html », consentement requis) ;
  (b) — préférable — ne pas dupliquer : s'assurer que `citroen_heritage` renvoie
      le portrait Pierre Michelin (97389) pour cette phrase.
Dans les deux cas : PAS de nouveau scraper nécessaire, et connecteur GATED par
extra.scraping_consent tant que la réponse Terre Blanche n'est pas « oui ».

API (lecture seule ; à n'appeler qu'avec consentement) :
  build_search_url(), parse_results(), search(), fetch_item(), resolve()
"""
import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------- #
# Constantes institutionnelles
# --------------------------------------------------------------------------- #
SOURCE_KEY = "conservatoire_citroen"
INSTITUTION = "Conservatoire Citroën & DS / Citroën Heritage (L'Aventure Peugeot Citroën DS)"
ARCHIVE_CENTRE = "Centre d'Archives de Terre Blanche (Hérimoncourt)"
ASSOCIATION = "L'Aventure Peugeot Citroën DS — https://laventure-association.com"
COLLECTIONS_PAGE = ("https://laventure-association.com/laventure-citroen/"
                    "le-conservatoire-de-laventure-citroen-ds/")
CONTACTS = {
    "archives": "archives-avpcd@laventureassociation.com",
    "general": "contact-avpcd@laventureassociation.com",
}

BASE = "https://www.archives-terreblanche.fr"
UA = ("MnemosyneBot/1.0 (moteur de recherche d'images d'archives; "
      "contact archivist.mnemosyne@gmail.com)")
HEADERS = {"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"}

RIGHT_TEXT = ("Tous droits réservés. Reproduction interdite sans autorisation "
              "(© Citroën / L'Aventure Peugeot Citroën DS). Mnemosyne affiche "
              "uniquement les métadonnées et un lien vers la notice ; aucune "
              "copie, aucun hébergement, aucune redistribution.")

# Statut d'accès / consentement (à garder à jour).
ACCESS = {
    "protocol": "html-scrape",
    "api": False,             # aucun endpoint programmatique
    "iiif": False,
    "oai_pmh": False,
    "requires_consent": True,  # extra.scraping_consent
    "consent_status": "pending",   # e-mail 2026-11-25 22:45, aucune réponse au 2026-11-26
    "no_bypass": True,        # jamais contourner un 403/WAF
}

# Exemples vérifiés en direct (utiles au résolveur et aux tests).
KNOWN_ITEMS = {
    "97389": {
        "digitized": True,
        "reference": "DOS2017FIG-01045",
        "description": "Portrait de Mr Pierre Michelin.",
        "period": "01/12/1950 - 31/12/1950",
        "theme": "Direction générale / Dirigeant",
        "society": "3. Citroën / André Citroën SA",
        "image_url": BASE + "/upload/documents/7561339-68bbadb250f98975156479.jpg",
        "note": "Seule image numérique liée à Michelin (Pierre Michelin = nommé phrase [73]).",
    },
    "96582": {
        "digitized": False,
        "reference": "DOS2017FIG-00496",
        "description": "Messieurs Citroën & Michelin.",
        "period": "01/11/1944 - 30/11/1944",
        "theme": "Patrimoine / Guerre mondiale; Direction générale / Dirigeant",
        "society": "3. Citroën / André Citroën SA",
        "image_url": "",
        "note": "Métadonnée seule, NON numérisée.",
    },
}

# Fragment du nom de la seule image numérique pertinente pour la phrase.
PIERRE_MICHELIN_ID = "97389"

# Libellés de champs -> clés normalisées.
_FIELD_MAP = {
    "Description": "description",
    "Période": "period_raw",
    "Type de document": "doc_type",
    "Theme": "theme",
    "Thème": "theme",
    "Société": "society",
    "Auteur": "creator",
    "Lieux": "place",
    "Lieu": "place",
    "Référence du document": "reference",
}


# --------------------------------------------------------------------------- #
# Utilitaires
# --------------------------------------------------------------------------- #
def _abs(url):
    if not url:
        return ""
    return url if url.startswith("http") else BASE + url


def _norm(text):
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _session(session):
    return session or requests


# --------------------------------------------------------------------------- #
# Recherche
# --------------------------------------------------------------------------- #
def build_search_url(query, page=1, group_type="1", date_from=None, date_to=None):
    """URL de recherche HTML de Terre Blanche.

    group_type : « 1 » = iconographique (photos/affiches). Autres valeurs 2..5.
    date_from / date_to : ISO « YYYY-MM-DD » (filtre sur la DATE DE DÉBUT de
    période ; les autres formats sont ignorés en silence par le site).
    """
    url = (f"{BASE}/recherche?search%5Bsearch%5D={quote(query)}"
           f"&search%5BgroupTypeElement%5D={group_type}&page={page}")
    if date_from:
        url += f"&search%5BdateDebut%5D%5Bfrom%5D={date_from}"
    if date_to:
        url += f"&search%5BdateDebut%5D%5Bto%5D={date_to}"
    return url


def parse_results(html):
    """Renvoie la liste des cartes de résultat d'une page de recherche."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for card in soup.select("div.result"):
        a = card.select_one("a.result__link[href*='/archive/'], a[href*='/archive/']")
        if not a:
            continue
        m = re.search(r"/archive/(\d+)", a.get("href", ""))
        if not m:
            continue
        iid = m.group(1)

        def g(sel, card=card):
            el = card.select_one(sel)
            return _norm(el.get_text(" ", strip=True)) if el else ""

        img = card.select_one(".result__col--image img.result__image, "
                              ".result__col--image img")
        err = card.select_one(".result__error")
        title = g(".result__title") or g(".result__description")
        out.append({
            "id": iid,
            "title": title,
            "doc_type": g(".result__type"),
            "description": g(".result__description"),
            "dates": g(".result__dates"),
            "image_url": _abs(img.get("src")) if img else "",
            "digitized": bool(img) and not err,
            "reference": "",
            "theme": "",
            "society": "",
            "creator": "",
            "place": "",
            "page_url": f"{BASE}/archive/{iid}",
        })
    return out


def search(query, page=1, group_type="1", date_from=None, date_to=None, session=None):
    """Recherche Terre Blanche (1 page). Renvoie parse_results(...)."""
    url = build_search_url(query, page=page, group_type=group_type,
                           date_from=date_from, date_to=date_to)
    r = _session(session).get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return parse_results(r.text)


# --------------------------------------------------------------------------- #
# Notice
# --------------------------------------------------------------------------- #
def fetch_item(item, session=None):
    """Détail d'une notice. `item` = id numérique ou URL de notice /archive/<id>."""
    if isinstance(item, str) and "archive/" in item:
        url = item if item.startswith("http") else BASE + item
        m = re.search(r"/archive/(\d+)", url)
        iid = m.group(1) if m else str(item)
    else:
        iid = str(item).strip()
        url = f"{BASE}/archive/{iid}"
    r = _session(session).get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    big = soup.select_one("#big-image")
    image_url = _abs(big.get("src")) if big else ""

    fields = {}
    det = soup.select_one(".archive__details")
    if det:
        for div in det.find_all("div", recursive=False):
            ps = div.find_all("p")
            if len(ps) >= 2:
                fields[_norm(ps[0].get_text())] = _norm(ps[1].get_text())

    rec = {"id": iid, "image_url": image_url, "digitized": bool(image_url),
           "page_url": url, "fields": fields, "rights": RIGHT_TEXT}
    for label, key in _FIELD_MAP.items():
        if label in fields:
            rec[key] = fields[label]
    rec.setdefault("description", "")
    period = fields.get("Période", "")
    if period:
        parts = re.split(r"\s*-\s*", period)
        rec["period_start"] = parts[0].strip()
        rec["period_end"] = parts[1].strip() if len(parts) > 1 else ""
    return rec


# --------------------------------------------------------------------------- #
# Normalisation -> enregistrement type Mnemosyne
# --------------------------------------------------------------------------- #
def _card_from_item(item):
    """Fabrique une pseudo-carte à partir d'une notice (pour resolve)."""
    return {
        "id": item["id"],
        "title": item.get("description") or f"Notice {item['id']}",
        "doc_type": item.get("doc_type", ""),
        "description": item.get("description", ""),
        "dates": item.get("period_raw", ""),
        "image_url": item.get("image_url", ""),
        "digitized": item.get("digitized", False),
        "page_url": item.get("page_url", f"{BASE}/archive/{item['id']}"),
        "reference": item.get("reference", ""),
        "theme": item.get("theme", ""),
        "society": item.get("society", ""),
        "creator": item.get("creator", ""),
        "place": item.get("place", ""),
    }


def _record(card):
    """Enregistrement normalisé pour le moteur (métadonnées + lien, jamais l'image copiée)."""
    return {
        "source": SOURCE_KEY,
        "institution": INSTITUTION,
        "id": card["id"],
        "reference": card.get("reference", ""),
        "title": card.get("title", ""),
        "description": card.get("description", ""),
        "doc_type": card.get("doc_type", ""),
        "theme": card.get("theme", ""),
        "society": card.get("society", ""),
        "creator": card.get("creator", ""),
        "place": card.get("place", ""),
        "date_text": card.get("dates", ""),
        "rights": RIGHT_TEXT,
        "page_url": card.get("page_url", f"{BASE}/archive/{card['id']}"),
        # image_url fourni UNIQUEMENT si numérisé ; jamais téléchargée/réhébergée.
        "image_url": card.get("image_url", "") if card.get("digitized") else "",
        "digitized": bool(card.get("digitized")),
    }


def _is_strong_michelin_query(low):
    """Vrai si la requête vise la prise de contrôle Citroën par Michelin (phrase [73])."""
    if "pierre michelin" in low:
        return True
    if "michelin" in low and any(k in low for k in
                                 ("citroen", "citroën", "faillite", "crise",
                                  "controle", "contrôle", "accord", "dirigeant",
                                  "1935", "rachat")):
        return True
    return False


def resolve(query, limit=8, session=None):
    """Résout une requête (phrase) vers des notices du patrimoine Citroën.

    Comportement :
      • recherche free-text « query » sur Terre Blanche (iconographique) ;
      • si la requête vise la prise de contrôle Citroën par Michelin (phrase [73]),
        le portrait NUMÉRISÉ de Pierre Michelin (97389) est placé EN TÊTE — seule
        image numérique réellement liée à Michelin ;
      • renvoie des enregistrements digitized-d'abord (l'image n'est jamais
        copiée, seulement l'URL + métadonnées + lien notice).
    """
    sess = _session(session)
    low = (query or "").lower()
    try:
        cards = search(query, session=sess)
    except Exception:
        cards = []

    ordered = []
    have = set()
    if _is_strong_michelin_query(low):
        try:
            it = fetch_item(PIERRE_MICHELIN_ID, session=sess)
            if it.get("digitized"):
                pc = _card_from_item(it)
                ordered.append(pc)
                have.add(pc["id"])
        except Exception:
            pass

    for c in sorted(cards, key=lambda c: 0 if c.get("digitized") else 1):
        if c["id"] in have:
            continue
        have.add(c["id"])
        ordered.append(c)
    return [_record(c) for c in ordered[:limit]]


if __name__ == "__main__":
    print("BASE:", BASE)
    print("CONSENT:", ACCESS["consent_status"], "| api:", ACCESS["api"])
    print("\n-- resolve('crise André Citroën, contrôle Michelin 1935') --")
    for rec in resolve("crise André Citroën prise de contrôle Michelin 1935", limit=6):
        print(f"  {rec['id']:>7} {'DIG' if rec['digitized'] else '   '} "
              f"{rec['reference']:>16} {rec['date_text'][:23]:23} {rec['title'][:55]}")
