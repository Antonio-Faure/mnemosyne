# AGENTS.md — mnemosyne

Autonomous heartbeat agent that aggregates historical image archive providers into
one unified API.

## Golden rules

1. **Never commit secrets.** API keys, logins, cookies and sessions live in the
   encrypted vault (`vault/`, git-ignored) or in `.env` (git-ignored). Never hardcode
   one. `.env.example` is the only file allowed to mention variable *names*.
2. **Atomic writes.** Every file write (JSON, DB export, image, credential) goes
   through `<path>.tmp` → `os.replace(tmp, path)`. A killed process must never
   corrupt a final artifact. Orphan `.tmp` files are cleaned on startup.
3. **The heartbeat is the product.** Anything the agent must do "forever" is a
   durable job in the job store, never a bare `while True` in a one-off script.
   State must survive a crash and resume.
4. **Respect the governor.** All rate-limited / sensitive actions (HTTP calls to a
   provider, account creation, outbound email) go through `reputation.governor`.
   Never bypass it; on 403/429/captcha the whole system slows down.
5. **Lawful & transparent.** Respect robots.txt and provider ToS. Throttle per
   domain. The agent acts in its own name and **every email / contact form states
   who it is and links this repository** (build the text with
   `identity.disclosure()`, never hand-roll it). Human-in-the-loop is mandatory for
   anything irreversible or legally binding.
6. **Every asset carries provenance.** No image enters the store without its source,
   canonical page URL, license/rights and retrieval timestamp.
7. **Bounded memory.** Long-running conversations must go through
   `memory.Memory`: recent messages verbatim + a rolling summary, older turns
   compacted (summarized then pruned). Never resend an unbounded history to the
   LLM. Do not set an output `max_tokens` by default (reasoning models return empty
   `content` when the budget is exhausted); record `usage` to track cost.
8. **Always able to ask the operator on Telegram.** Whenever the agent is stuck,
   uncertain, blocked (captcha, phone verification, refusal, ambiguous access
   request, risky/irreversible action) it **must be able to ask the operator a
   question on Telegram** and may wait for the answer. Use `Notifier.ask()` (or
   the `request_human` tool) — never guess or force through a blocker. The
   operator's Telegram replies are polled by the heartbeat, written to
   `control/inbox.md` and the journal, and then read like any operator message.
   Telegram must therefore stay configured and enabled.

## Connector contract

Each provider is a `Connector` subclass in `src/mnemosyne/sources/`, registered and
described by a YAML descriptor in `config/sources/`. A connector implements:

```python
async def search(self, query: str, limit: int = 20, **filters) -> list[Asset]
async def fetch(self, asset: Asset) -> bytes            # optional (lazy)
def provenance(self, asset: Asset) -> dict
```

Descriptor fields: `id`, `name`, `institution`, `country`, `protocol`, `base_url`,
`auth` (`none` | `api_key` | `account` | `oauth`), `key_env`, `license`, `rate_limit`,
`priority`, `tags`, `enabled`.

Never leak a provider's raw shape into `Asset`: normalize at the connector boundary.

## Adding a provider

1. Add `config/sources/<id>.yaml`.
2. Implement / reuse a connector in `src/mnemosyne/sources/`.
3. Register it in `src/mnemosyne/sources/__init__.py`.
4. Add a test in `tests/` (mock HTTP; never hit the network in tests).

## Operator channels

- **Journal**: `journal/YYYY-MM-DD.md`, one file per day, append-only. Written by
  the heartbeat (`mnemosyne journal` to read). Git-ignored.
- **Service journals**: `journal/services/<id>.md`, one markdown per provider the
  agent wants to access. Every entry is a dated action (`YYYY-MM-DD HH:MM:SS`):
  access attempt, API key obtained, email sent, block, escalation. Read with
  `mnemosyne journal --service <id>`.
- **Steering**: `control/directives.md` (standing instructions, re-read on start)
  and `control/inbox.md` (one-off messages via `mnemosyne say`). Git-ignored.
- **Alerts**: Telegram (`notify/`) for hard blockers.
- **Health**: `mnemosyne doctor`.

## LLM auth

`llm/client.py` resolves the OpenCode Go key from `OPENCODE_API_KEY` → vault
(`opencode_api_key`) → the opencode auth cache (`~/.local/share/opencode/auth.json`,
entry `opencode-go`). It always sends a clean `User-Agent` and a stable
`x-opencode-session` header (required by Zen).

## Agentic layer (Stirrup)

The heartbeat is the deterministic control plane; the per-task LLM loop uses
**Stirrup** with **browser-use** over CDP (`docs/P2-AGENTS.md`). Give agents
deterministic business tools (`agents/tools.py`), never the raw DOM. Stirrup and
browser-use imports must stay inside `agents/*` / `browser/*` so the core runs
without the `browser` extra. Browser work needs the extra:

```bash
pip install -e '.[browser]'
```

## Dev

```bash
pip install -e '.[dev]'
ruff check .
pytest
```

## Token / cost sobriety (when an AI works on this repo)

- Prefer `Glob`/`Grep` over full reads; read by slices.
- Keep LLM calls batched; do not re-run harvest/analysis when valid artifacts exist.
- Summarize logs with `tail`/`grep ERROR`, never dump full output.

## Decision log

Architecture-critical decisions and their rationale are recorded in `docs/`.
