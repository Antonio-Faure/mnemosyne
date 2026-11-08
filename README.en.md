# mnemosyne

> **The broadest possible access to the world's historical archive images.**
>
> A free and open source project, under active development, built by one person —
> without copying, hosting or reselling the institutions' images.

I am building Mnemosyne, a free and open source documentary research project. My
goal is simple: make historical photographs **easier to find**, wherever they are
kept.

## The problem

The photographs that tell history are scattered across thousands of museums,
libraries, archives and learned societies. Each has its own catalogue, formats
and access rules. To find a precise image you must know the institution, its
portal, sometimes write an email and wait for an answer.

General search engines cannot query these catalogues. Existing aggregators often
stop at the institutions that already have a modern API. The others — the
majority — remain invisible.

## My ambition

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

## What Mnemosyne does

- **Discovers** institutions and their catalogues.
- **Connects** very different systems: APIs, IIIF, OAI-PMH, proprietary
  catalogues, older websites.
- **Queries live**: a search queries the sources at request time. There is no
  local copy of the collections.
- **Normalises** results: title, creator, date, place, licence, provenance, link
  to the record.
- **Maintains** connections: failure detection, repair, updates.
- **Points back** to the institution: credit, link to the original catalogue.

## What this changes for an institution

- Your collections become **easier to discover**, without changing your systems.
- Every result **credits your institution** and links to your catalogue.
- **No installation**, no development on your side.
- You can **ask for a record to be removed** at any time.
- You can **ask for a human exchange**, with no technical knowledge required.

## What I do not do

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

## How it works, without jargon

1. You search for "oil wells in Alsace around 1920".
2. Mnemosyne queries the connected catalogues live.
3. It gathers comparable records and shows, for each: title, date, institution,
   known rights and the link.
4. You click: you land on the institution's site, which gives you access to the
   image and its conditions.

## Let's talk

Did you receive a message from me? Are you wondering what I do with your
collections?

- Read [the page for institutions](docs/POUR-LES-INSTITUTIONS.md) (in French).
- Write to me: **archivist.mnemosyne@gmail.com**
- **For a phone call or a video call, contact me by email.** We will arrange the
  appointment by email; no technical knowledge is needed.
- Want your institution removed? Say so: it is immediate.

I prefer to remain anonymous. The project itself is public: source code,
documentation and history are open.

## For developers

### API

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

### Displaying images in a frontend

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

### CLI

```bash
mnemosyne search "puits de Lacq 1950"   # live multi-source search
mnemosyne status                        # sources + governor
mnemosyne run                           # heartbeat (permanent engine)
mnemosyne agency "..."                  # bi-agent (coder + browser)
mnemosyne resolve enqueue <segment_id>  # sentence → image resolver
```

### Architecture

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

### Project status

- **66 declared sources, 53 active** (November 2026) — and the number of sources
  is going to explode.
- Sources range from national libraries and museums to regional archives and
  aggregators (Europe, the Americas, Asia, Oceania).
- A few sources are temporarily blocked from my infrastructure
  (Cloudflare / Akamai: Gallica, NGA, Library of Congress). They stay documented
  and will be re-enabled when access returns.
- Details in [`docs/SOURCES.md`](docs/SOURCES.md).

### Contributing

The code is MIT-licensed. Contributions are welcome, especially connectors to
under-covered institutions and metadata fixes. Open an issue or a pull request:
<https://github.com/Antonio-Faure/mnemosyne>.

## Licence

MIT.
