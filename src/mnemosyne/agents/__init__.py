"""Autonomous agents.

* ``mailbox`` / ``supervisor`` — durable messages + deterministic turn-taking.
* ``browser_agent`` — the Stirrup browser agent (Chrome via browser-harness).
* ``dev`` (package)      — the coder agent (repo, tests, git/PR).
* ``warmup``             — human-like browsing that ages the account.

Stirrup / browser-harness imports stay inside these modules so the core
(heartbeat, API) works without the ``browser`` extra.
"""
