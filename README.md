# mnemosyne

> **Le meilleur accès possible aux images d'archives historiques du monde.**
>
> Un projet libre et open source, en développement actif, que je développe seul —
> sans copier, héberger ni revendre les images des institutions.

Je développe Mnemosyne, un projet de recherche documentaire libre et open source.
Mon objectif est simple à dire : rendre les photographies historiques **plus
faciles à trouver**, où qu'elles soient conservées.

## Le problème

Les photographies qui racontent l'histoire sont dispersées dans des milliers de
musées, bibliothèques, archives et sociétés savantes. Chacun a son catalogue, ses
formats, ses règles d'accès. Pour trouver une image précise, il faut connaître
l'institution, son portail, parfois écrire un e-mail et attendre une réponse.

Les moteurs de recherche classiques ne savent pas interroger ces catalogues. Les
agrégateurs existants se limitent souvent aux institutions qui disposent déjà
d'une API moderne. Les autres — les plus nombreuses — restent invisibles.

## Mon ambition

Rendre interrogeables, depuis un seul point d'entrée, les collections
photographiques dispersées dans le monde entier, **y compris celles qui n'ont
jamais été conçues pour être interrogées automatiquement**.

**Mon projet se veut exhaustif sur les sources.** Je ne veux pas seulement les
grandes institutions qui ont déjà une API : je veux aussi les petites structures,
les catalogues anciens, les sites sans accès programmatique. C'est là que le
travail est difficile, et c'est là qu'il a de la valeur.

**Le nombre de sources est amené à exploser.** Le projet est en développement
actif : les chiffres, les sources et l'API bougent encore. Ce que vous lisez ici
est un état daté, pas une promesse figée.

Ce n'est pas un moteur de recherche de plus : c'est une **infrastructure
d'accès**. Elle ne copie pas les images. Elle apporte la notice, les métadonnées,
les droits connus et le lien vers l'institution qui conserve l'original.

## Ce que fait Mnemosyne

- **Découvre** les institutions et leurs catalogues.
- **Connecte** des systèmes très différents : API, IIIF, OAI-PMH, catalogues
  propriétaires, sites anciens.
- **Interroge en direct** : une recherche interroge les sources au moment de la
  demande. Il n'y a pas de copie locale des collections.
- **Normalise** les résultats : titre, auteur, date, lieu, licence, provenance,
  lien vers la notice.
- **Maintient** les connexions : détection des pannes, réparation, mise à jour.
- **Renvoie** vers l'institution : crédit, lien vers le catalogue d'origine.

## Ce que ça change pour une institution

- Vos collections sont **plus faciles à découvrir**, sans changer votre système
  informatique.
- Chaque résultat **cite votre institution** et renvoie vers votre catalogue.
- **Aucune installation**, aucun développement de votre côté.
- Vous pouvez **demander le retrait** d'une notice à tout moment.
- Vous pouvez **demander un échange humain**, sans connaissance technique.

## Ce que je ne fais pas

- Je ne télécharge pas les images.
- Je ne les héberge pas.
- Je ne les redistribue pas.
- Je ne les revends pas.
- Je ne donne aucun droit sur les images.
- Je ne remplace pas votre catalogue.

**Mnemosyne donne accès aux sources, pas aux droits qu'elles contiennent.** Une
image trouvée via Mnemosyne n'est pas libre pour autant : les conditions de
consultation, de reproduction et de réutilisation dépendent de l'institution, de
l'auteur, des ayants droit et de la législation applicable. Mnemosyne affiche les
informations de droits disponibles et renvoie vers la source ; les démarches
restent à la charge de l'utilisateur final.

## Comment ça marche, sans jargon

1. Vous cherchez « puits de pétrole en Alsace vers 1920 ».
2. Mnemosyne interroge en direct les catalogues connectés.
3. Il rassemble les notices comparables et affiche, pour chacune : le titre, la
   date, l'institution, les droits connus et le lien.
4. Vous cliquez : vous arrivez sur le site de l'institution, qui vous donne accès
   à l'image et à ses conditions.

## Parlons-en

Vous avez reçu un message de ma part ? Vous vous demandez ce que je fais de vos
collections ?

- Lisez [la page pour les institutions](docs/POUR-LES-INSTITUTIONS.md).
- Écrivez-moi : **archivist.mnemosyne@gmail.com**
- **Pour un échange téléphonique ou une visioconférence, contactez-moi par
  e-mail.** C'est par e-mail que je fixerai le rendez-vous ; aucune
  connaissance technique n'est nécessaire.
- Vous voulez que votre institution soit retirée ? Dites-le : c'est immédiat.

Je préfère rester anonyme. Le projet, lui, est public :
code source, documentation et historique sont ouverts.

## Pour les développeurs

### API

L'API est une fédération en temps réel : elle interroge les fournisseurs au
moment de la requête, puis normalise et déduplique les résultats.

```bash
mnemosyne serve                 # API locale (127.0.0.1:8080)
GET /search?q=puits+de+Lacq&limit=20
GET /sources                    # catalogue des institutions connectées
GET /sources/status             # état, latence, erreurs par source
```

Chaque résultat porte sa provenance (`source_id`, `page_url`, `image_url`,
`thumbnail_url`, licence, droits) et un identifiant stable. Les images ne sont
jamais téléchargées : seules leurs URL sont transmises.

### Afficher les images dans un frontend

Oui, un frontend peut afficher l'image **depuis l'URL fournie par l'API**
(`image_url` ou `thumbnail_url`), sans la télécharger ni la stocker : c'est le
navigateur du visiteur qui va la chercher chez l'institution.

Conditions à respecter :

- afficher le **crédit** et un **lien vers la notice** de l'institution ;
- ne pas ré-héberger l'image, ne pas la mettre en cache sur ton serveur, ne pas
  la proxyfier ;
- préférer `thumbnail_url` pour les vignettes ;
- prévoir un **fallback** si l'institution bloque le hotlinking (403/Referer) ou
  si l'URL expire : afficher alors un lien « voir sur le site de l'institution » ;
- les conditions de l'institution priment toujours ; si elle demande le retrait,
  on retire.

Afficher n'est pas réutiliser : l'image reste chez l'institution, et ses
conditions s'appliquent.

### CLI

```bash
mnemosyne search "puits de Lacq 1950"   # recherche live multi-sources
mnemosyne status                        # sources + gouverneur
mnemosyne run                           # heartbeat (moteur permanent)
mnemosyne agency "..."                  # bi-agent (codeur + navigateur)
mnemosyne resolve enqueue <segment_id>  # résolveur phrase → image
```

### Architecture

```
heartbeat      ordonnanceur durable (jobs SQLite), reprise après crash
catalog        registre des sources + machine à états
connectors     adaptateurs de protocoles (IIIF, SRU, REST, SPARQL…)
sources        un connecteur par institution (config/sources/*.yaml)
api            service FastAPI de recherche fédérée
agents         bi-agent (codeur + navigateur) et résolveur adversarial
observatory    interface locale de lecture (sessions, jobs, événements)
```

Deux boucles permanentes travaillent en parallèle : le **bi-agent** maintient le
catalogue et les connecteurs ; le **résolveur** met à l'épreuve la relation
phrase → image (candidats, validation humaine, trous de couverture).

### État du projet

- **66 sources déclarées, 53 actives** (novembre 2026) — et le nombre de sources
  est amené à exploser.
- Sources réparties entre bibliothèques nationales, musées, archives régionales
  et agrégateurs (Europe, Amériques, Asie, Océanie).
- Quelques sources sont momentanément bloquées depuis mon infrastructure
  (Cloudflare / Akamai : Gallica, NGA, Library of Congress). Elles restent
  documentées et seront réactivées dès que l'accès sera rétabli.
- Le détail est dans [`docs/SOURCES.md`](docs/SOURCES.md).

### Contribuer

Le code est sous licence MIT. Les contributions sont bienvenues, en particulier
les connecteurs vers des institutions peu couvertes et les corrections de
métadonnées. Ouvrez une issue ou une pull request :
<https://github.com/Antonio-Faure/mnemosyne>.

## Licence

MIT.
