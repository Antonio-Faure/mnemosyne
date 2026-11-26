# Source La Contemporaine (ex-BDIC) — connecteur L'Argonnaute

Statut : **connecteur actif** (`la_contemporaine_argonnaute`), construit **sans
scraping HTML ni contournement d'anti-bot**, sur l'**API JSON par document**.
Demandé par le Résolveur (phrase `yt_01grGKLcVOc_67` : condition ouvrière et
grandes grèves, Citroën Javel 1933/1936). Complète les fonds déjà présents en
couvrant l'histoire sociale et ouvrière du 20ᵉ siècle (grèves, manifestations,
monde du travail) — voir la note de couverture honnête plus bas.

## L'institution

La Contemporaine (ex-BDIC), Université Paris Nanterre — bibliothèque, archives
et musée d'histoire contemporaine. Ses documents numérisés sont dans
**L'Argonnaute**, sa bibliothèque numérique (`https://argonnaute.parisnanterre.fr/`
— noter que `argonnaute.contemporaine-parisnanterre.fr` ne résout pas).

## Accès constatés (vérifiés en direct)

| Canal | Constat | Usage |
|---|---|---|
| Recherche du site `/search/results` | HTML rendu serveur ; **anti-bot hCaptcha** (`data-captcha="hcaptcha"`) | **PAS utilisé** (scraping HTML + anti-bot interdits) |
| **API JSON par document** `/visualizer/api?arkName=<ARK>&uuid=<UUID>` | répond 200 ; `media[0].record{title, referenceCode, description, period.boundaries, locationKeywords}` + `media[0].location{original, thumb, iiif:null}` | **canal retenu** (accès programmatique officiel) |
| IIIF | `isIIIFEnabled=false`, `location.iiif=null`, chemins IIIF en 404 | **pas de IIIF** |
| Recherche JSON | aucune API `/api/search`, aucun index Solr/Elastic public | pas de recherche par mot-clé par programme |
| OAI-PMH `/oai-pmh` | répond mais `oai_dc` minimal (identifiants seuls), pas de recherche ; **interdit par robots.txt** | non utilisé |
| Images | `/images/<UUID>.jpg` (original), `/images/<UUID>_thumbnail.jpg` | **hotlink** : on renvoie l'URL publique, aucune copie |

robots.txt : seuls `/private/`, `/oai-pmh`, `/user/` sont interdits ; le reste
(dont `/visualizer/api`, `/images/`) est autorisé. L'User-Agent descriptif du
projet (mnemosyne) n'est pas dans la liste des robots bloqués nommément.

## Modèle d'accès du connecteur (`protocol: rest`)

L'API n'expose que le **JSON par document** : il n'y a **pas** d'API de recherche,
donc pas de découverte par mot-clé au niveau serveur. Le connecteur utilise une
**liste `seeds` curatée** (une URL notice/média par photographie) dans le
descripteur :

1. chaque seed est résolu en `(arkName, uuid)` (regex sur `/ark:/<naan>/<ark>/<uuid>`) ;
2. `GET /visualizer/api?arkName=<ARK>&uuid=<UUID>` → métadonnées du média ;
3. normalisation vers un `Asset` : `{source, id=uuid, title, date_from, date_to,
   reference_code, collection, description, keywords, image_url (hotlink),
   thumbnail_url, license, record_url}` ;
4. `search(query)` renvoie les seeds pertinents (recouvrement de tokens après
   suppression des accents), tronqués à `limit`.

Aucune copie d'image (on renvoie l'URL publique), aucune lecture des pages HTML
du site, aucun contournement d'anti-bot — règle dure respectée.

## Droits / licence (à afficher tel quel + renvoyer à la notice)

Licence globale (institution) : pour les œuvres du **domaine public**, la
réutilisation est libre et gratuite sous **Licence Ouverte / Open Licence**
(attribution requise) ; les documents protégés sont « tous droits réservés » et
soumis à l'accord préalable de La Contemporaine. Il n'existe **pas** de champ
« droits » machine-readable par item ni de facette dédiée : le connecteur affiche
la licence connue (« Licence Ouverte / Open Licence — voir la notice »), attribue
« La Contemporaine / L'Argonnaute » et renvoie **toujours** à `record_url`. On
n'affirme pas un domaine public non vérifié.

## Couverture (honnête, pour le Résolveur)

Avec `facet_media=image` : `grèves 1936` ≈ 235 photos, `Front populaire` ≈ 339
(299 photos), `manifestation ouvriers` ≈ 277 (231 photos), `métallurgistes` ≈ 213,
`Citroën` ≈ 102, `usines Citroën` ≈ 90. Excellente couverture **photo** des
grandes grèves et de la condition ouvrière des années 1930 (fonds « France,
entre-deux-guerres 1918-1939. Photographies », cote PH C1-C5).

**Mais** il n'y a **pas** de photographie isolée « grève Citroën Javel 1936 » :
le fonds Citroën propre est fait des albums Valois (Javel 1915, Première Guerre
mondiale) et d'affiches. La source comble donc le trou « condition ouvrière /
grèves des années 1930 », et non précisément « Citroën Javel 1936 » — signalé
ici en toute transparence.

## Limite de découverte

Faute d'API de recherche, la couverture réelle dépend des `seeds` curatés (le
connecteur ne peut pas « chercher » dynamiquement dans le catalogue). Pour
élargir la couverture, ajouter des seeds (URL notice/média) au descripteur.
