# P2 — the agentic layer (Stirrup)

## Why Stirrup

The heartbeat (control plane) stays home-made: durable jobs, crash recovery,
governor. It is deterministic and must not be an LLM loop.

For the **cognition/action** layer (obtain access, contact providers) we use
**Stirrup** (Artificial Analysis), the same framework already used in
`youtube-shorts-pipeline/research/histoire_industrie`. It is lightweight and
handles agent sessions, the tool-calling loop, and interruption caching
(`agent.session(...)`).

The browser actuators are **browser-use** attached to the dedicated Chrome over
CDP. Following the proven pattern, the agent is **not** given the DOM: it gets a
small set of **deterministic business tools**, which keeps tokens low and loops
rare.

## Layout

```
src/mnemosyne/
├── browser/
│   ├── stirrup_client.py   ZenChatClient (User-Agent + x-opencode-session) + builder
│   └── session.py          browser-use BrowserSession bound to CDP
├── agents/
│   ├── prompts.py          system/task prompts (transparency baked in)
│   ├── tools.py            BrowserToolProvider / OutreachToolProvider (deterministic tools)
│   ├── onboarding.py       run_onboarding(config, descriptor) -> AgentOutcome
│   └── outreach.py         run_outreach(config, descriptor, ask, ...) -> AgentOutcome
└── heartbeat/jobs.py       handle_onboard / handle_outreach (governed, journalled)
```

## Tools exposed to the agent

Common (browser): `goto`, `read_page`, `list_links`, `fill`, `click`,
`press_enter`, `blocked_status`, `remember`, `request_human`, `task_done`.

Outreach adds: `send_email` (Gmail via the browser), `submit_contact_form`,
`read_inbox`.

Extraction, persistence and wall detection are done in code; the agent only
decides the next step.

## Governance & safety

- `handle_onboard` requires `governor.allowed("onboard")`; `handle_outreach`
  requires `governor.allowed("outbound")`. Both respect the warmup phases.
- Any captcha / phone verification / refusal raises `request_human` → Telegram
  alert + journal entry, then the agent stops (never loops).
- Outreach text is generated from `identity.py`; the disclosure line (who the
  agent is + repo URL) is mandatory.
- Credentials found during onboarding are stored in the encrypted vault via the
  `remember` / `task_done(api_key=...)` tools.

## Running

The `browser` extra is required:

```bash
pip install -e '.[browser]'
```

Prerequisites: the dedicated Chrome is up and signed into Google (see
`RUNBOOK.md`). Then the heartbeat enqueues `onboard` jobs for providers with
`auth != none`, gated by the governor.

## Status

The framework, prompts, tools, governance and heartbeat wiring are implemented.
Provider-specific DOM details (exact selectors of each signup form / contact
page) are refined per provider when onboarding it — the deterministic-tools
design keeps those changes local to `tools.py`.
