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
Sign the profile into **Chrome** once over VNC: Gmail then logs in automatically
and Chrome's **password manager** can create/store credentials. See `docs/RUNBOOK.md`.

## Monitoring & steering

The agent keeps a **daily markdown journal** (`journal/YYYY-MM-DD.md`) and can be
steered at any time:

```bash
mnemosyne journal                    # today's journal
mnemosyne say "priorise Lacq"        # one-off message → control/inbox.md
mnemosyne status                     # providers, assets, governor pressure
mnemosyne doctor                     # config, vault, LLM auth, Chrome health
```

Edit `control/directives.md` for standing instructions (re-read on start). Telegram
alerts fire on hard blockers (captcha, phone verify, refusal, permanent failures).
See `docs/RUNBOOK.md` for launching and connecting the agent's Gmail over VNC.

## LLM auth (OpenCode Go)

The agent uses your OpenCode Go subscription by reading the token **opencode
already caches** at `~/.local/share/opencode/auth.json` (entry `opencode-go`).
Resolution order: `OPENCODE_API_KEY` → mnemosyne vault (`opencode_api_key`) →
opencode auth store. No separate key needed if you are logged in.

```bash
mnemosyne doctor       # shows auth_source
mnemosyne llm test     # one round-trip
```

## Memory, cost & transparency

- **Bounded memory**: `src/mnemosyne/memory.py` keeps the last N messages verbatim
  plus a rolling summary; older turns are summarized by the LLM and pruned
  (compaction). The context never grows without bound, so long-running agents do
  not blow up the token bill. Tune in `config.memory`.
- **No output cap by default**: calls send no `max_tokens` (the provider decides),
  and the returned `usage` is recorded to follow the cost.
- **Transparency**: every outbound email / contact form carries a one-line identity
  disclosure and the repository URL, generated from `config.identity`
  (`src/mnemosyne/identity.py`).

## Milestone status

- **P0+P1 (this repo)**: heartbeat, catalog, governor, 5 keyless providers
  (Gallica, Wikidata, Wikimedia Commons, Internet Archive, Openverse),
  normalization/dedup/provenance, unified API.
- **P2 (in progress)**: Stirrup agent loop + browser-use over CDP, deterministic
  tools, onboarding & outreach agents, Gmail-via-browser, governed by warmup.
  Install with `pip install -e '.[browser]'`. See `docs/P2-AGENTS.md`.
- **P3**: autonomous discovery (GLAM SPARQL, directories).
- **P4**: connector self-repair, dashboard, scale to hundreds of sources.

See `docs/` and `AGENTS.md` for details.

## License

MIT.
