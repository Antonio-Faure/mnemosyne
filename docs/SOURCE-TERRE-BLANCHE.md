# Centre d'Archives de Terre Blanche (L'Aventure Peugeot Citroën DS) — abandon documenté

Statut : **abandon documenté (décision opérateur, 2026-11-26) — aucun connecteur
livré, aucun descripteur créé.** Note **unique** consolidant les trois demandes
du Résolveur qui visent le **même fonds** :

| Mission | Phrase | Recherche demandée | Issue |
|---|---|---|---|
| #544 | `yt_01grGKLcVOc_30` | Rosalie / record 300 000 km à Montlhéry (1933) en photo d'époque | trou non comblé (catalogue = photos de véhicules restaurés) |
| #553 | `yt_01grGKLcVOc_72` | ouvriers et usines Citroën (Javel, années 1930) | trou non comblé |
| #559 | `yt_01grGKLcVOc_84` | faillite Citroën 1934-35 / Compagnie Franco-Américaine des Jantes Bois / André Citroën ruiné | trou non comblé (iconographie de crise non numérisée) |

Les anciennes notes `docs/SOURCE-AVENTURE-CITROEN.md` (#553) et
`docs/SOURCE-CITROEN-HERITAGE.md` (#544) ont été fusionnées ici et ne sont plus
que des renvois. **Ne pas créer de nouvelle copie de cette source** (ni
`site_citroen`, ni `conservatoire_citroen`, ni `citroen_heritage`,
`aventure_citroen`…) : ce serait toujours le même catalogue.

## L'institution et le catalogue

L'Aventure (association patrimoniale Peugeot + Citroën + DS) expose son fonds
numérisé via le **Centre d'Archives de Terre Blanche**. Le seul catalogue
consultable en ligne est `https://www.archives-terreblanche.fr` (anciens
domaines `archives-laventurepeugeotcitroends.com` → redirection ; l'URL
`www.aventure-peugeot-citroen.com` de la demande #559 **ne résout pas**,
NXDOMAIN). Application Symfony rendue côté serveur.

## Accès constatés (relevés 2026-11-25 / 2026-11-26, agent navigateur)

| Canal | Constat | Usage |
|---|---|---|
| `/api`, `/iiif`, `/oaipmh`, `/oai`, `/manifest`, `/.well-known/`, `/sitemap.xml`, `/robots.txt` | **404** sur les deux domaines | **aucun accès programmatique** |
| Recherche `GET /recherche?search[search]=…&search[groupTypeElement]=1&page=N` | HTML serveur | lecture des pages publiques seulement après autorisation |
| Fiche `GET /archive/{id}` | HTML ; champs Description, Période, Type, Société, Lieux, Référence (cote stable, ex. `DOS2017FIG-01128`) | lecture après autorisation |
| Images `/upload/documents/{n}-{hash}.jpg` | JPEG ~1280 px, parfois plusieurs par fiche | **affichage direct** seulement, **jamais de copie** |
| Fiches non numérisées | message « Cette archive n'a pas encore été numérisée ! » | métadonnée seule → à exclure de toute exposition d'image |

Volumétrie (filtrée société « André Citroën SA » / « Automobiles Citroën ») :
environ **3 048 documents iconographiques**, dont une **faible part numérisée**.

## Droits

**Tous droits réservés.** Photos + marques CITROËN / DS / PEUGEOT protégées.
Les mentions légales interdisent « toute reproduction, représentation,
utilisation, adaptation, modification, incorporation, traduction,
commercialisation » hors exceptions légales, et « de copier ou reproduire le
Site ». Le site vend d'ailleurs des reproductions (boutique). **Aucune licence
libre.** Au mieux : affichage de métadonnées + lien vers la fiche ; **jamais**
d'hébergement, de copie ou de miroir d'image.

## Consentement

E-mail envoyé le **2026-11-25 22:45** par l'agent navigateur à
`archives-avpcd@laventureassociation.com` (objet « Mnemosyne — ajouter les
images d'archives du Centre d'Archives de Terre Blanche… »), demandant l'accès
programmatique et, à défaut, l'autorisation de lire automatiquement les pages
publiques. **Aucune réponse** à ce jour. **Ne pas relancer.** Cet e-mail sortant
**n'est pas** une autorisation : aucun `extra.scraping_consent` n'est tracé, et
il ne pourrait provenir que d'une réponse de l'institution.

## Pertinence pour les phrases visées

Faible pour les trois. Cas #559 en détail : « faillite » → 0 ; « Compagnie
Franco-Américaine » / « Jantes Bois » → correspondances hors sujet. Les pièces
sur la crise 1934-35 sont en **métadonnée seule (non numérisées)** :

| ID | Titre | Statut |
|---|---|---|
| 96611 | « L'usine de Javel en 1934 » | non numérisé |
| 76921 | Portrait d'André Citroën (1928) | métadonnée (portrait, pas la faillite) |
| 96582 | « Citroën & Michelin » (1944) | non numérisé |
| 142770 | Usine Javel, vue des terrains avant construction | non numérisé |

Seuls documents numérisés proches de 1934 = publicité/affiche voiture —
**11126** « Traction Avant Citroën » (1934) et **92058** « Rosalie 8 des
records » (affiche 1934) — sans rapport avec la faillite. Autres numérisés vus :
96272 réfectoire usine Javel (1941), 96235 chaîne de châssis (1940), 99856
chaîne DS (1955). **Donc, même avec un accès accordé, l'iconographie de la
crise n'existe pas en ligne : ce fonds ne comble pas le trou de couverture.**

## Décision (opérateur, #559)

**Abandon documenté.** Aucun descripteur, aucun connecteur, aucun test, aucune
entrée dans `docs/SOURCES.md`. Motifs cumulatifs :

1. **Pas de consentement écrit** → la règle dure interdit tout scraper HTML
   (`protocol: html` exige `extra.scraping_consent`, vérifié par
   `tests/test_sources_inventory.py::test_html_sources_carry_scraping_consent`).
2. **Droits réservés, pas de licence** → une intégration ne pourrait exposer que
   métadonnées + lien, jamais d'image ; intérêt produit marginal.
3. **Pertinence faible / non numérisé** → l'iconographie de la crise 1934-35
   n'est pas en ligne ; la source ne comble pas le trou visé.
4. **Doublon** → #544 et #553 avaient déjà conclu à l'attente sans connecteur ;
   #559 est le troisième passage sur le même fonds.

**Ne pas réveiller le Résolveur pour cette source** : le trou reste non
comblable par ce fonds. Pour la faillite de 1934-35, chercher une alternative
publique libre (presse numérisée 1934 sur Gallica, Agence Rol, etc.), hors du
périmètre de cette note.

## Slug réservé (si l'institution accorde un jour un accès écrit)

Un **seul** identifiant pour ce fonds : **`terre_blanche`** (hôte réel
`archives-terreblanche.fr`). Les libellés `citroen_heritage` (#544),
`aventure_citroen` (#553) et `conservatoire_citroen` (#559) sont des **alias**
du même fonds — ne pas les matérialiser séparément.

Si (et seulement si) un écrit arrive :

- **Accès officiel** (API/IIIF/export) → connecteur `iiif`/`rest`, sans
  consentement de scraping.
- **Autorisation de lire les pages publiques** → descripteur
  `config/sources/terre_blanche.yaml` (`protocol: html` +
  `extra.scraping_consent` = « e-mail de <expéditeur> du <date> »), connecteur
  `src/mnemosyne/sources/terre_blanche.py` : `/recherche` (documents
  iconographiques) puis `/archive/{id}` ; n'exposer `/upload/documents/…`
  qu'en **affichage direct** et **uniquement** pour les fiches réellement
  numérisées ; normaliser en `Asset` à la frontière ; test mocké ;
  enregistrement dans `src/mnemosyne/sources/__init__.py` ; mise à jour de
  `docs/SOURCES.md`.
- **Refus** → cet abandon fait foi.
