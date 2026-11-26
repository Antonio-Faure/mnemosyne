# Source L'Aventure Citroën / Centre d'Archives de Terre Blanche — état de l'accès

Statut : **en attente d'autorisation — pas encore de connecteur.** Cette note
documente la recherche d'accès pour la mission de source #553 (demande du
Résolveur, phrase `yt_01grGKLcVOc_72` : photographies d'ouvriers et d'usines
Citroën — quai de Javel, années 1930). Le fonds photographique visé complète
l'unique photo Citroën déjà présente au registre (Agence Rol, « usines Citroën,
ouvriers assemblés dans l'usine », 1923, utilisée par la tâche #470).

## L'institution

L'Aventure (association, Aulnay-sous-Bois) est le conservatoire historique
Citroën & DS. Les photos de véhicules se trouvent au Conservatoire Citroën & DS ;
les photos d'usine (Javel, chaînes, ateliers, ouvriers) relèvent du **Centre
d'Archives de Terre Blanche**, de la même association (Peugeot + Citroën + DS),
géré par le Fonds de dotation Peugeot (1 rue du Stade, 25310 Hérimoncourt).
Terre Blanche annonce environ 4,5 millions de photographies, mais n'en expose
qu'une **partie en ligne**.

| Ressource | URL | Constat |
|---|---|---|
| Association | `https://laventure-association.com` | pages descriptives |
| Conservatoire Citroën & DS | `https://laventure-association.com/laventure-citroen/le-conservatoire-de-laventure-citroen-ds/` | ~300 véhicules, pas de recherche d'images |
| **Centre d'Archives de Terre Blanche** | `https://www.archives-terreblanche.fr` | catalogue HTML (Symfony + Varnish, rendu serveur) ; ancien domaine `archives-laventurepeugeotcitroends.com` redirige ici |

## Accès constatés (2026-11-26, relevé par l'agent navigateur)

| Canal | Constat | Usage |
|---|---|---|
| API REST / IIIF / OAI-PMH / JSON / sitemap / robots.txt | **404** sur tout — aucun accès programmatique | néant |
| Recherche `GET /recherche` | HTML ; paramètres `search[search]`, `search[groupTypeElement]` (1 = documents iconographiques), `search[societe]`, `search[dateDebut][from|to]`, `search[dateFin][from|to]` | lecture automatique des pages publiques **uniquement après autorisation** |
| Fiche `GET /archive/{id}` | champs Description, Période (jj/mm/aaaa), Type de document, Thème, Société, Lieux (p. ex. « Sites du Groupe en France / Usine de Javel », parfois vide), Référence (= cote stable, p. ex. `DOS2017FIG-01128`) | lecture automatique après autorisation |
| Images `/upload/documents/{n}-{hash}.jpg` | JPEG ~1280 px, éventuellement plusieurs par fiche | **affichage direct** seulement, **aucune copie** |
| Fiches non numérisées | message « Cette archive n'a pas encore été numérisée ! » → métadonnée seule | à exclure : n'exposer une image **que** pour les fiches réellement numérisées |

Volumétrie (relevée) : filtre société **« 3. Citroën / André Citroën SA »**
(aussi « 3. Citroën / Automobiles Citroën ») — environ **3 048 documents
iconographiques** taggés André Citroën SA.

## Exemples numérisés vérifiés (2026-11-26, données)

| ID | Titre | Période | Référence | Taille |
|---|---|---|---|---|
| 96272 | Réfectoire de l'usine de Javel (3 images) | 1941 | DOS2017FIG-00446 | 1280x846 |
| 96235 | Chaîne de châssis | 09/1940 | DOS2017FIG-00392 | 1280x939 |
| 97455 | Usine. — La chaîne | 06/1951 | DOS2017FIG-01128 | 1280x924 |
| 97422 | Vue de la chaîne de B14 | 02/1951 | DOS2017FIG-01085 | 678x960 |
| 99856 | Chaîne de montage DS (nuit, 4 images) | 1955 | DOS2017FIG-05575 | — |
| 96653 / 96655 | Usine de Slough / Usine d'Amsterdam | 1947 | DOS2017FIG-00585 / -00587 | — |

Fiches Javel années 1930 présentes en **métadonnée seule, non numérisées** :
« L'usine de Javel en 1934 » (id 96611), « Usine Citroën Quai de Javel, vue des
terrains avant construction » (id 142770), « banquet d'inauguration »
08/10/1933 (id 142763). Ces fiches ne fourniraient aucune image.

## Droits

Tout est sous **droits réservés** (droits d'auteur + marques Citroën / Peugeot /
DS). Reproduction interdite sans autorisation ; le site vend d'ailleurs des
reproductions (boutique/panier). **Aucune licence libre.** La lecture
automatique des pages publiques et toute reproduction exigent donc une
**autorisation écrite**.

## Conséquence (politique d'accès aux images)

- Ce n'est **pas** une source à accès programmatique : le seul canal technique
  est la lecture des pages HTML et l'affichage direct des JPEG.
- La **lecture automatique des pages publiques** n'est autorisée qu'après une
  **autorisation reçue par e-mail** ; la référence (« e-mail de <expéditeur> du
  <date> ») serait alors tracée dans le descripteur sous
  `extra.scraping_consent`.
- **Aucune autorisation n'est reçue à ce jour** : pas de connecteur, pas de
  lecture automatique, aucun contournement d'anti-bot (règle dure).
- Une fois autorisé : **affichage direct** des images depuis l'institution,
  **jamais** de copie/réhébergement.

## Action en cours

E-mail envoyé le **2026-11-25 22:45** par l'agent navigateur à
`archives-avpcd@laventureassociation.com` (objet : « Mnemosyne — ajouter les
images d'archives du Centre d'Archives de Terre Blanche (L'Aventure Peugeot
Citroën DS)… »), posant l'unique question de l'**accès programmatique** (API,
IIIF, export) et, à défaut, de l'**autorisation de lire automatiquement les
pages publiques**, avec demande d'exemples d'usine Citroën. Aucun rebond et
**aucune réponse** au 2026-11-26. **Ne pas relancer.** Cet e-mail **n'est pas**
une autorisation : à ce jour aucun `extra.scraping_consent` n'est tracé.

## Alternative publique

La Contemporaine / L'Argonnaute (université Paris Nanterre) détient une série
« Paris. Usine Citroën. Quai de Javel » avec ouvriers, mais elle est **aussi**
bloquée (OAI-PMH trop pauvre, anti-bot sur le front HTML, CGU exigeant un accord
écrit). Elle est suivie séparément dans `docs/SOURCE-LA-CONTEMPORAINE.md` et ne
relève pas de cette mission.

## Décision et prochaines étapes

**Ne pas committer de descripteur ni de connecteur « live »** tant qu'aucune
autorisation écrite n'est reçue (règle « Accès aux images — pas de scraping »).

1. Réponse de l'institution (via l'agent navigateur, `mailwatch`).
2. **Si accord** (accès officiel, ou autorisation de lire les pages publiques
   avec référence expéditeur + date) :
   - descripteur `config/sources/aventure_citroen.yaml` — accès officiel, ou
     `protocol: html` + `extra.scraping_consent` (« e-mail de <expéditeur> du
     <date> ») ;
   - connecteur `src/mnemosyne/sources/aventure_citroen.py` : `/recherche`
     (filtre société Citroën, documents iconographiques) puis `/archive/{id}` ;
     n'exposer une image (`/upload/documents/…`, en **affichage direct**) que
     pour les fiches réellement numérisées ; normaliser vers `Asset` à la
     frontière du connecteur ;
   - test mocké dans `tests/` ;
   - enregistrement dans `src/mnemosyne/sources/__init__.py` ;
   - mise à jour de `docs/SOURCES.md`.
3. **Si refus** : abandon documenté.

Slug réservé : **`aventure_citroen`** (aucun descripteur existant au
2026-11-26 — vérifié dans `config/sources/`).
