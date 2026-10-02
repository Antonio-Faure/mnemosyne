"""Deterministic supervisor for the bi-agent.

The agents never launch each other: they post messages to the mailbox, and this
supervisor runs ONE agent at a time (turn-taking) until the mailbox is drained
or the hand-off budget is reached. No LLM manager — it is a simple state machine
so the cost stays low and the behaviour is predictable.
"""

from __future__ import annotations

import os
import re
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


async def _run_coder(
    config: Config,
    task: str,
    mailbox: Mailbox,
    journal,
    vault_get,
    max_turns: int | None = None,
):
    from mnemosyne.dev.agent import run_dev_agent
    from mnemosyne.dev.worktree import add_worktree, remove_worktree

    repo = Path(config.dev.repo_path or config.root)
    worktree = add_worktree(repo, Path(config.data_path) / "agent-worktree", config.dev.base_branch)
    try:
        return await run_dev_agent(
            config,
            task,
            vault_get=vault_get,
            journal=journal,
            repo=worktree,
            mailbox=mailbox,
            max_turns=max_turns,
        )
    finally:
        remove_worktree(repo, worktree)


async def _run_browser(
    config: Config,
    task: str,
    mailbox: Mailbox,
    journal,
    vault_get,
    max_turns: int | None = None,
):
    from mnemosyne.agents.browser_agent import run_browser_agent

    return await run_browser_agent(
        config,
        task,
        mailbox=mailbox,
        journal=journal,
        vault_get=vault_get,
        max_turns=max_turns,
    )


_RUNNERS = {"coder": _run_coder, "browser": _run_browser}

#: a browser session may run long (up to 400 turns); hold the Chrome lease well
#: past the longest plausible session
BROWSER_LEASE_S = 18000

#: one pilot at a time: two concurrent supervisors would run two coder turns in
#: the same git worktree and two browser turns against the same Chrome session.
#: Longer than the browser lease, since a pilot may chain several turns.
AGENCY_LEASE_S = 8 * 3600


def _task_with_directives(config: Config, task: str) -> str:
    """Append the operator's standing directives (control/directives.md)."""
    try:
        from mnemosyne.journal import Control

        directives = (Control(config.control_path).directives() or "").strip()
    except Exception:  # noqa: BLE001 - directives must never block a turn
        directives = ""
    if not directives:
        return task
    return f"{task}\n\n---\nCONSIGNES PERMANENTES DE L'OPÉRATEUR :\n{directives}"


def _acquire_browser_lease(db: Database, agent: str) -> bool | None:
    """True = lease held, False = not needed, None = needed but taken."""
    if agent != "browser":
        return False
    if db.try_lease("browser", ttl_s=BROWSER_LEASE_S):
        return True
    log.info("browser lease held elsewhere; skipping this turn")
    return None


#: a message may cap its own turn: a first line `[[tour: 40]]` bounds the session
#: (used by the warmup mission, which must be short and boring)
_TURN_CAP_RE = re.compile(r"^\s*\[\[tour:\s*(\d+)\s*\]\]\s*$", re.M)


def _split_turn_cap(messages: list[dict]) -> tuple[list[dict], int | None]:
    """Extract (and strip) per-message turn caps from a batch of messages.

    A batch turns on the *longest* budget it contains: a short warmup mission
    batched with a full-length mission must not truncate the latter, so when any
    message has no cap the batch runs on the agent default.
    """
    caps: list[int] = []
    for message in messages:
        found = _TURN_CAP_RE.search(message["body"])
        if found:
            caps.append(int(found.group(1)))
    cap = max(caps) if caps and len(caps) == len(messages) else None
    cleaned: list[dict] = []
    for message in messages:
        body = _TURN_CAP_RE.sub("", message["body"]).strip()
        cleaned.append({**message, "body": body})
    return cleaned, cap


def _turns_of(outcome: object) -> int | None:
    """Turn count of a finished session (attribute or outcome dict)."""
    turns = getattr(outcome, "turns", None)
    if isinstance(turns, int):
        return turns
    extra = getattr(outcome, "outcome", None)
    if isinstance(extra, dict) and isinstance(extra.get("turns"), int):
        return extra["turns"]
    return None


def _batched_task(messages: list[dict]) -> str:
    """One task out of several pending messages (a report then an update...)."""
    if len(messages) == 1:
        return messages[0]["body"]
    parts = [
        f"Tu as {len(messages)} messages en attente. Traite-les en UNE seule passe "
        "(le dernier peut être une mise à jour du précédent), puis termine par "
        "finish avec un bilan unique.",
        "",
    ]
    for index, message in enumerate(messages, 1):
        parts.append(
            f"--- message {index}/{len(messages)} — de {message['sender']} "
            f"à {message['created_at']} ---"
        )
        parts.append(message["body"])
        parts.append("")
    return "\n".join(parts).strip()


async def _execute_turn(
    config: Config,
    agent: str,
    messages: list[dict],
    mailbox: Mailbox,
    journal,
    vault_get,
) -> dict:
    """Run one agent turn for a batch of claimed messages, then mark them all."""
    messages, turn_cap = _split_turn_cap(messages)
    note_prefix = f"{len(messages)} message(s)"
    outcome = None
    error: str | None = None
    try:
        outcome = await _RUNNERS[agent](
            config,
            _task_with_directives(config, _batched_task(messages)),
            mailbox,
            journal,
            vault_get,
            max_turns=turn_cap,
        )
    except Exception as exc:  # noqa: BLE001 - one agent must not kill the agency
        error = str(exc)
        log.error("agent %s failed: %s", agent, exc)
    finish = finish_text(getattr(outcome, "finish", None)) or ""
    if error is not None:
        status, note = "failed", error[:200]
    elif finish:
        status, note = "handled", finish[:200]
    else:
        status, note = "review", "agent stopped without calling finish"
    for message in messages:
        mailbox.mark(message["id"], status, note)
    turns = _turns_of(outcome)
    log.info(
        "agent %s terminé : %d message(s), %s tours, statut=%s",
        agent,
        len(messages),
        turns if turns is not None else "?",
        status,
    )
    return {
        "agent": agent,
        "turns": _turns_of(outcome),
        "message_ids": [m["id"] for m in messages],
        "message_id": messages[0]["id"],
        "batch": note_prefix,
        "finish": finish,
        "branch": getattr(outcome, "branch", None),
        "error": error,
    }


async def run_pending_once(config: Config, *, journal=None, vault_get=None) -> str | None:
    """Background turn: run ONE agent for its pending messages (if any).

    Called by the heartbeat so the loop continues without the operator once the
    initial task is posted. Idle (no pending message) => no agent, no cost.
    """
    db = Database(config.db_file())
    mailbox = Mailbox(db)
    held: bool | None = False
    # Same pilot lease as run_agency: the heartbeat turn must never overlap a
    # CLI run (two coder turns would share one git worktree).
    if not db.try_lease("agency", ttl_s=AGENCY_LEASE_S, owner=f"heartbeat:{os.getpid()}"):
        return None
    try:
        released = db.recover_stale_messages()
        if released:
            log.warning("released %d message(s) stuck in running", released)
        pending = mailbox.pending_recipients()
        if not pending:
            return None
        agent = pending[0]
        held = _acquire_browser_lease(db, agent)
        if held is None:
            return None
        messages = mailbox.claim_all_for(agent, owner=f"heartbeat:{os.getpid()}")
        if not messages:
            return None
        note = (
            f"agency (fond) → agent {agent} : {len(messages)} message(s) : "
            f"{messages[0]['body'][:140]}"
        )
        log.info(note)
        if journal:
            journal.append(note, source="agency")
        await _execute_turn(config, agent, messages, mailbox, journal, vault_get)
        return agent
    finally:
        if held:
            db.release_lease("browser")
        db.release_lease("agency")
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
    db.recover_stale_messages()
    target = start or pick_agent(task)
    result = AgencyResult(start=target)
    if not db.try_lease("agency", ttl_s=AGENCY_LEASE_S, owner=f"cli:{os.getpid()}"):
        # Another pilot is alive. We still post the task, so nothing is lost: the
        # running pilot drains the mailbox turn by turn and will serve it.
        mailbox.post("operator", target, task)
        log.info("agency lease held elsewhere; task left in the mailbox")
        db.close()
        result.stop_reason = "agency_busy"
        return result
    mailbox.post("operator", target, task)
    last: str | None = None
    failures = 0

    try:
        for _ in range(max(1, max_handoffs)):
            pending = mailbox.pending_recipients(prefer_exclude=last)
            if not pending:
                result.stop_reason = "no_pending"
                break
            agent = pending[0]
            held = _acquire_browser_lease(db, agent)
            if held is None:
                result.stop_reason = "browser_busy"
                break
            try:
                messages = mailbox.claim_all_for(agent, owner=f"cli:{os.getpid()}")
                if not messages:
                    result.stop_reason = "busy"
                    break
                note = (
                    f"superviseur → agent {agent} : {len(messages)} message(s) : "
                    f"{messages[0]['body'][:180]}"
                )
                log.info(note)
                if journal:
                    journal.append(note, source="agency")
                turn = await _execute_turn(
                    config, agent, messages, mailbox, journal, vault_get
                )
                if turn["error"]:
                    failures += 1
                result.turns.append(turn)
            finally:
                if held:
                    db.release_lease("browser")
            last = agent
        else:
            result.stop_reason = "max_handoffs"
        if failures:
            result.stop_reason = "failed"
    finally:
        db.release_lease("agency")
        db.close()
    return result
