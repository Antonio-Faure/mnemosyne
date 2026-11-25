# Source L'Aventure Peugeot Citroën DS — Centre d'Archives de Terre Blanche

Statut : **accès à demander (scrape HTML sous consentement e-mail)** — pas encore
de connecteur. Note d'accès pour la mission de source #544 (demande du Résolveur,
phrase `yt_01grGKLcVOc_30` : Rosalie lancée en 1932 ; record de 300 000 km en
134 jours en 1933 à l'autodrome de Linas-Montlhéry → besoin d'une photographie
d'**époque 1932-1933** ; le catalogue ne contient que des photos **modernes**
1972-2012 de Rosalie restaurées).

## L'institution

L'Aventure Peugeot Citroën DS — association patrimoniale (musée de Sochaux).
Catalogue d'archives en ligne : **Centre d'Archives de Terre Blanche**,
`https://www.archives-terreblanche.fr`. Site de l'association :
`https://laventure-association.com`.

> NB : l'URL fournie dans la tâche `www.lavenir-peugeot-citroen-ds.fr` ne résout
> pas (NXDOMAIN). Les liens « archives » de l'association aboutissent au Centre
> d'Archives de Terre Blanche, qui sert effectivement les images.

## Accès constatés (2026-11-25, vérifiés par l'agent navigateur)

| Canal | Constat |
|---|---|
| API / IIIF / OAI / OpenSearch (`/api`, `/search.json`, `/oai?verb=Identify`, `/iiif`, `/manifest`, `/sitemap.xml`, `/robots.txt`) | **tous 404 HTML** — application Symfony rendue côté serveur, aucune route de données |
| Recherche | HTML server-rendered : `GET /recherche?search[search]=<q>&search[groupTypeElement]=1&page=<N>` (`groupTypeElement=1` = documents iconographiques) |
| Anti-bot | aucun (requête `requests` + UA descriptif = 200 + `image/jpeg`) |
| robots.txt | 404 (aucune restriction publiée) |

Aucun accès programmatique exploitable : le **seul** canal est le HTML
server-rendered. La note de référence `harness/helpers/la_contemporaine.py`
décrit la même famille (recherche HTML + hotlink de l'asset image public).

## Politique d'accès (règle dure appliquée par les tests)

Le scrape HTML (`protocol: html`) n'est autorisé que pour une **petite structure
sans accès programmatique** ET **après autorisation écrite par e-mail** de lire
les pages publiques, tracée dans le descripteur sous `extra.scraping_consent`
(« e-mail de <expéditeur> du <date> »). Cette règle est **appliquée par les
tests** (`tests/test_sources_inventory.py::test_html_sources_carry_scraping_consent`
et `::test_connectors_do_not_scrape_html_without_consent`). Sans consentement
tracé, **aucun descripteur `protocol: html` ni connecteur parseur HTML ne peut
être ajouté** : les tests échouent et le commit est bloqué (cf.
`docs/FIXES-LOT1.md §3`, où le chemin HTML d'ANMT a été retiré pour cette raison).

## Action en cours

Consentement demandé à l'**agent navigateur** (2026-11-25) : engager la prise de
contact décrite dans `docs/OUTREACH.md` auprès de L'Aventure Peugeot Citroën DS
demandant (1) un éventuel **accès programmatique** (API / IIIF / export) — à
privilégier — ou, à défaut, (2) l'**autorisation de lire automatiquement les
pages publiques** du Centre d'Archives de Terre Blanche. La réponse (expéditeur +
date) sera stockée dans `extra.scraping_consent` pour débloquer l'implémentation.

## Spécification d'implémentation (prête, à appliquer après consentement)

- Descripteur `config/sources/citroen_heritage.yaml` : `protocol: html`,
  `institution: "L'Aventure Peugeot Citroën DS"`, `base_url:
  https://www.archives-terreblanche.fr`, `extra.scraping_consent: "e-mail de … du …"`.
- Connecteur `src/mnemosyne/sources/citroen_heritage.py` :
  - recherche `GET /recherche?search[search]=<q>&search[groupTypeElement]=1&page=<N>` ;
  - cartes `div.result` : `a[href^="/archive/"]` → id ; `.result__description`,
    `.result__dates`, `.result__type` ; vignette `.result__col--image img`
    (89×120) **si numérisé**, précédée de `.result__error` (« pas encore
    numérisée ») sinon → **ne garder que `digitized=true`** ;
  - item `GET /archive/<id>` : `img#big-image` → scan complet
    (`/upload/documents/<hash>.jpg`, ~714×960) ; métadonnées `.archive__details`
    (Description, Période, Type de document, Auteur, Theme, Société, Référence) ;
  - mapping `Asset` : id → `source_asset_id`, Description → `title`/`description`,
    Période → `date_text` (+ `year`), Société/Auteur/Type/Référence → `extra` ;
    `page_url = /archive/<id>`, `image_url = #big-image`, `thumbnail_url = vignette`.
- **Pas** de scope `search[societe]` (match exact multi-valeurs, rate des items) :
  chercher en texte libre sur tout le catalogue (l'institution EST Citroën).
- Droits : « Tous droits réservés (L'Aventure Peugeot Citroën DS / Centre
  d'Archives de Terre Blanche) » ; hotlink de l'image publique + métadonnées +
  lien item, **aucune copie / hébergement / redistribution**.
- Politesse : UA descriptif `mnemosyne`, pacing ~0,4 s, sous-ensemble
  iconographique (`groupTypeElement=1`) uniquement.
- Présence vérifiée (2026-11-25) : figuratif « Rosalie » 1928-1934 = 548 items,
  544 numérisés. Échantillons **numérisés** : 92058 (PI2017FIG-02585, 1934,
  « ROSALIE 8 « des records » … affiche »), 56110 (PI2013FIG-02458, 1933,
  « Championnat féminin Montlhéry 301 »). **Non numérisés à exclure** : 18779
  (PI2010FIG-06201, 1933, « Records de la Rosalie Citroën à Montlhéry »), 49001
  (PI2010FIG-00029). Tests : 92058 remonte AVEC `image_url` ; 18779 filtré/omis.
- Filtre date : porte sur la date de **début** de l'item → un item « 1928-1933 »
  est exclu si `dateDebut[from]=1932` ; chercher en texte libre puis lire les dates.

## Prochaines étapes

1. Réponse de l'institution via l'agent navigateur (`mailwatch`) → consentement
   (`e-mail de <expéditeur> du <date>`) OU accès programmatique.
2. Si accès officiel : connecteur sur l'API. Sinon, avec consentement tracé :
   descripteur + connecteur HTML + tests mockés (92058 numérisé remonte ; 18779
   filtré) + enregistrement dans `src/mnemosyne/sources/__init__.py` + mise à
   jour de `docs/SOURCES.md` + PR.
3. Si refus : abandon documenté (`finish`).
