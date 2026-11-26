"""
citroen_heritage — lecture seule du catalogue « Centre d'Archives de Terre Blanche »
(L'Aventure Peugeot Citroën DS), pour la source Mnemosyne `citroen_heritage`.

DONNÉES DE RÉFÉRENCE (vérifiées en direct 2026-11-25)
----------------------------------------------------
• Institution : L'Aventure Peugeot Citroën DS (Fonds de dotation), association
  https://laventure-association.com ; catalogue d'archives hébergé sur
  https://www.archives-terreblanche.fr (Centre d'Archives de Terre Blanche,
  Hérimoncourt). L'URL fournie par le résolveur `www.lavenir-peugeot-citroen-ds.fr`
  ne résout plus (NXDOMAIN) — utiliser archives-terreblanche.fr.

• ACCÈS : AUCUN endpoint programmatique (ni API, ni IIIF, ni SRU/OAI, ni JSON ;
  /api, /sitemap.xml, /robots.txt -> 404). Seule surface = HTML rendu côté serveur.
  → protocole « html » / scrape, SOUMIS à la règle de consentement du repo
  (extra.scraping_consent) pour un connecteur avec marqueurs HTML.
  Pas d'anti-bot ; requests + UA descriptif suffit ; public, sans login.

• RECHERCHE : GET {BASE}/recherche?search[search]=<q>&search[groupTypeElement]=1&page=<N>
    - groupTypeElement=1 = iconographique (photos/affiches), 20 résultats/page.
    - Filtre date OPTIONNEL : &search[dateDebut][from]=YYYY-MM-DD&search[dateDebut][to]=YYYY-MM-DD
      → ISO UNIQUEMENT (les formats dd/mm/yyyy et « année » sont ignorés en silence) ;
      applique sur la DATE DE DÉBUT de la période.

• NOTICE : {BASE}/archive/<id>   (⚠ PAS /notice/<id> : renvoie 404).
    - img#big-image[src] = scan complet (présent seulement si numérisé).
    - .archive__details > div : chaque div = <p>LABEL</p><p>VALUE</p>
      → Description, Période, Type de document, Auteur, Theme, Société, Lieux (optionnel),
        Référence du document.

• RÉSULTATS (cartes div.result) : a[href^="/archive/"] → id ; .result__description ;
  .result__dates → Période ; .result__type ; .result__col--image img[src] → image
  (présent SEULEMENT si numérisé) ; .result__error « Cette archive n'a pas encore été
  numérisée ! » (présent SEULEMENT si NON numérisé). Filtre : numérisé = image ET pas d'erreur.

• DROITS : afficher uniquement les métadonnées + lien vers la notice ; ne jamais copier/
  réhéberger l'image. RIGHT_TEXT ci-dessous.

PERTINENCE « PHRASE » — Rosalie 1932-1933 / record 300 000 km Montlhéry 1933
----------------------------------------------------------------------------
• COUVERTURE OUI : ~543 items NUMÉRISÉS de photos promotionnelles d'ÉPOQUE de la Rosalie
  (Période PLAGE 1928-1933, Société « 3. Citroën / André Citroën SA »), desc. du type
  « … réalisation de prises de vues avec une Rosalie coupé/Berline et un ou deux
  mannequins » (la voiture EST dans la photo). Ex. 115118, 115753. + affiche 92058 (1934).
• CAVEAT : l'item EXACT du record de Montlhéry (18779 « Records de la Rosalie Citroën à
  Montlhéry », 1933, Circuit de Montlhéry) EXISTE mais N'EST PAS numérisé (aucune image).
  La photo précisément du record 300 000 km/134 j n'est donc pas dispo numérisée.

⚠ DEUX CAUTIONS D'IMPLÉMENTATION (vérifiées)
-------------------------------------------
1. NE PAS scoper par société : search[societe] = exact-match sur la chaîne multi-valeurs
   « 3. Citroën / … » → droppe des items. Rechercher en free-text.
2. NE PAS appliquer un filtre date strict 1932-1933 : la série promo Rosalie porte une
   Période de PLAGE 1928-1933 (début=1928) → un filtre strict la droppe (0 numérisé sur
   1932-33). Chercher « Rosalie » en free-text, ou filtre large (from=1928).

API (lecture seule) : build_search_url(), parse_results(), search(), fetch_item(), resolve().
"""
import re
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

BASE = "https://www.archives-terreblanche.fr"
UA = ("MnemosyneBot/1.0 (moteur de recherche d'images d'archives; "
      "contact archivist.mnemosyne@gmail.com)")
HEADERS = {"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"}
RIGHT_TEXT = ("Tous droits réservés (L'Aventure Peugeot Citroën DS / "
              "Centre d'Archives de Terre Blanche)")
_PACE = 0.4  # secondes entre requêtes (politesse)


def _get(url, timeout=30):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def _clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def _text(el):
    return _clean(el.get_text(" ", strip=True)) if el else ""


def build_search_url(query, group_type=1, page=1, date_from=None, date_to=None):
    """URL de recherche. date_* en ISO (YYYY-MM-DD) UNIQUEMENT (filtre sur date de début)."""
    parts = [f"search%5Bsearch%5D={quote(query)}",
             f"search%5BgroupTypeElement%5D={group_type}"]
    if date_from:
        parts.append(f"search%5BdateDebut%5D%5Bfrom%5D={quote(date_from)}")
    if date_to:
        parts.append(f"search%5BdateDebut%5D%5Bto%5D={quote(date_to)}")
    parts.append(f"page={page}")
    return f"{BASE}/recherche?" + "&".join(parts)


def parse_results(html):
    """Parse une page de résultats -> liste de dicts (cartes div.result)."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for c in soup.select("div.result"):
        a = c.select_one('a[href^="/archive/"]')
        if not a:
            continue
        iid = a["href"].rstrip("/").rsplit("/", 1)[-1]
        img = c.select_one(".result__col--image img")
        err = c.select_one(".result__error")
        src = img.get("src") if img else None
        image = (BASE + src) if (src and src.startswith("/")) else src
        out.append({
            "id": iid,
            "url": f"{BASE}/archive/{iid}",
            "digitized": bool(image) and not bool(err),
            "description": _text(c.select_one(".result__description")),
            "period": _text(c.select_one(".result__dates")),
            "type": _text(c.select_one(".result__type")),
            "image": image,
            "error": _text(err) if err else None,
        })
    return out


def search(query, group_type=1, max_pages=1, date_from=None, date_to=None,
           digitized_only=False):
    """Recherche paginée. digitized_only=True ne garde que les notices numérisées."""
    results = []
    for page in range(1, max_pages + 1):
        url = build_search_url(query, group_type, page, date_from, date_to)
        cards = parse_results(_get(url).text)
        if not cards:
            break
        results.extend(cards)
        if page < max_pages:
            time.sleep(_PACE)
    if digitized_only:
        results = [r for r in results if r["digitized"]]
    return results


def fetch_item(item_id):
    """Détail complet d'une notice /archive/<id> (métadonnées + image si numérisée)."""
    url = f"{BASE}/archive/{item_id}"
    soup = BeautifulSoup(_get(url).text, "html.parser")
    details = {}
    for div in soup.select(".archive__details > div"):
        ps = div.find_all("p")
        if len(ps) >= 2:
            details[_text(ps[0])] = _text(ps[1])
    img = soup.select_one("img#big-image")
    src = img.get("src") if img else None
    image = (BASE + src) if (src and src.startswith("/")) else src
    return {
        "id": item_id,
        "url": url,
        "digitized": bool(image),
        "image": image,
        "title": details.get("Description"),
        "period": details.get("Période"),
        "type": details.get("Type de document"),
        "author": details.get("Auteur"),
        "theme": details.get("Theme"),
        "society": details.get("Société"),
        "place": details.get("Lieux"),
        "reference": details.get("Référence du document"),
        "rights": RIGHT_TEXT,
        "details": details,
    }


def resolve(query, date_from=None, date_to=None, max_pages=3, digitized_only=True,
            detail_top=0):
    """Recherche + (option) détail des N premiers. Pour le résolveur Mnemosyne."""
    results = search(query, max_pages=max_pages, date_from=date_from,
                     date_to=date_to, digitized_only=digitized_only)
    for r in results[:detail_top]:
        r["detail"] = fetch_item(r["id"])
        time.sleep(_PACE)
    return results


if __name__ == "__main__":
    # Démo : la série promo Rosalie d'époque (ne PAS filtrer strictement 1932-33).
    items = search("Rosalie", max_pages=1, digitized_only=True)
    print(f"{len(items)} notices numérisées (page 1) pour 'Rosalie'")
    for r in items[:3]:
        print(f'  {r["id"]} [{r["period"]}] {r["description"][:60]} -> {r["image"]}')
    rec = fetch_item("18779")
    print("Record Montlhéry 18779 numérisé ?", rec["digitized"],
          "| lieu:", rec["place"])
