# Source La Contemporaine (ex-BDIC) — connecteur L'Argonnaute

Statut : **connecteur actif** (`la_contemporaine_argonnaute`), construit **sans
scraping HTML ni contournement d'anti-bot**, sur l'**API JSON par document**.
Demandé par le Résolveur (phrases `yt_01grGKLcVOc_67` puis `yt_01grGKLcVOc_72` :
condition ouvrière et grandes grèves / mouvements sociaux des années 1930 en
Île-de-France). Complète les fonds déjà présents en couvrant l'histoire sociale
et ouvrière du 20ᵉ siècle (grèves, manifestations, monde du travail) — voir la
note de couverture honnête plus bas.

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
   reference_code, description, keywords, image_url (hotlink), thumbnail_url,
   license, record_url}` ;
4. `search(query)` renvoie les seeds pertinents, tronqués à `limit`.

Aucune copie d'image (on renvoie l'URL publique), aucune lecture des pages HTML
du site, aucun contournement d'anti-bot — règle dure respectée.

### Pertinence tolérante aux phrases du Résolveur

La source n'ayant pas de recherche côté serveur, `search` filtre la liste
curatée par **recouvrement lexical** (titre, description, mots-clés, cote,
date). Pour que les phrases longues et fléchies du Résolveur (ex. « ouvriers
Citroën grèves 1930 ») retrouvent bien les photos de grèves des années 1930, ce
recouvrement est rendu tolérant :

- **pluriel ⇄ singulier** : les tokens sont ramenés au singulier (`grèves` =
  `grève`, `ouvriers` = `ouvrier`) ;
- **année ⇄ décennie** : une année à 4 chiffres de la requête retient les
  documents de la même décennie (`1930` retient 1933/1936/1938), le fonds étant
  légendé par la presse et non daté au jour près.

Le filtrage reste **strict** : sans aucun recouvrement, un seed est écarté
(« agriculture moisson » ne renvoie rien ; une recherche hors sujet n'hérite
jamais des photos curatées). Couvert par
`tests/test_la_contemporaine_relevance.py`.

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

Le **fonds** « France, entre-deux-guerres 1918-1939. Photographies » est riche
(grèves, Front populaire, manifestations, monde ouvrier ; cotes PH C1-C5). Le
**connecteur**, lui, n'expose que la liste `seeds` curatée du descripteur :
7 photographies vérifiées en direct (HTTP 200, JSON conforme) —

- grève des Bateliers à Conflans, 1936 (PH C4 03-16) ;
- grève des transports, janvier 1938 (PH C4 03-23) ;
- grève des taxis, 1933 (PH C4 06-05) ;
- grève de la Batellerie terminée, 1936 (PH C4 03-15) ;
- manifestation du Front populaire à la Nation, 1938 (PH C4 03-02) ;
- marcheurs de la faim arrivés à Paris, 1933 (PH C4 06-11) ;
- Paris, usine Citroën, quai de Javel, 1915 (VAL 364/022, Albums Valois).

**Limite honnête** : il n'y a **pas** de photographie isolée « ouvriers de
Citroën / grève Javel 1936 ». Le fonds Citroën propre est fait des albums Valois
(Javel 1915, Première Guerre mondiale) et d'affiches. La valeur réelle de cette
source est donc **« grèves / mouvements sociaux des années 1930 en Île-de-France »**,
**pas** « usines Citroën ». L'hypothèse « ouvriers de Citroën 1930s » du Résolveur
n'est **pas** couverte telle quelle — signalé ici en toute transparence.

## Limite de découverte

Faute d'API de recherche, la couverture réelle dépend des `seeds` curatés (le
connecteur ne peut pas « chercher » dynamiquement dans tout le catalogue). Pour
élargir la couverture, ajouter des seeds (URL notice/média) vérifiées au
descripteur `config/sources/la_contemporaine_argonnaute.yaml` — sans jamais
scraper le HTML de recherche.
