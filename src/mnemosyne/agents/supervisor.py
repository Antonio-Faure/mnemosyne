"""Deterministic supervisor for the bi-agent: the TASK QUEUE.

The operator touches only the queue (add, list, cancel). Everything else is a
task's internal life: each task owns a temporary mailbox and at most one live
session per agent. A task spawns ONE session if its starting agent never
writes to the other, TWO sessions when the ping-pong starts — and the
ping-pong is UNLIMITED: every reply reopens the agent's existing session
(stirrup cache), so each agent keeps the full context of its part. The only
case of more than two sessions is stirrup's own context compaction.

No LLM manager: a simple state machine, one activation at a time.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from mnemosyne.agents.mailbox import AGENTS, Mailbox
from mnemosyne.agents.session_cache import (
    drop_session_cache,
    inject_reply,
)
from mnemosyne.config import Config
from mnemosyne.db import NOTE_MAX_CHARS, Database
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
    task_id: int,
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
            task_id=task_id,
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
    task_id: int,
    max_turns: int | None = None,
):
    from mnemosyne.agents.browser_agent import run_browser_agent

    return await run_browser_agent(
        config,
        task,
        mailbox=mailbox,
        journal=journal,
        vault_get=vault_get,
        task_id=task_id,
        max_turns=max_turns,
    )


_RUNNERS = {"coder": _run_coder, "browser": _run_browser}

#: a browser session may run long (up to 400 turns); hold the Chrome lease well
#: past the longest plausible session
BROWSER_LEASE_S = 18000

#: one pilot at a time: two concurrent supervisors would run two coder turns in
#: the same git worktree and two browser turns against the same Chrome session.
#: Held per activation (an activation may itself run long — no time cap).
AGENCY_LEASE_S = 8 * 3600


def _task_with_directives(config: Config, task: str) -> str:
    """Append the operator's standing directives (control/directives.md)."""
    try:
        from mnemosyne.journal import Control

        directives = (Control(config.control_path).directives() or "").strip()
    except Exception:  # noqa: BLE001 - directives must never break a turn
        directives = ""
    if not directives:
        return task
    return f"{task}\n\n---\nCONSIGNES PERMANENTES DE L'OPÉRATEUR :\n{directives}"


#: The note is the mailbox record of an activation: an agent's factual report
#: carries the delivery link, the verified duration, what is left.
def outcome_status_note(finish: str, error: str | None) -> tuple[str, str]:
    """Status and stored note of an activation, with the report kept readable."""
    if error is not None:
        return "failed", error[:NOTE_MAX_CHARS]
    if finish:
        return "handled", finish[:NOTE_MAX_CHARS]
    return "review", "agent stopped without calling finish"


def _branch_has_commits(config: Config, branch: str) -> bool:
    """True if the branch exists locally with commits ahead of the base branch."""
    repo = Path(config.dev.repo_path or config.root)
    res = subprocess.run(
        ["git", "rev-list", "--count", f"{config.dev.base_branch}..{branch}"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    return res.stdout.strip().isdigit() and int(res.stdout.strip()) > 0


def _settle_discovery(config: Config, db: Database, task: dict, branch: str | None) -> None:
    """Close the discovery lifecycle of a connect task, like `connect-next` does.

    'connected' = a branch with commits exists — not a source that works (the
    human reviews the PR); 'failed' = no branch, so the host stays replayable.
    Non-connect tasks (and tasks posted outside the queue) are left alone.
    """
    try:
        payload = json.loads(task.get("payload") or "{}")
    except ValueError:
        return
    source_id = payload.get("source_id")
    if payload.get("kind") != "connect" or not source_id:
        return
    status = "connected" if branch and _branch_has_commits(config, branch) else "failed"
    db.set_discovery_status(source_id, status)
    log.info("découverte %s → %s (tâche #%s)", source_id, status, task["id"])


#: consecutive transient provider failures tolerated before a task is failed
_TRANSIENT_MAX_ATTEMPTS = 5


def _is_transient_provider_error(exc: BaseException) -> bool:
    """True for retryable LLM/network failures: 5xx, 429, timeouts, drops.

    A provider blip must not kill a 20-minute session: the activation is
    interrupted, the task stays open, and the next tick resumes it.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        try:
            from openai import (
                APIConnectionError,
                APIStatusError,
                APITimeoutError,
                RateLimitError,
            )

            if isinstance(current, (APIConnectionError, APITimeoutError, RateLimitError)):
                return True
            if isinstance(current, APIStatusError) and current.status_code >= 500:
                return True
        except ImportError:  # the agent extra is optional
            pass
        if isinstance(
            current,
            (
                httpx.ConnectError,
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.RemoteProtocolError,
            ),
        ):
            return True
        if re.search(r"Error code: 5\d\d\b|Connection error|timed out", str(current)):
            return True
        current = current.__cause__ or current.__context__
    return False


def _acquire_browser_lease(db: Database, agent: str) -> bool | None:
    """True = lease held, False = not needed, None = needed but taken."""
    if agent != "browser":
        return False
    if db.try_lease("browser", ttl_s=BROWSER_LEASE_S):
        return True
    log.info("browser lease held elsewhere; skipping this activation")
    return None


def _turns_of(outcome: object) -> int | None:
    """Turn count of a finished activation (attribute or outcome dict)."""
    turns = getattr(outcome, "turns", None)
    if isinstance(turns, int):
        return turns
    extra = getattr(outcome, "outcome", None)
    if isinstance(extra, dict) and isinstance(extra.get("turns"), int):
        return extra["turns"]
    return None


async def _activate_session(
    config: Config,
    db: Database,
    mailbox: Mailbox,
    journal: Journal | None,
    vault_get,
    agent: str,
    task: dict,
    messages: list[dict],
) -> dict:
    """One activation of (task, agent): reopen the session, feed it any reply,
    run it to its finish. The task closes when its mailbox comes out empty."""
    task_id = task["id"]
    if messages:
        reply_text = "\n\n".join(
            (
                f"--- réponse de l'opérateur ({m['created_at']}) ---\n{m['body']}"
                if m["sender"] == "operator"
                else f"--- message de {m['sender']} ({m['created_at']}) ---\n{m['body']}"
            )
            for m in messages
        )
        task_text = _task_with_directives(config, inject_reply(config, agent, task, reply_text))
        # consumed: they now live in the session history (no duplicate on resume)
        for message in messages:
            mailbox.mark(message["id"], "handled")
    else:
        task_text = _task_with_directives(config, inject_reply(config, agent, task))
    db.touch_task_activation(task_id)

    outcome = None
    error: str | None = None
    error_exc: BaseException | None = None
    try:
        outcome = await _RUNNERS[agent](
            config,
            task_text,
            mailbox,
            journal,
            vault_get,
            task_id=task_id,
            max_turns=task["turn_cap"],
        )
    except Exception as exc:  # noqa: BLE001 - one agent must not kill the agency
        error = str(exc)
        error_exc = exc
        log.error("agent %s failed: %s", agent, exc)

    finish = finish_text(getattr(outcome, "finish", None)) or ""
    # the operator may have cancelled the task while this session was running:
    # never resurrect it — a non-'running' row is left exactly as the operator set it
    task_now = db.get_task(task_id)
    if task_now is None or task_now["status"] != "running":
        log.info(
            "tâche #%s déjà fermée côté opérateur (%s) — fermeture annulée",
            task_id,
            task_now["status"] if task_now else "absente",
        )
        db.delete_kv(f"transient:{task_id}")
        return {"agent": agent, "task_id": task_id, "finish": finish, "turns": _turns_of(outcome),
                "branch": getattr(outcome, "branch", None), "error": error}

    if error:
        transient_key = f"transient:{task_id}"
        if error_exc is not None and _is_transient_provider_error(error_exc):
            attempts = int(db.get_kv(transient_key, 0)) + 1
            if attempts <= _TRANSIENT_MAX_ATTEMPTS:
                db.set_kv(transient_key, attempts)
                log.warning(
                    "tâche #%s : erreur provider transitoire (%s) — reprise au prochain "
                    "tick (%d/%d)",
                    task_id,
                    error[:80],
                    attempts,
                    _TRANSIENT_MAX_ATTEMPTS,
                )
                if journal:
                    journal.append(
                        f"tâche #{task_id} : erreur provider transitoire — tentative "
                        f"{attempts}/{_TRANSIENT_MAX_ATTEMPTS}, reprise au prochain tick",
                        level="warn",
                        source="agency",
                    )
                return {"agent": agent, "task_id": task_id, "finish": "",
                        "turns": _turns_of(outcome),
                        "branch": getattr(outcome, "branch", None), "error": error}
            error = f"{error} — abandon après {attempts} tentatives transitoires"
        db.delete_kv(transient_key)
        db.set_task_status(task_id, "failed", note=error[:NOTE_MAX_CHARS])
        drop_session_cache(config, task)
        db.delete_task_messages(task_id)
        _settle_discovery(config, db, task, getattr(outcome, "branch", None))
        if journal:
            journal.append(
                f"tâche #{task_id} échouée : {error[:160]}", level="error", source="agency"
            )
        return {"agent": agent, "task_id": task_id, "finish": "", "turns": _turns_of(outcome),
                "branch": getattr(outcome, "branch", None), "error": error}

    if mailbox.pending_count(task_id) == 0:
        status = "done" if finish else "review"
        db.set_task_status(task_id, status, note=finish[:NOTE_MAX_CHARS] or None)
        db.delete_kv(f"transient:{task_id}")
        drop_session_cache(config, task)
        db.delete_task_messages(task_id)
        _settle_discovery(config, db, task, getattr(outcome, "branch", None))
        if journal:
            journal.append(
                f"tâche #{task_id} — {status} (agent {agent})"
                + (f" : {finish[:160]}" if finish else ""),
                source="agency",
            )
    return {"agent": agent, "task_id": task_id, "finish": finish, "turns": _turns_of(outcome),
            "branch": getattr(outcome, "branch", None), "error": None}


async def run_pending_once(config: Config, *, journal=None, vault_get=None) -> dict | None:
    """Background activation: the running task continues first, else the oldest
    pending task starts. Called by the heartbeat. Idle => no agent, no cost.

    Returns the activation record (agent, task_id, finish, turns, branch) so
    callers can act on it — e.g. connect-next reads the branch to close the
    discovery lifecycle.

    Ping-pong is unlimited BY DESIGN: each activation is one job; the task
    stays 'running' until one of its sessions finishes with an empty mailbox.
    """
    db = Database(config.db_file())
    mailbox = Mailbox(db)
    if not db.try_lease("agency", ttl_s=AGENCY_LEASE_S, owner=f"heartbeat:{os.getpid()}"):
        return None
    held_browser: bool | None = False
    try:
        task = db.next_task()
        if task is None:
            return None
        if task["status"] == "pending":
            agent = task["start_agent"]
            recipients = [r for r in mailbox.recipients(task["id"]) if r in AGENTS]
            agent = recipients[0] if recipients else agent
            messages = mailbox.pending_for(task["id"], agent)
            db.set_task_status(task["id"], "running")
        else:
            recipients = [r for r in mailbox.recipients(task["id"]) if r in AGENTS]
            if not recipients:
                # no reply waiting: either the last activation ended cleanly and
                # is about to close, or the process died mid-activation — either
                # way, RESUME the starting agent's session (stirrup cache
                # restores the exact state; the agent closes or continues).
                agent = task["start_agent"]
                messages = []
            else:
                agent = recipients[0]
                messages = mailbox.pending_for(task["id"], agent)
        held_browser = _acquire_browser_lease(db, agent)
        if held_browser is None:
            return None
        note = (
            f"agency (fond) → agent {agent} : tâche #{task['id']} : "
            f"{len(messages)} message(s)"
        )
        log.info(note)
        if journal:
            journal.append(note, source="agency")
        return await _activate_session(
            config, db, mailbox, journal, vault_get, agent, task, messages
        )
    finally:
        if held_browser:
            db.release_lease("browser")
        db.release_lease("agency")
        db.close()


async def drain_queue(
    config: Config,
    *,
    journal: Journal | None = None,
    vault_get=None,
) -> AgencyResult:
    """Run activations until the queue is empty. No handoff budget — the
    ping-pong runs to its end; Ctrl+C caches the open sessions, a later run
    resumes them."""
    result = AgencyResult(start="queue")
    while True:
        info = await run_pending_once(config, journal=journal, vault_get=vault_get)
        if info is None:
            break
        result.turns.append(info)
    return result


async def run_agency(
    config: Config,
    task: str,
    *,
    start: str | None = None,
    journal: Journal | None = None,
    vault_get=None,
) -> AgencyResult:
    """CLI pilot: enqueue the operator task, then drain the queue."""
    db = Database(config.db_file())
    target = start or pick_agent(task)
    db.enqueue_task(target, task)
    db.close()
    result = await drain_queue(config, journal=journal, vault_get=vault_get)
    result.start = target
    return result
