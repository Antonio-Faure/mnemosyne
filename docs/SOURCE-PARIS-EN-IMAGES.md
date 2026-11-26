# Source Paris en Images — Paris Musées Collections (photothèque historique de la Ville de Paris)

Statut : **connecteur actif** (`paris_en_images`), construit **sans scraping
HTML ni contournement d'anti-bot**, sur le **manifeste IIIF v2 par œuvre** et une
liste `seeds` curatée. Demandé par le Résolveur (phrase `yt_01grGKLcVOc_84` :
tribunal de commerce de Paris — île de la Cité — et usine de Javel / 15ᵉ
arrondissement, années 1930). Voir la note de couverture honnête plus bas.

## L'institution

« Paris en Images » désigne les **collections photographiques historiques de la
Ville de Paris**, aujourd'hui publiées par **Paris Musées**. L'ancien domaine
`parisenimages.fr` **redirige (301/302) vers `paris.fr`** : il n'y a plus de
photothèque dédiée. Les œuvres vivent sur
`https://www.parismuseescollections.paris.fr` et leur API IIIF sur
`https://apicollections.parismusees.paris.fr` — le **même hôte** que la source
`paris_musees` (connecteur générique IIIF mono-manifeste). `paris_en_images` est
la variante « photothèque historique » focalisée photographies, à découverte par
`seeds`, comme `gallica` / `gallica_agences_photos` / `gallica_estampes_affiches`
scindent une même institution. Archives de Paris (`archives.paris.fr`) est une
**autre institution** (source distincte) : ne pas confondre.

## Accès constatés (vérifiés en direct)

| Canal | Constat | Usage |
|---|---|---|
| `parisenimages.fr` | 301/302 vers `paris.fr`, plus de photothèque | **PAS utilisé** (domaine mort) |
| Recherche `/fr/recherche` | HTML rendu côté serveur (parsing par `<article>`) | **PAS utilisé** (scraping HTML interdit : IIIF existe) |
| GraphQL `/graphql` | **403**, exige un jeton `auth-token` par compte | **PAS utilisé** (compte non créable) |
| **Manifeste IIIF v2 par œuvre** `/iiif/<visuel_id>/manifest` | 200, **sans authentification** | **canal retenu** (accès programmatique officiel) |
| Collection IIIF | aucune Collection énumérable | pas de découverte par IIIF |
| API de recherche publique | aucune (ni REST ni SRU/OAI) | pas de recherche par mot-clé par programme |

Aucune copie d'image : on renvoie l'URL publique fournie par le manifeste
(**affichage direct**), aucune lecture des pages HTML du site, aucun
contournement d'anti-bot — règle dure respectée.

## Modèle d'accès du connecteur (`protocol: iiif`)

Faute d'API de recherche publique et de Collection IIIF énumérable, la
découverte passe par une **liste `seeds` curatée** dans le descripteur. Chaque
seed est une œuvre IIIF au format `"<visuel_id>|<droits>|<url_fiche>"` :

- `visuel_id` : identifiant interne du manifeste (`/iiif/<visuel_id>/manifest`) ;
- `droits` : `open` (CC0 / domaine public, vérifié sur la fiche) ou `restricted` ;
  vide → détection via le champ `license`/`rights` du manifeste ;
- `url_fiche` : lien public vers la fiche (provenance / droits).

`search(query)` renvoie les seeds pertinents (recouvrement de tokens après
suppression des accents), tronqués à `limit`. Pour chaque seed retenu, on résout
le manifeste et on normalise vers un `Asset` (résultat) : `{source, id,
title, date_from, date_to, reference_code, collection, description, keywords,
image_url, thumbnail_url, license, record_url}`.

## Droits par fiche (à afficher tel quel + renvoyer à la fiche)

Les droits **varient par œuvre** : certaines sont en **CC0 / domaine public**,
d'autres « tous droits réservés ». Le connecteur applique la règle suivante :

- **fiche ouverte (CC0 / domaine public)** : image **pleine résolution**
  exposée (affichage direct depuis le manifeste) avec **mention de
  l'institution** « CC0 Paris Musées / <musée> » ;
- **fiche restreinte** : on ne renvoie que la **vignette** et le **lien vers la
  fiche**, **jamais** l'image pleine résolution d'une œuvre protégée.

On n'affirme pas un domaine public non vérifié : le hint `droits` du seed prime,
puis on retombe sur le champ `license`/`rights` du manifeste.

## Couverture (honnête, pour le Résolveur)

Le catalogue Paris Musées répond bien aux mots-clés « tribunal de commerce »
(≈ 191 résultats), « usine de Javel » (≈ 6), « île de la Cité » (≈ 1 385) — mais
ces comptes viennent de la recherche HTML, **non utilisée** par le connecteur.
**Un seul seed vérifié** est présent à ce jour : un **dessin** (Fichot) de
l'escalier du tribunal de commerce, **CC0** (`visuel_id` 320017427), qui répond
au mot-clé « tribunal de commerce ». Les **photographies des années 1930** du
tribunal sont, elles, **sous droits** (vignette + lien vers la fiche seulement),
et les fonds **Javel / 15ᵉ** restent à curer.

## Limite de découverte

Faute d'API de recherche, la couverture réelle dépend des `seeds` curatés (le
connecteur ne peut pas « chercher » dynamiquement dans le catalogue). Pour
élargir la couverture (photos 1930 du tribunal, Javel, 15ᵉ), ajouter des seeds
`"<visuel_id>|<droits>|<url_fiche>"` au descripteur — **aucune modification de
code** n'est nécessaire.
