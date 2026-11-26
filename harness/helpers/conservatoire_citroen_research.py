"""
conservatoire_citroen_research — NOTE DE RECHERCHE versionnée (task #559, phrase
yt_01grGKLcVOc_84 : faillite de Citroën 1934-35, assignation de la Compagnie
Franco-Américaine des Jantes Bois, André Citroën ruiné).

Source demandée : « L'Aventure Peugeot Citroën DS — Conservatoire Citroën »
(patrimoine de l'entreprise). Verdict de faisabilité ci-dessous.

Ce module re-vérifie EN DIRECT (lecture seule) l'accès et les droits. Il ne copie
ni n'héberge aucune image. Il expose de petits utilitaires réutilisables
(build_search_url / total_count / parse_results / fetch_item) au cas où un
connecteur serait autorisé plus tard.

====================================================================
VERDICT (vérifié en direct le 2026-11-26 15:11)
====================================================================
1) IDENTITÉ / HÉBERGEMENT DU FONDS
   - Institution : Fonds de dotation Peugeot pour la mémoire de l'histoire
     industrielle (association « L'Aventure Peugeot Citroën DS »). Les
     PHOTOGRAPHIES d'usine/patrimoine Citroën (Javel, ateliers, années 1930) sont
     au Centre d'Archives de Terre Blanche, catalogue public :
         https://www.archives-terreblanche.fr
   - L'URL fournie dans la tâche (https://www.aventure-peugeot-citroen.com/)
     NE RÉSOUT PAS (chrome-error / NXDOMAIN) au 2026-11-26 → inutilisable.
   - Contact officiel (page mentions légales, vérifié) :
         archives-avpcd@laventureassociation.com  (resp. publication : M. Petitgirard)

2) ACCÈS PROGRAMMATIQUE : INEXISTANT (re-vérifié 2026-11-26)
   - /api, /api/, /iiif, /iiif/, /oaipmh, /oai, /manifest, /.well-known/,
     /sitemap.xml, /sitemap_index.xml, /robots.txt  ->  TOUS 404.
   - Seule surface = HTML rendu côté serveur (Symfony/Varnish). Pas d'IIIF, pas
     d'OAI, pas de JSON, pas de sitemap, pas de robots.txt.
   => Seul mode possible = lecture HTML (scrape) des pages publiques, métadonnées
      + lien. Cela relève de la règle `extra.scraping_consent` du dépôt.

3) DROITS DE RÉUTILISATION : TOUS DROITS RÉSERVÉS
   - Mentions légales (https://www.archives-terreblanche.fr/mentions-legales) :
     « Sont protégés par la législation sur le droit d'auteur : … des
       photographies … Et/ou … dessins et modèles … marques : … "CITROËN",
       "double chevron", "PEUGEOT", "DS" …
       A ce titre, toute reproduction, représentation, utilisation, adaptation,
       modification, incorporation, traduction, commercialisation, partielles ou
       intégrales … sont interdites … » (sauf exceptions légales, art. 122-5 CPI).
     « Il est formellement interdit de copier ou reproduire le Site ou toute
       partie de ce Site sur n'importe quel serveur… »
   - Aucune licence libre, aucun domaine public revendiqué. Site « destiné à
     l'information personnelle des internautes ».
   => INTERDIT de copier / réhéberger une image. Au mieux : afficher métadonnées
      + lien vers la notice (comme un moteur de recherche), et même cela suppose
      l'autorisation d'accès programmatique demandée par e-mail.

4) PERTINENCE POUR LA PHRASE (crise 1934-35 / Jantes Bois / André Citroën ruiné)
   - « faillite » -> 0 résultat. « Compagnie Franco-Américaine » / « Jantes Bois »
     -> uniquement des correspondances OR hors sujet (fêtes franco-américaines
     1946, « jantes / bois » génériques). L'ÉVÉNEMENT de crise n'a PAS d'image
     numérisée dans le fonds.
   - Items SUR LE SUJET mais NON numérisés (métadonnée seule, aucune image) :
       * 96611  « L'usine de Javel en 1934 »   (photo datée 1946 ; cote DOS2017FIG-00539)
       * 76921  « André Citroën : portrait »    (1928 ; PI2016FIG-00016)
       * 96582  « Messieurs Citroën & Michelin » (1944)
   - EXEMPLE NUMÉRISÉ le plus proche (période 1934 = année de la crise ; la Traction
     Avant est le modèle dont le coût provoqua la faillite) :
       * 11126  « Traction avant Citroën », 1934, Société « Automobiles Citroën »,
                image publique : /upload/documents/648656-68bb25e6f124e917687105.jpg
                (cote PI2010FIG-11970) — JPEG servi publiquement (magic FF D8 FF E0).
       * 92058  « ROSALIE 8 "des records", une 8 CV Citroën : affiche », 1934.
   => PERTINENCE FAIBLE pour CETTE phrase : le fonds nourrit les requêtes
      « Citroën 1934 » (voitures) mais PAS l'iconographie de la crise / ruine.

5) STATUT CONSENTEMENT
   - E-mail d'autorisation d'accès programmatique déjà envoyé le 2026-11-25 22:45 à
     archives-avpcd@laventureassociation.com (cf. tâche #553). Aucune réponse au
     2026-11-26. => NE PAS activer de connecteur « live » avant un « oui ».

6) DOUBLON À RÉGLER CÔTÉ PRODUIT
   - Le MÊME fonds (archives-terreblanche.fr) a déjà des helpers connecteurs :
     `terre_blanche_archives.py` et `citroen_heritage.py`. La source demandée
     `conservatoire_citroen` = le même catalogue. Ne pas créer une 4e copie :
     consolider / renommer, à trancher par le codeur (config/sources).

--------------------------------------------------------------------
SPÉCIFICATION DESCRIPTEUR prête (si le codeur/opérateur décide d'activer,
p. ex. derrière extra.scraping_consent, comme les autres sources HTML du fonds) :
  key            : conservatoire_citroen
  name           : « L'Aventure Peugeot Citroën DS — Centre d'Archives de Terre Blanche »
  base           : https://www.archives-terreblanche.fr
  protocol       : html (scrape serveur), extra.scraping_consent requis
  search         : GET {base}/recherche?search[search]={q}&search[groupTypeElement]=1&page={n}
                   (groupTypeElement=1 = iconographique ; 20 résultats/page ;
                    total dans un titre « N archives correspondent à votre recherche »)
  date (opt.)    : &search[dateDebut][from]=YYYY-MM-DD&search[dateDebut][to]=YYYY-MM-DD
                   (ISO seulement ; filtre sur date de DÉBUT de période)
  notice         : GET {base}/archive/{id}   (⚠ PAS /notice/{id}) ;
                   image = img#big-image[src] (présent seulement si numérisé) ;
                   métadonnées = .archive__details > div (paires <p>LABEL</p><p>VALUE</p>)
  cartes         : div.result ; lien a[href^="/archive/"] ; .result__description ;
                   .result__dates (période) ; .result__col--image img (si numérisé) ;
                   .result__error « Cette archive n'a pas encore été numérisée ! »
  filtre         : numérisé = présence d'image ET absence de .result__error
  droits         : RIGHT_TEXT « Tous droits réservés… » ; afficher métadonnées + lien,
                   NE JAMAIS copier/réhéberger l'image.
  exemples       : 11126 (Traction avant 1934, numérisé),
                   96611 (Javel 1934), 76921 (portrait André Citroën), 92058 (affiche 1934).
"""
import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

BASE = "https://www.archives-terreblanche.fr"
UA = ("MnemosyneBot/1.0 (moteur de recherche d'images d'archives; "
      "contact archivist.mnemosyne@gmail.com)")
HEADERS = {"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"}
RIGHT_TEXT = ("Tous droits réservés (L'Aventure Peugeot Citroën DS / Fonds de dotation "
              "Peugeot pour la mémoire de l'histoire industrielle). Afficher les "
              "métadonnées + lien uniquement ; ne reproduire ni réhéberger l'image.")

TOTAL_RE = re.compile(r"(\d[\d\s\u00a0]*)\s+archives?\s+correspond", re.I)


def build_search_url(q, group=1, page=1, date_from=None, date_to=None, base=BASE):
    """URL de recherche iconographique. group=1 => photos/affiches."""
    u = (f"{base}/recherche?search%5Bsearch%5D={quote(q)}"
         f"&search%5BgroupTypeElement%5D={group}&page={page}")
    if date_from:
        u += f"&search%5BdateDebut%5D%5Bfrom%5D={date_from}"
    if date_to:
        u += f"&search%5BdateDebut%5D%5Bto%5D={date_to}"
    return u


def total_count(html):
    """Nombre total d'archives annoncé (« N archives correspondent … »), ou None."""
    m = TOTAL_RE.search(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    return int(m.group(1).replace(" ", "").replace("\u00a0", "")) if m else None


def parse_results(html):
    """Liste de dicts depuis une page /recherche. 'digitized' = image ET pas d'erreur."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for c in soup.select("div.result"):
        a = c.select_one('a[href^="/archive/"]')
        if not a:
            continue
        img = c.select_one(".result__col--image img, img")
        err = c.select_one(".result__error")
        dates = c.select_one(".result__dates")
        desc = c.select_one(".result__description")
        out.append({
            "id": a["href"].split("/")[-1],
            "title": (desc.get_text(" ", strip=True) if desc else "")[:200],
            "period": " ".join((dates.get_text(" ", strip=True) if dates else "").split()),
            "image": img.get("src") if img else None,
            "not_digitized": bool(err),
            "digitized": bool(img) and not bool(err),
            "url": BASE + a["href"],
        })
    return out


def fetch_item(item_id, base=BASE):
    """Métadonnées d'une notice /archive/{id} (+ image si numérisée). Lecture seule."""
    h = requests.get(f"{base}/archive/{item_id}", headers=HEADERS, timeout=20).text
    s = BeautifulSoup(h, "html.parser")
    big = s.select_one("#big-image")
    details = {}
    for div in s.select(".archive__details > div"):
        ps = div.select("p")
        if len(ps) >= 2:
            details[ps[0].get_text(strip=True)] = ps[1].get_text(" ", strip=True)
    return {
        "id": str(item_id),
        "image": big.get("src") if big else None,
        "digitized": big is not None,
        "details": details,
        "url": f"{base}/archive/{item_id}",
        "rights": RIGHT_TEXT,
    }
