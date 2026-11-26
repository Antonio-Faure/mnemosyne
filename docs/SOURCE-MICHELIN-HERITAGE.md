# Source L'Aventure Michelin — état de l'accès (aucune collection en ligne)

Statut : **aucune collection en ligne, aucun accès programmatique — pas de connecteur.**
Cette note documente la vérification menée pour la mission de source #557 (demande
du Résolveur, phrase `yt_01grGKLcVOc_74` : la reprise/restructuration de Citroën par
Michelin en 1934-1937 — plan de sauvetage, contrôle de Pierre Michelin,
réorganisation de l'usine du quai de Javel, licenciements). Verdict : la source
demandée (`michelin_heritage`, URL `https://www.aventure-michelin.com`) **n'existe
pas** et aucune collection photographique interrogeable ne couvre l'événement.
On n'ajoute **ni descripteur, ni connecteur, ni test** : un descripteur sans
connecteur ne produirait aucun résultat (source fantôme). Le Résolveur ne doit pas
être réveillé en croyant à une source ajoutée.

## La demande

- Mission de source #557, demandée par le Résolveur pour la résolution `yt_01grGKLcVOc_74`.
- Faits visés : Michelin, acquéreur qui impose en 1934-1935 le plan de
  sauvetage/restructuration de Citroën (contrôle de Pierre Michelin,
  réorganisation de l'usine du quai de Javel, licenciements).
- Le catalogue actuel ne contient aucune image 1934-1937 de cet épisode : la seule
  photo d'usine Citroën/Javel (Agence Rol 1928) est déjà employée par une autre
  phrase, et les autres clichés (obus 1915) sont anachroniques.
- URL fournie par le Résolveur : `https://www.aventure-michelin.com` — **ne résout
  pas** (NXDOMAIN).

## L'institution

L'Aventure Michelin — espace patrimonial du groupe Michelin à Clermont-Ferrand.
Le vrai site du musée est `https://laventure.michelin.com` (WordPress, site
**visiteur**). Le patrimoine du groupe est présenté par une frise chronologique sur
`michelin.com` (`/groupe/histoire`, `/en/group/heritage`). La « collection
historique Michelin » est **physique** (objets, affiches, pneus, véhicules en
réserves), non publiée en ligne.

## Vérification (2026-11-26 — agent navigateur, `fetch_url`, exploration directe)

| Canal | Constat | Usage |
|---|---|---|
| `aventure-michelin.com` et variantes (`www.`, `.fr`, `laventuremichelin.*`) | NXDOMAIN ; le `.fr` répond au DNS mais le serveur ne répond jamais (timeout) | URL de la demande inexistante |
| `laventure.michelin.com` (vrai site musée) | WordPress visiteur ; sitemaps = pages/rubriques + `download_document` (PDF) + news ; **aucun** type de contenu collection/objet/photo ; `/wp-json/wp/v2/types` → HTTP 401 | pas de catalogue d'images |
| `michelin.com/groupe/histoire` (frise patrimoine) | SPA de marketing : un chapitre 1935 « Michelin, Citroën, and the 2CV » (rachat + programme TPV/2CV) mais les images sont des prospectus années 1950 (pneu X + 2CV) et un prototype 2CV 1938 — **pas** Javel 1934-37 ni les licenciements ; **non interrogeable** (pas de recherche/API/IIIF/URL par item) | illustratif, pas une source |
| Sous-domaines `archives`/`patrimoine`/`photothèque`/`media`/`photo`/`heritage`/`collection`… `.michelin.com` | tous NXDOMAIN ; chemins `/patrimoine`, `/heritage`, `/espace-presse` → 404 | pas de banque d'images |
| Collection historique Michelin (Stéphane Nicolas) | **physique** (réserves), non publiée en ligne | inaccessible |

## Conséquence (politique d'accès aux images)

- **Aucun accès programmatique** (API REST, IIIF, SRU, OAI-PMH, JSON) : confirmé.
- **Aucun catalogue en ligne** à interroger, donc **aucune cible** pour une lecture
  automatique des pages publiques : il n'y a rien à lire.
- Conséquence : **pas de connecteur** `michelin_heritage`. On n'ajoute pas de source
  fantôme au registre des sources, et le Résolveur doit être considéré comme déjà
  servi (ou non) par les sources ci-dessous.

## Où sont réellement les photos de l'événement (sources déjà au catalogue / pistes séparées)

L'épisode Michelin-Citroën 1934-1937 relève de la **presse** et de l'**archive**, pas
du fonds Michelin :

- **`gallica_agences_photos` (déjà au catalogue, active)** — photographies des
  agences de presse (Rol / Meurisse / Mondial), `protocol: sru` + images IIIF,
  **accès 100 % officiel et programmatique**. Ses graines couvrent exactement
  l'événement : « Citroën usine quai de Javel », « Citroën Traction Avant 1934 »,
  « agence photographique presse automobile 1930 ». C'est la vraie piste pour cette
  phrase. ⚠ constat déjà documenté : `gallica.bnf.fr/SRU` renvoie **HTTP 403** (WAF)
  depuis l'IP de l'agent — blocage infrastructurel (IP/ASN), pas un bug de
  connecteur ; à réévaluer depuis une IP de production (ADR #15). **Ne pas
  contourner le 403.**
- **`archives_paris` (déjà au catalogue, active)** — Arkothèque « ad75 », JSON
  public + IIIF v2 ; câblée au **niveau territoire** (Javel / quai de Grenelle /
  15e arr.) ; « Citroën » = 0 photo (vérifié), ne promet pas l'usine du quai de Javel.
- **Fonds Peugeot / Citroën (L'Aventure Peugeot Citroën DS, Centre d'Archives Terre
  Blanche)** — piste séparée (missions #544 / #553), lecture automatique des pages
  publiques soumise à autorisation ; **consentement en attente** (voir
  `docs/SOURCE-CITROEN-HERITAGE.md`).

## Décision

- **Aucun ajout côté Michelin** pour cette phrase (pas de descripteur, pas de
  connecteur, pas de test) : il n'existe aucune collection en ligne exploitable.
- La couverture de l'événement passe par les sources de presse déjà présentes ; leur
  403 est un problème d'infrastructure IP à traiter côté exploitation, pas une source
  manquante.
- Un e-mail au « service patrimoine » de L'Aventure Michelin reste théoriquement
  possible mais **sans objet aujourd'hui** : il n'y a aucun catalogue numérique
  auquel accéder, et la collection est physique.

## Note de recherche

La recherche détaillée de l'agent navigateur est versionnée dans
`harness/helpers/michelin_heritage_research.py` (PR #184, helpers uniquement). Cette
note (`docs/`) fait foi pour la décision côté code.
