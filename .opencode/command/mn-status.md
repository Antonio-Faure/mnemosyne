---
description: Show mnemosyne status and recent heartbeat logs
agent: mnemosyne
---

Run `.venv/bin/mnemosyne status` (or `make status`) and
`docker compose logs --tail=80 mnemosyne`.

Summarize: provider states (connected/degraded/broken), asset counts, governor
pressure and daily caps, and any ERROR lines. Propose a concrete next action if
something is wrong. Do not modify any file.
