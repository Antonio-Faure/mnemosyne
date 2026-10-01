"""Deterministic supervisor for the bi-agent.

The agents never launch each other: they post messages to the mailbox, and this
supervisor runs ONE agent at a time (turn-taking) until the mailbox is drained
or the hand-off budget is reached. No LLM manager — it is a simple state machine
so the cost stays low and the behaviour is predictable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from mnemosyne.agents.mailbox import Mailbox
from mnemosyne.config import Config
from mnemosyne.db import Database
from mnemosyne.journal import Journal
from mnemosyne.logger import get_logger
from mnemosyne.util import finish_text

log = get_logger("supervisor")

#: words that route an initial task to the browser agent
_BROWSER_HINTS = (
    "http://",
    "https://",
    "www.",
    "gmail",
    "mail",
    "navig",
    "site",
    "compte",
    "signup",
    "s'inscrire",
    "formulaire",
    "wetransfer",
    "we transfer",
    "télécharg",
    "upload",
    "vidéo",
    "capture",
    "screenshot",
    "warmup",
)


def pick_agent(task: str) -> str:
    """Route an operator task to 'browser' or 'coder' (heuristic)."""
    low = task.lower()
    return "browser" if any(h in low for h in _BROWSER_HINTS) else "coder"


@dataclass
class AgencyResult:
    start: str
    turns: list[dict] = field(default_factory=list)
    stop_reason: str = "no_pending"


async def _run_coder(config: Config, task: str, mailbox: Mailbox, journal, vault_get):
    from mnemosyne.dev.agent import run_dev_agent
    from mnemosyne.dev.worktree import add_worktree, remove_worktree

    repo = Path(config.dev.repo_path or config.root)
    worktree = add_worktree(repo, Path(config.data_path) / "agent-worktree", config.dev.base_branch)
    try:
        return await run_dev_agent(
            config, task, vault_get=vault_get, journal=journal, repo=worktree, mailbox=mailbox
        )
    finally:
        remove_worktree(repo, worktree)


async def _run_browser(config: Config, task: str, mailbox: Mailbox, journal, vault_get):
    from mnemosyne.agents.browser_agent import run_browser_agent

    return await run_browser_agent(
        config, task, mailbox=mailbox, journal=journal, vault_get=vault_get
    )


_RUNNERS = {"coder": _run_coder, "browser": _run_browser}


async def run_pending_once(config: Config, *, journal=None, vault_get=None) -> str | None:
    """Background turn: run ONE agent for the oldest pending message (if any).

    Called by the heartbeat so the loop continues without the operator once the
    initial task is posted. Idle (no pending message) => no agent, no cost.
    """
    from mnemosyne.util import finish_text

    db = Database(config.db_file())
    mailbox = Mailbox(db)
    try:
        pending = mailbox.pending_recipients()
        if not pending:
            return None
        agent = pending[0]
        message = mailbox.claim_for(agent, owner=f"heartbeat:{os.getpid()}")
        if message is None:
            return None
        note = f"agency (fond) → agent {agent} : {message['body'][:160]}"
        log.info(note)
        if journal:
            journal.append(note, source="agency")
        try:
            outcome = await _RUNNERS[agent](config, message["body"], mailbox, journal, vault_get)
            finish = finish_text(getattr(outcome, "finish", None)) or ""
            if finish:
                mailbox.mark(message["id"], "handled", finish[:200])
            else:
                mailbox.mark(
                    message["id"], "review", "agent stopped without task_done"
                )
        except Exception as exc:  # noqa: BLE001
            log.error("agency background: agent %s failed: %s", agent, exc)
            mailbox.mark(message["id"], "failed", str(exc)[:200])
        return agent
    finally:
        db.close()


async def run_agency(
    config: Config,
    task: str,
    *,
    start: str | None = None,
    max_handoffs: int = 6,
    journal: Journal | None = None,
    vault_get=None,
) -> AgencyResult:
    """Post the operator task, then run agents turn-by-turn until the mailbox drains."""
    db = Database(config.db_file())
    mailbox = Mailbox(db)
    target = start or pick_agent(task)
    mailbox.post("operator", target, task)
    result = AgencyResult(start=target)
    last: str | None = None
    failures = 0

    try:
        for _ in range(max(1, max_handoffs)):
            pending = mailbox.pending_recipients(prefer_exclude=last)
            if not pending:
                result.stop_reason = "no_pending"
                break
            agent = pending[0]
            message = mailbox.claim_for(agent, owner=f"cli:{os.getpid()}")
            if message is None:
                result.stop_reason = "busy"
                break
            note = f"superviseur → agent {agent} : {message['body'][:200]}"
            log.info(note)
            if journal:
                journal.append(note, source="agency")
            try:
                outcome = await _RUNNERS[agent](
                    config, message["body"], mailbox, journal, vault_get
                )
                finish = finish_text(getattr(outcome, "finish", None)) or ""
                if finish:
                    mailbox.mark(message["id"], "handled", finish[:200])
                else:
                    mailbox.mark(
                        message["id"], "review", "agent stopped without task_done"
                    )
                result.turns.append(
                    {"agent": agent, "message_id": message["id"], "finish": finish}
                )
            except Exception as exc:  # noqa: BLE001 - one agent must not kill the agency
                failures += 1
                log.error("agent %s failed: %s", agent, exc)
                mailbox.mark(message["id"], "failed", str(exc)[:200])
                result.turns.append(
                    {"agent": agent, "message_id": message["id"], "error": str(exc)}
                )
            last = agent
        else:
            result.stop_reason = "max_handoffs"
        if failures:
            result.stop_reason = "failed"
    finally:
        db.close()
    return result
