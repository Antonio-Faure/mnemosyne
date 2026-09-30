# mnemosyne

> Autonomous, resilient agent that discovers, connects and aggregates hundreds of
> historical image archive providers into a single unified API.

Named after Mnemosyne, the Greek goddess of memory and the mother of the Muses —
the archives.

## Why

Finding *the best* historical images for a topic is not a search problem, it is an
**access** problem. The sources that matter (national libraries, Europeana, company
archives, regional and departmental collections, local historical associations) are
extremely heterogeneous: some expose IIIF or OAI-PMH, some only a web portal, some
only a contact address. Onboarding them (accounts, API keys, access requests by
email) is a long human task.

`mnemosyne` delegates that work to a perpetual agent with a **heartbeat**:

```
discover → warmup → onboard → verify → harvest → repair → retry
```

It is never "finished": it keeps extending the catalog and repairing connectors on
its own. The end product is a **unified search API** over the aggregated corpus,
with provenance and license attached to every asset.

## Architecture

```
src/mnemosyne/
├── heartbeat/    durable scheduler + job store (SQLite) + workers
├── reputation/   adaptive governor + account warmup phases
├── catalog/      source registry, state machine, provenance
├── connectors/   protocol adapters: IIIF / SRU / OAI-PMH / SPARQL / REST / HTML
├── sources/      one connector per provider
├── agents/       discovery · onboarding · outreach (browser-use)
├── browser/      dedicated real Chrome over CDP (Xvfb + VNC), anti-detect profile
├── email/        Gmail via the dedicated browser (account verification) + fallback forms
├── vault/        encrypted credentials (API keys, logins, sessions) — never in git
├── normalize/    canonical Asset, dedup, license & provenance
├── api/          FastAPI aggregation service
└── notify/       Telegram alerts (human-in-the-loop)
```

### The heartbeat

Every provider is a durable job in a persisted state machine:

```
DISCOVERED → RESEARCHED → ONBOARDING → PENDING → CREDENTIALED → CONNECTED → DEGRADED → BROKEN
```

The scheduler survives crashes and restarts (SQLite WAL). On any 403/429/captcha
the **governor** slows the whole system down automatically, and hard blockers are
escalated to a human over Telegram while the agent keeps working elsewhere.

## Quickstart

```bash
cp .env.example .env          # fill in keys
python -m venv .venv && . .venv/bin/activate
pip install -e .

# encrypted vault (stores API keys / sessions)
mnemosyne vault init

# list configured providers
mnemosyne sources

# one-shot live search across keyless providers
mnemosyne search "puits de Lacq 1950"

# run the aggregation API
mnemosyne serve

# run the perpetual heartbeat (harvest + verify)
mnemosyne run
```

## Docker

```bash
docker compose up -d          # mnemosyne + dedicated Chrome (Xvfb + VNC + CDP 9222)
```

- API: http://localhost:8080
- Chrome CDP: http://localhost:9222 (browser-use)
- noVNC (human intervention): http://localhost:6080

The Chrome profile (holding the agent's own Google account) persists in a volume.

## Milestone status

- **P0+P1 (this repo)**: heartbeat, catalog, governor, 5 keyless providers
  (Gallica, Wikidata, Wikimedia Commons, Internet Archive, Openverse),
  normalization/dedup/provenance, unified API.
- **P2**: browser-use onboarding agent + Gmail-via-browser + warmup → keyed providers.
- **P3**: autonomous discovery (GLAM SPARQL, directories).
- **P4**: connector self-repair, dashboard, scale to hundreds of sources.

See `docs/` and `AGENTS.md` for details.

## License

MIT.
