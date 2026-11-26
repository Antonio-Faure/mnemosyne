# Mission de source — L'Aventure Michelin (musée Michelin, Clermont-Ferrand) : état de l'accès

Statut : **en attente d'autorisation — pas encore de connecteur.** Cette note
documente la recherche d'accès pour la mission de source **#555** (demande du
Résolveur, phrase `yt_01grGKLcVOc_73` : « *Exsangue, André Citroën finira par se
tourner vers son créancier principal, Michelin, qui signera avec lui une
convention donnant un large contrôle à Pierre Michelin, le fils d'Édouard* »).

L'image attendue doit montrer **Michelin / Pierre Michelin / la prise de
contrôle de Citroën par Michelin en 1934-35**. Le registre n'a **aucun** portrait
de Pierre Michelin ni photo de l'accord Citroën-Michelin : les recherches
« Pierre Michelin » et « André Citroën Michelin 1935 » ne renvoient que du bruit
moderne (panneaux routiers Michelin, architecte Nicolas Michelin, portrait
d'André Michelin 1898). Les portraits d'Édouard et Pierre Michelin et les photos
de la reprise de Citroën en 1935 relèvent du patrimoine historique Michelin.

## L'institution

**L'Aventure Michelin** (Clermont-Ferrand) est le musée / parcours Michelin. Les
portraits d'Édouard et Pierre Michelin et les photographies de la reprise de
Citroën (1934-35) sont détenus par le **service du patrimoine historique
Michelin** (interne). Tout droits réservés.

Site officiel vérifié le 2026-11-26 : `https://laventure.michelin.com`
(⚠ l'ancien `www.laventuremichelin.com` est NXDOMAIN).

## Accès constatés (2026-11-26, relevé par l'agent navigateur)

| Canal | Constat | Usage |
|---|---|---|
| Site | WordPress vitrine / visite (page, presse, scolaire, billetterie, boutique) | néant |
| API REST / IIIF / OAI-PMH / JSON / collections | **aucun** — pas d'API, pas de IIIF, pas d'OAI-PMH, pas de JSON de collections | néant |
| `robots.txt` | Disallow vide (crawl autorisé) mais sitemaps (Yoast) = pages visite + PDF pédagogiques + PDF presse ; aucune image d'archive | néant |
| WordPress REST `/wp-json/wp/v2/media` | **401** « Kadence/iThemes Security: REST API access restricted » — endpoints média / posts / pages non publics | néant (non contourné) |
| Sous-domaines `patrimoine.` / `heritage.` / `archives.` / `collection.` | **aucun** | néant |
| Catalogue / photothèque en ligne | **inexistant** ; recherche web = boutique, stock commercial Alamy / Shutterstock / Getty ; Wikimedia Commons = photos du musée visité, **pas** les portraits d'archive | néant |

## Droits

Tout est sous **droits réservés**, détenu en interne par le service du
patrimoine historique Michelin. Aucune licence libre. Aucune image d'archive
n'est exposée publiquement (ni catalogue, ni photothèque en ligne).

## Conséquence (politique d'accès aux images)

- Ce n'est **pas** une source à accès programmatique : aucun canal technique
  public (ni API, ni IIIF, ni OAI-PMH, ni JSON).
- Il n'existe **aucune page publique** portant les images visées : la lecture
  automatique des pages publiques (`protocol: html`) est donc **sans objet** ici
  (rien à lire) — et resterait de toute façon soumise à une autorisation écrite
  (règle « Accès aux images — pas de scraping » ; référence à tracer sous
  `extra.scraping_consent`).
- Seul canal : le service du patrimoine historique Michelin, via l'e-mail
  `contact@laventure.michelin.com` ou le formulaire
  `https://laventure.michelin.com/contact/` (objet « Contacter le service
  patrimoine historique Michelin »). Un accès (API / IIIF / export, ou mise à
  disposition d'images) exigerait une **autorisation écrite**.

## Pourquoi aucun descripteur n'est ajouté (pas de statut « hors ligne »)

Le registre n'a **ni** champ `status` / `access: none` **ni** protocole `none` :
`Protocol` = `{iiif, sru, oaipmh, sparql, rest, html, email}`, et
`tests/test_descriptors.py` exige que **chaque** descripteur de `config/sources/`
construise un connecteur (`build_connector`) — un descripteur sans connecteur
(accès inexistant) ferait **échouer** les tests. Le seul état « enregistré mais
inactif » est `enabled: false`, et il est réservé aux sources **qui ont un
connecteur** et une licence restrictive (13 sources au 2026-11-26, ex. musée
d'Orsay, Belvédère). Une source sans aucun accès ni images ne peut donc pas être
enregistrée, même en `enabled: false`. ⇒ **Aucun descripteur ni connecteur** tant
qu'aucun accès n'existe.

## Décision et prochaines étapes

**Ne pas committer de descripteur ni de connecteur « live »** tant qu'aucun accès
écrit n'est reçu (règle « Accès aux images — pas de scraping »).

1. E-mail d'outreach à `contact@laventure.michelin.com` (ou formulaire), **validé
   par l'opérateur avant envoi**, posant l'unique question de l'**accès
   programmatique** (API, IIIF, export) et, à défaut, la mise à disposition des
   portraits d'Édouard / Pierre Michelin et des photos de la reprise de Citroën
   1934-35. Réponse suivie via `mailwatch`.
2. **Si accord** (accès officiel) :
   - descripteur `config/sources/aventure_michelin.yaml` — `protocol` = le
     protocole officiel fourni (`iiif` / `rest`…), `rights` = « tous droits
     réservés » ; si la licence reste restrictive, `enabled: false` en attendant
     la politique du projet ;
   - connecteur `src/mnemosyne/sources/aventure_michelin.py` normalisant vers
     `Asset` à la frontière du connecteur ; **affichage direct** des images
     depuis l'institution, **jamais** de copie / ré-hébergement ;
   - test mocké dans `tests/` ; enregistrement dans
     `src/mnemosyne/sources/__init__.py` ; mise à jour de `docs/SOURCES.md`.
3. **Si refus** : abandon documenté.

Slug réservé : **`aventure_michelin`** (aucun descripteur existant au 2026-11-26
— vérifié dans `config/sources/`).

## État du registre (pour l'e-mail d'outreach)

Catalogue au 2026-11-26 (relevé dans `config/sources/`) : **74 sources
déclarées, 61 actives, 13 désactivées**. La ligne de synthèse en tête de
`docs/SOURCES.md` indique encore « 71 / 58 / 13 » et est à rafraîchir (les
tableaux détaillés, eux, sont à jour : `tests/test_sources_inventory.py` les
vérifie). Pour l'e-mail, indiquer **61 sources actives**.
