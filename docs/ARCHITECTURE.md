# Architecture & decision log

## Goal

Aggregate hundreds of heterogeneous historical image providers into one search
API. The bottleneck is not search but **access**: onboarding providers (accounts,
API keys, emails) is a long human task, so it is delegated to a perpetual agent
with a heartbeat.

## Layers

| Layer | Role |
|---|---|
| `heartbeat` | durable scheduler + job queue (SQLite WAL). Survives crashes. |
| `reputation` | adaptive governor + account warmup phases. |
| `catalog` | provider registry + state machine. |
| `connectors` | protocol adapters (IIIF / SRU / OAI-PMH / SPARQL / REST / HTML). |
| `sources` | one connector per provider, mapped from `config/sources/*.yaml`. |
| `normalize` | canonical `Asset`, dedup, provenance. |
| `api` | FastAPI unified search. |
| `vault` | encrypted credentials (Fernet). |
| `notify` | Telegram HITL alerts. |
| `browser`/`agents`/`email` | P2: real Chrome over CDP for onboarding/outreach. |

## Provider state machine

```
DISCOVERED → RESEARCHED → ONBOARDING → PENDING → CREDENTIALED → CONNECTED → DEGRADED → BROKEN
```

`sync()` upserts descriptors from YAML without resetting state, so editing a
descriptor never loses lifecycle progress.

## Decisions

1. **Heartbeat, not scripts.** Everything perpetual is a durable job. Recurring
   jobs carry `interval_s`; on success the scheduler re-enqueues them. Stale locks
   are recovered on each tick.
2. **Governor is mandatory.** Every HTTP call passes through per-domain pacing and
   a cooldown after a block; a global pressure multiplier (AIMD) slows the whole
   system when a provider fights back. Daily caps follow warmup phases.
3. **Warmup is phase-based.** A brand-new agent account must not create accounts or
   send emails immediately. `account_created_at` in config drives
   outbound/harvest caps (0 outbound for the first 3 days by default).
4. **Real Chrome, not headless.** P2 attaches browser-use to a dedicated headful
   Chrome (Xvfb) with a persistent profile over CDP. Captcha resistance comes from
   a real profile + residential IP + human pacing, not from "no automation".
5. **Human-in-the-loop.** VNC access to the agent's browser + Telegram alerts for
   hard blockers (captcha, phone verification, refusal). The agent keeps working
   on other providers meanwhile.
6. **Gmail via the browser.** The agent has its own Google account and reads
   verification emails / sends outreach through the dedicated browser. A
   contact-form fallback covers bounces.
7. **Keyless first.** P1 connects providers that need no credentials to prove the
   whole pipeline before spending reputation on onboarding.
8. **Atomic writes everywhere** (`.tmp` → `os.replace`); orphan tmp files are
   cleaned on startup.
9. **Operator observability.** A daily markdown journal (`journal/`) makes the
   agent's activity auditable, and plain files (`control/directives.md`,
   `control/inbox.md`) give the human a low-tech way to steer it. Both are
   git-ignored runtime state.
10. **Reuse the OpenCode Go subscription.** `llm/client.py` reads the token opencode
    already caches (`~/.local/share/opencode/auth.json` → `opencode-go`) so no
    separate key is needed, and injects the `x-opencode-session` / `User-Agent`
    headers Zen requires.

## Milestones

- **P0+P1** (this): heartbeat, catalog, governor, 5 keyless providers, normalize,
  unified API.
- **P2**: browser-use onboarding + Gmail-via-browser + keyed providers.
- **P3**: autonomous discovery (GLAM SPARQL, directories).
- **P4**: connector self-repair, dashboard, scale to hundreds of providers.
