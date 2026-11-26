# Source Centre d'Archives Terre Blanche (L'Aventure Peugeot Citroën DS) — état de l'accès

Statut : **accès à demander — consentement en attente, pas encore de connecteur.**
Cette note documente la recherche d'accès pour la mission de source #544 (demande
du Résolveur, phrase `yt_01grGKLcVOc_30` : photographies d'époque 1932-1933 de la
Rosalie et du record d'endurance — 300 000 km en 134 jours à l'autodrome de
Linas-Montlhéry en 1933 —, que le catalogue actuel ne couvre qu'en photos
modernes de véhicules restaurés).

## L'institution

L'Aventure Peugeot Citroën DS — association patrimoniale du constructeur. Son
fonds numérisé est exposé par le **Centre d'Archives Terre Blanche**
(`https://archives-terreblanche.fr/`, redirige vers `www.archives-terreblanche.fr`).
Le site indiqué par la demande (`https://www.lavenir-peugeot-citroen-ds.fr/`)
**ne résout plus** (échec DNS à la vérification du 2026-11-25).

## Accès constatés (2026-11-25 — `fetch_url` + exploration de l'agent navigateur)

| Canal | Constat | Usage |
|---|---|---|
| Catalogue HTML `archives-terreblanche.fr` | application web sur mesure (assets `/build/main/…`, Matomo, Adobe Typekit) ; notices rendues en HTML | **seul canal** : la lecture au niveau pièce passe par le HTML |
| `robots.txt`, `sitemap.xml`, `/api` | absents (HTTP 404 aux chemins testés) | pas d'entrée programmatique évidente |
| Motif d'URL `…/notice/<id>` | HTTP 404 → le motif de notice n'est **pas** `/notice/<id>` | motif exact à relever par l'agent navigateur |

D'après l'agent navigateur : le catalogue présente des notices ; l'item **92058**
remonte avec une `image_url`, l'item **18779** est **non numérisé** (à filtrer) ;
il ne faut **pas** restreindre la recherche par société (un filtre exact sur la
société supprime des items).

## Conséquence (politique d'accès aux images)

- Aucun accès programmatique (API REST, IIIF, SRU, OAI-PMH, JSON) trouvé : le
  seul canal est la lecture des pages publiques → **scraper HTML**.
- Un scraper HTML (`protocol: html`) n'est permis qu'**après autorisation écrite**
  de lire les pages publiques, tracée sous `extra.scraping_consent`
  (« e-mail de <expéditeur> du <date> »). Les règles dures et les tests
  `test_html_sources_carry_scraping_consent` /
  `test_connectors_do_not_scrape_html_without_consent` l'imposent : sans
  consentement tracé, **pas de scraper**.
- Prérequis non encore vérifié : la **présence effective** de photographies
  d'époque Rosalie 1932-1933 et du record de Montlhéry dans le fonds (à
  confirmer par l'agent navigateur). Sans ces images, la source ne répond pas à
  la demande du Résolveur.

## Action en cours

L'**agent navigateur** a envoyé le 2026-11-25 (e-mail validé par l'opérateur) une
demande à `archives-avpcd@laventureassociation.com` (Centre d'Archives de Terre
Blanche) posant l'unique question : accès programmatique (1) officiel, ou
(2) autorisation de lire les pages publiques, ou (3) refus. **Consentement en
attente** ; la référence (`e-mail de <expéditeur> du <date>`) ne peut provenir que
de leur réponse — pas de l'e-mail sortant.

## Plan dès réception

1. **Accès officiel** (API/IIIF/export) : connecteur `rest`/`iiif`, sans
   consentement de scraping.
2. **Autorisation de lire les pages publiques** : descripteur
   `config/sources/citroen_heritage.yaml` (`protocol: html` +
   `extra.scraping_consent` renseigné), connecteur
   `src/mnemosyne/sources/citroen_heritage.py` (normalisé en `Asset` ; filtrer
   les notices non numérisées ; **ne pas** sur-filtrer par société), test mocké
   dans `tests/`, enregistrement dans `src/mnemosyne/sources/__init__.py`, mise à
   jour de `docs/SOURCES.md`.
3. **Refus** : abandon documenté (cette note fait foi).

## Informations attendues de l'agent navigateur

- Confirmation de la présence de photos d'époque Rosalie 1932-1933 / Montlhéry
  (avec quelques identifiants d'items et `image_url` si trouvés).
- Motif d'URL de recherche et de notice ; emplacement exact du champ
  `image_url` ; représentation d'une notice « non numérisé » (ex. 18779).
- Référence exacte du consentement à réception.
