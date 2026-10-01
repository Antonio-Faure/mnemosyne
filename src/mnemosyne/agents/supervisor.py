"""Deterministic supervisor for the bi-agent.

The agents never launch each other: they post messages to the mailbox, and this
supervisor runs ONE agent at a time (turn-taking) until the mailbox is drained
or the hand-off budget is reached. No LLM manager — it is a simple state machine
so the cost stays low and the behaviour is predictable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mnemosyne.agents.mailbox import Mailbox
from mnemosyne.config import Config
from mnemosyne.db import Database
from mnemosyne.journal import Journal
from mnemosyne.logger import get_logger

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

    try:
        for _ in range(max(1, max_handoffs)):
            pending = mailbox.pending_recipients(prefer_exclude=last)
            if not pending:
                result.stop_reason = "no_pending"
                break
            agent = pending[0]
            message = mailbox.next_for(agent)
            if message is None:
                result.stop_reason = "no_pending"
                break
            mailbox.mark(message["id"], "running")
            note = f"superviseur → agent {agent} : {message['body'][:200]}"
            log.info(note)
            if journal:
                journal.append(note, source="agency")
            try:
                outcome = await _RUNNERS[agent](
                    config, message["body"], mailbox, journal, vault_get
                )
                mailbox.mark(message["id"], "handled", (outcome.finish or "")[:200] or None)
                result.turns.append(
                    {"agent": agent, "message_id": message["id"], "finish": outcome.finish}
                )
            except Exception as exc:  # noqa: BLE001 - one agent must not kill the agency
                log.error("agent %s failed: %s", agent, exc)
                mailbox.mark(message["id"], "failed", str(exc)[:200])
                result.turns.append(
                    {"agent": agent, "message_id": message["id"], "error": str(exc)}
                )
            last = agent
        else:
            result.stop_reason = "max_handoffs"
        if result.stop_reason == "max_handoffs" and not mailbox.pending_recipients():
            result.stop_reason = "no_pending"
    finally:
        db.close()
    return result
