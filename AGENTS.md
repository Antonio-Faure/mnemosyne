# AGENTS.md — mnemosyne

Autonomous heartbeat agent that aggregates historical image archive providers into one unified API.

# Priorities

- Clarity · Precision · Low verbosity
- **Token/cost sobriety**: prompt caching, bounded tool outputs, no wasted calls
- **Security & legality**: secrets in the vault, robots/ToS, transparent outreach
- **Atomic writes**: `<path>.tmp` → `os.replace`, always

# Overview

Runtime is a **deterministic heartbeat** (durable jobs) driving **two Stirrup agents** (coder + browser). Details in `docs/`.

- `main.py` — CLI entry (`python main.py`, or the `mnemosyne` script)
- `src/mnemosyne/heartbeat/` — durable scheduler, job store (SQLite WAL), job handlers
- `src/mnemosyne/reputation/` — adaptive governor (pacing, blocks, warmup caps)
- `src/mnemosyne/catalog/` — provider registry + lifecycle state machine
- `src/mnemosyne/connectors/` — connector contract (`base.py`)
- `src/mnemosyne/sources/` — one connector per provider (`iiif.py` = generic IIIF)
- `src/mnemosyne/agents/` — bi-agent: `mailbox.py`, `supervisor.py`, `browser_agent.py`, `warmup*.py`
- `src/mnemosyne/dev/` — coder agent: `agent.py`, `tools.py`, `guard.py`, `git_ops.py`, `worktree.py`
- `src/mnemosyne/discovery/` — find new providers (Wikidata IIIF hosts)
- `src/mnemosyne/normalize/` — canonical `Asset`, dedup
- `src/mnemosyne/api/` — FastAPI aggregation service
- `src/mnemosyne/vault/` — encrypted credentials · `src/mnemosyne/notify/` — Telegram
- `src/mnemosyne/browser/` — CDP client, history reader · `src/mnemosyne/journal.py` — daily + per-service journals
- `src/mnemosyne/identity.py` — transparency (identity + repo URL) · `src/mnemosyne/memory/` — bounded memory
- `harness/` — helpers (agent-written, versioned) + vendored interaction skills
- `config/config.yaml`, `config/sources/*.yaml` — settings + provider descriptors

# Runtime agents vs AGENTS.md

`AGENTS.md` is for a **coding agent working on this repo** — NOT the runtime prompt of our agents. Each runtime agent has its own editable instructions file, loaded at run time:

- **coder** → `agents/coder.md` (product code, tests, git/PR)
- **browser** → `agents/browser.md` (browser-harness, helpers, video, accounts/keys)

The validated two-agent design is in **`docs/VISION-BIAGENT.md`** — read it before any agent work.

# Commands

```bash
make up | down | logs          # single container: app + real Chrome (Xvfb/VNC/CDP)
make cdp | vnc | record | egress
mnemosyne run | serve | status | doctor | journal
mnemosyne agency "<task>" [--to coder|browser] | messages      # bi-agent
mnemosyne discover | connect-next | warmup
mnemosyne llm test | telegram test | sources | search "<q>" | harvest
make install-timer             # daily connect-next (systemd user timer)
```

Dev: `pip install -e '.[dev]'` then `ruff check .` and `pytest`.

# Security

- **Never commit secrets.** Keys/logins/sessions live in the vault (`vault/`, git-ignored) or `.env` (git-ignored). `.env.example` only names variables. Never put a secret in an agent message — send a `vault:<key>` reference. Source keys are stored as `<key_env>.lower()` and exported to env at `Engine` start (`docs/CREDENTIALS.md`).
- Chrome runs as **uid 1000 with its sandbox enabled**; never `--no-sandbox`. Exposed ports are **loopback only**; the agent's traffic must not transit Tailscale (`make egress`).
- **Governor mandatory** for any rate-limited/sensitive action (HTTP, account creation, outbound email). On 403/429/captcha the whole system slows down.
- **Transparent outreach**: every email/contact form states who the agent is and links the repo — build it with `identity.disclosure()`, never by hand. Human-in-the-loop for anything irreversible. The operator channel is currently **disabled** (no `operator` recipient, no agent questions): on a blocker, stop cleanly with a factual `task_done`; the operator reads the journal. Telegram remains an outbound alert only.
- **Provenance on every asset** (source, page URL, license/rights, date).
- **Bounded context**: agent turns are bounded Stirrup sessions (`agents.max_turns`), tool outputs are truncated, and turns go through the durable mailbox instead of replaying history. Stirrup requires an output ceiling — keep `agents.max_tokens` high (32k). Record `usage`.

# Contributing

- A new provider = `config/sources/<id>.yaml` + a `Connector` in `src/mnemosyne/sources/` + registration in `sources/__init__.py` + a mocked test (never hit the network in tests). Normalize into `Asset` at the connector boundary.
- **Self-extension** runs through `dev/guard.py`: writes only under `config/sources/`, `src/mnemosyne/sources/`, `tests/`, `docs/`; never `.env`, `vault/`, `data/`, `agents/`, `heartbeat/`, `reputation/`, `dev/`, `AGENTS.md`, `pyproject.toml`; no `--force`/`reset`/`clean`; lint + tests must pass; PR reviewed by a human.
- Prefer the smallest diff that fixes the problem; keep token use low (`Grep`/`Glob`, sliced reads, `tail`/`grep ERROR` on logs).
- Architecture decisions are recorded in `docs/`.
