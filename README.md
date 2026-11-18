**English below** — [jump to the English version ↓](#english)

# mnemosyne

> **Le moteur de recherche des images d'archives.**

Un projet libre et open source, en développement actif, que je développe seul —
sans copier, héberger ni revendre les images des institutions.

Mnemosyne est un moteur de recherche. Pas un musée, pas un site qui stocke des
images, pas un vendeur de droits : un moteur de recherche. Les sources sont
ajoutées par **Archivist**, le système autonome du projet.

Comme un moteur de recherche ne possède pas les pages qu'il trouve, Mnemosyne ne
possède pas les images d'archives qu'il référence. Il montre qu'elles existent,
affiche les informations qu'il a récupérées, et renvoie vers le site qui les
conserve.

## Le problème

Les photographies qui racontent l'histoire sont dispersées dans des milliers de
musées, bibliothèques, archives et sociétés savantes. Chacun a son catalogue, ses
formats, ses règles d'accès. Pour trouver une image précise, il faut connaître
l'institution, son site, parfois écrire un e-mail et attendre une réponse.

Les sites qui rassemblent déjà des collections se limitent souvent aux grandes
institutions qui ont un accès technique moderne. Les autres — les plus nombreuses
— restent invisibles.

## Mon ambition

Un seul champ de recherche pour interroger, à terme, les images d'archives de
milliers de sources différentes, y compris celles qui n'ont jamais été conçues
pour être interrogées par un programme.

**Mon projet a une ambition d'exhaustivité sur les sources.** Je ne veux pas
seulement les grandes institutions qui ont déjà un accès technique : je veux
aussi les petites structures, les catalogues qui n'ont jamais été pensés pour
être interrogés à distance, les sites sans accès automatique. C'est le travail le
plus difficile, et le plus utile.

**L'ambition est mondiale : de l'ordre de 3 000 sources en France, 20 000 en
Europe et 100 000 dans le monde.** Le projet est en développement actif : les
chiffres, les sources et l'accès bougent encore. Ce que vous lisez ici est un
état daté, pas une promesse figée.

## Ce que fait Mnemosyne

- **Cherche** dans les sites des institutions, au moment de la demande.
- **Rassemble** les résultats et affiche les informations récupérées : titre,
  auteur, date, lieu, droits.
- **Montre** l'image et renvoie vers la page de l'institution.

## Ce que Mnemosyne ne fait pas

- Il ne garantit pas que les images sont libres de droits.
- Il ne donne aucun droit sur les images.
- Il ne télécharge pas, n'héberge pas, ne redistribue pas, ne revend pas.
- Il ne remplace pas le catalogue de l'institution.
- Il ne fait pas de conseil juridique.

**Un moteur de recherche n'est pas un distributeur de droits.** Une image
trouvée via Mnemosyne n'est pas libre pour autant. Les conditions de
consultation, de reproduction et de réutilisation dépendent de l'institution, de
l'auteur, des ayants droit et de la loi. Mnemosyne affiche les informations de
droits qu'il a récupérées et renvoie vers la source ; les démarches restent à la
charge de l'utilisateur.

## Comment ça marche

1. Vous cherchez « puits de pétrole en Alsace vers 1920 ».
2. Mnemosyne interroge les sites des institutions connectées.
3. Il rassemble les résultats et affiche, pour chacun : le titre, la date,
   l'institution, les droits connus et le lien.
4. Vous cliquez : vous arrivez sur le site de l'institution, qui vous donne accès
   à l'image et à ses conditions.

## Ce que ça change pour une institution

- Vos collections sont **plus faciles à découvrir**, sans changer votre système
  informatique.
- Chaque résultat **nomme votre institution** et renvoie vers votre site.
- **Aucune installation**, aucun développement de votre côté.
- Vous pouvez **demander le retrait** de votre institution à tout moment.
- Vous pouvez **demander un échange humain**, sans connaissance technique.

## Parlons-en

Vous avez reçu un mail de ma part ? Vous vous demandez ce que je fais de vos
collections ?

- Lisez [la page pour les institutions](docs/POUR-LES-INSTITUTIONS.md).
- Répondez au mail que vous avez reçu : je vous réponds personnellement.
- **Pour un échange téléphonique ou une visioconférence, demandez-le dans votre
  réponse.** Aucune connaissance technique n'est nécessaire.
- Vous voulez que votre institution soit retirée ? Dites-le : c'est immédiat.

Le projet est porté par **Antonio Faure**, son gestionnaire. Le code source, la
documentation et l'historique sont publics.

## Pour les développeurs

Le code est sous licence MIT. Les contributions sont bienvenues, en particulier
les connexions vers des institutions peu couvertes et les corrections
d'informations. Ouvrez une issue ou une pull request :
<https://github.com/Antonio-Faure/mnemosyne>.

### API

```bash
mnemosyne serve                 # API locale (127.0.0.1:8080)
GET /search?q=puits+de+Lacq&limit=20
GET /sources
GET /sources/status
```

Page de recherche locale : <http://127.0.0.1:8080/explorer>.

Chaque résultat indique sa provenance (`source_id`, `page_url`, `image_url`,
`thumbnail_url`, droits) et un identifiant stable. Les images ne sont jamais
téléchargées : seules leurs adresses sont transmises.

### Afficher les images dans un site

Un site peut afficher l'image **depuis l'adresse fournie par l'API**, sans la
télécharger ni la stocker : c'est le navigateur du visiteur qui va la chercher
chez l'institution. Il faut :

- afficher le nom de l'institution et un lien vers sa page ;
- ne pas ré-héberger l'image, ne pas la mettre en cache, ne pas la proxyfier ;
- préférer `thumbnail_url` pour les vignettes ;
- prévoir un lien « voir sur le site de l'institution » si l'image ne s'affiche
  pas ;
- respecter les conditions de l'institution ; si elle demande le retrait, on
  retire.

Afficher n'est pas réutiliser : l'image reste chez l'institution, et ses
conditions s'appliquent.

### CLI

```bash
mnemosyne search "puits de Lacq 1950"
mnemosyne status
mnemosyne run
```

L'architecture, les connecteurs et l'état des sources sont documentés dans
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) et
[`docs/SOURCES.md`](docs/SOURCES.md).

## Licence

MIT.

---

## English

> **The search engine for archive images.**

A free and open source project, under active development, built by one person —
without copying, hosting or reselling the institutions' images.

Mnemosyne is a search engine. Not a museum, not a site that stores images, not a
seller of rights: a search engine. Sources are added by **Archivist**, the
project's autonomous system.

Just as a search engine does not own the pages it finds, Mnemosyne does not own
the archive images it references. It shows that they exist, displays the
information it has retrieved, and points to the site that keeps them.

### The problem

The photographs that tell history are scattered across thousands of museums,
libraries, archives and learned societies. Each has its own catalogue, formats
and access rules. To find a precise image you must know the institution, its
website, sometimes write an email and wait for an answer.

Sites that already gather collections often stop at the large institutions with
modern technical access. The others — the majority — remain invisible.

### My ambition

One search field to query, eventually, the archive images of thousands of
different sources, including those never designed to be queried by a program.

**My project wants to cover as many sources as possible.** Not only the large
institutions with technical access, but also small organisations, catalogues
never designed to be queried remotely, and sites without automatic access. That
is the hardest work, and the most useful.

**The ambition is global: on the order of 3,000 sources in France, 20,000 in
Europe and 100,000 worldwide.** The project is under active development: figures,
sources and access still move. What you read here is a dated snapshot, not a
frozen promise.

### What Mnemosyne does

- **Searches** the institutions' sites, at request time.
- **Gathers** the results and displays the information retrieved: title, author,
  date, place, rights.
- **Shows** the image and points to the institution's page.

### What Mnemosyne does not do

- It does not guarantee that the images are free of rights.
- It grants no rights over the images.
- It does not download, host, redistribute or resell them.
- It does not replace the institution's catalogue.
- It does not provide legal advice.

**A search engine is not a rights clearing house.** An image found through
Mnemosyne is not necessarily free to use. Consultation, reproduction and reuse
conditions depend on the institution, the author, the rights holders and the law.
Mnemosyne displays the rights information it has retrieved and points to the
source; the user remains responsible for the necessary steps.

### How it works

1. You search for "oil wells in Alsace around 1920".
2. Mnemosyne queries the connected institutions' sites.
3. It gathers the results and shows, for each: title, date, institution, known
   rights and the link.
4. You click: you land on the institution's site, which gives you access to the
   image and its conditions.

### What this changes for an institution

- Your collections become **easier to discover**, without changing your systems.
- Every result **names your institution** and points to your website.
- **No installation**, no development on your side.
- You can **ask for your institution to be removed** at any time.
- You can **ask for a human exchange**, with no technical knowledge required.

### Let's talk

Did you receive an email from me? Are you wondering what I do with your
collections?

- Read [the page for institutions](docs/POUR-LES-INSTITUTIONS.md) (in French).
- Reply to the email you received: I answer personally.
- **For a phone call or a video call, ask in your reply.** No technical
  knowledge is needed.
- Want your institution removed? Say so: it is immediate.

The project is led by **Antonio Faure**, its project manager. The source code,
documentation and history are public.

### For developers

The code is MIT-licensed. Contributions are welcome, especially connections to
under-covered institutions and information fixes. Open an issue or a pull
request: <https://github.com/Antonio-Faure/mnemosyne>.

#### API

```bash
mnemosyne serve                 # local API (127.0.0.1:8080)
GET /search?q=puits+de+Lacq&limit=20
GET /sources
GET /sources/status
```

Local search page: <http://127.0.0.1:8080/explorer>.

Each result carries its provenance (`source_id`, `page_url`, `image_url`,
`thumbnail_url`, rights) and a stable identifier. Images are never downloaded:
only their addresses are returned.

#### Displaying images on a website

A website can display the image **from the address returned by the API**,
without downloading or storing it: the visitor's browser fetches it from the
institution. It must:

- display the institution's name and a link to its page;
- never re-host the image, never cache it, never proxy it;
- prefer `thumbnail_url` for thumbnails;
- provide a "view on the institution's site" link if the image does not load;
- respect the institution's conditions; if it asks for removal, remove it.

Display is not reuse: the image stays with the institution, and its conditions
apply.

#### CLI

```bash
mnemosyne search "puits de Lacq 1950"
mnemosyne status
mnemosyne run
```

Architecture, connectors and source status are documented in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and
[`docs/SOURCES.md`](docs/SOURCES.md).

### Licence

MIT.
