**English below** — [jump to the English version ↓](#english)

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

---

## English

> **The broadest possible access to the world's historical archive images.**
>
> A free and open source project, under active development, built by one person —
> without copying, hosting or reselling the institutions' images.

I am building Mnemosyne, a free and open source documentary research project. My
goal is simple: make historical photographs **easier to find**, wherever they are
kept.

### The problem

The photographs that tell history are scattered across thousands of museums,
libraries, archives and learned societies. Each has its own catalogue, formats
and access rules. To find a precise image you must know the institution, its
portal, sometimes write an email and wait for an answer.

General search engines cannot query these catalogues. Existing aggregators often
stop at the institutions that already have a modern API. The others — the
majority — remain invisible.

### My ambition

Make the photographic collections scattered around the world queryable from a
single entry point, **including those never designed to be queried
automatically**.

**My project aims to be exhaustive about sources.** Not only the large
institutions with an API, but also small organisations, old catalogues and sites
without programmatic access. That is where the work is hard, and where it
matters.

**The number of sources is going to explode.** The project is under active
development: figures, sources and the API still move. What you read here is a
dated snapshot, not a frozen promise.

This is not another search engine: it is an **access infrastructure**. It does
not copy images. It brings the record, the metadata, the known rights and the
link to the institution that holds the original.

### What Mnemosyne does

- **Discovers** institutions and their catalogues.
- **Connects** very different systems: APIs, IIIF, OAI-PMH, proprietary
  catalogues, older websites.
- **Queries live**: a search queries the sources at request time. There is no
  local copy of the collections.
- **Normalises** results: title, creator, date, place, licence, provenance, link
  to the record.
- **Maintains** connections: failure detection, repair, updates.
- **Points back** to the institution: credit, link to the original catalogue.

### What this changes for an institution

- Your collections become **easier to discover**, without changing your systems.
- Every result **credits your institution** and links to your catalogue.
- **No installation**, no development on your side.
- You can **ask for a record to be removed** at any time.
- You can **ask for a human exchange**, with no technical knowledge required.

### What I do not do

- I do not download the images.
- I do not host them.
- I do not redistribute them.
- I do not resell them.
- I grant no rights over the images.
- I do not replace your catalogue.

**Mnemosyne gives access to the sources, not to the rights they contain.** An
image found through Mnemosyne is not free for all that: consultation,
reproduction and reuse conditions depend on the institution, the author, the
rights holders and applicable law. Mnemosyne displays the available rights
information and points to the source; the final user remains responsible for the
necessary steps.

### How it works, without jargon

1. You search for "oil wells in Alsace around 1920".
2. Mnemosyne queries the connected catalogues live.
3. It gathers comparable records and shows, for each: title, date, institution,
   known rights and the link.
4. You click: you land on the institution's site, which gives you access to the
   image and its conditions.

### Let's talk

Did you receive a message from me? Are you wondering what I do with your
collections?

- Read [the page for institutions](docs/POUR-LES-INSTITUTIONS.md) (in French).
- Write to me: **archivist.mnemosyne@gmail.com**
- **For a phone call or a video call, contact me by email.** We will arrange the
  appointment by email; no technical knowledge is needed.
- Want your institution removed? Say so: it is immediate.

I prefer to remain anonymous. The project itself is public: source code,
documentation and history are open.

### For developers

#### API

The API is a real-time federation: it queries the providers at request time,
then normalises and deduplicates the results.

```bash
mnemosyne serve                 # local API (127.0.0.1:8080)
GET /search?q=puits+de+Lacq&limit=20
GET /sources                    # connected institutions
GET /sources/status             # per-source state, latency, errors
```

Each result carries its provenance (`source_id`, `page_url`, `image_url`,
`thumbnail_url`, licence, rights) and a stable identifier. Images are never
downloaded: only their URLs are returned.

#### Displaying images in a frontend

Yes: a frontend can display the image **from the URL returned by the API**
(`image_url` or `thumbnail_url`) without downloading or storing it — the
visitor's browser fetches it from the institution.

Conditions:

- display the **credit** and a **link to the institution's record**;
- never re-host the image, never cache it on your server, never proxy it;
- prefer `thumbnail_url` for grids;
- provide a **fallback** when the institution blocks hotlinking (403/Referer) or
  the URL expires: show a "view on the institution's site" link;
- the institution's conditions always prevail; if it asks for removal, remove.

Display is not reuse: the image stays with the institution, and its conditions
apply.

#### CLI

```bash
mnemosyne search "puits de Lacq 1950"   # live multi-source search
mnemosyne status                        # sources + governor
mnemosyne run                           # heartbeat (permanent engine)
mnemosyne agency "..."                  # bi-agent (coder + browser)
mnemosyne resolve enqueue <segment_id>  # sentence → image resolver
```

#### Architecture

```
heartbeat      durable scheduler (SQLite jobs), crash recovery
catalog        source registry + state machine
connectors     protocol adapters (IIIF, SRU, REST, SPARQL…)
sources        one connector per institution (config/sources/*.yaml)
api            FastAPI federated search service
agents         bi-agent (coder + browser) and adversarial resolver
observatory    local read-only UI (sessions, jobs, events)
```

Two permanent loops run in parallel: the **bi-agent** maintains the catalogue and
the connectors; the **resolver** tests the sentence → image relation
(candidates, human validation, coverage gaps).

#### Project status

- **66 declared sources, 53 active** (November 2026) — and the number of sources
  is going to explode.
- Sources range from national libraries and museums to regional archives and
  aggregators (Europe, the Americas, Asia, Oceania).
- A few sources are temporarily blocked from my infrastructure
  (Cloudflare / Akamai: Gallica, NGA, Library of Congress). They stay documented
  and will be re-enabled when access returns.
- Details in [`docs/SOURCES.md`](docs/SOURCES.md).

#### Contributing

The code is MIT-licensed. Contributions are welcome, especially connectors to
under-covered institutions and metadata fixes. Open an issue or a pull request:
<https://github.com/Antonio-Faure/mnemosyne>.

### Licence

MIT.
