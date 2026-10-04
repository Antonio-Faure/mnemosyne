"""Per-task persistent sessions (the ping-pong backbone).

The task model: each task owns a temporary mailbox and AT MOST one live
session per agent. When an agent finishes its activation and the other agent
replies, the SAME session is reopened — stirrup's cache keeps the full message
history, so each agent holds the context of its whole part of the task. No
handoff budget: the ping-pong is unlimited; the queue (operator-facing) is the
guard — a task can be cancelled at any moment.

stirrup already provides the two mechanisms this rests on:
- persistence/resume: `stirrup.core.cache` (message history saved at exit,
  restored by `session(resume=True)`);
- compaction: `context_summarization_cutoff` summarizes the history when it
  grows past a fraction of the model's window.

The cache key is derived from the task text, so the text passed to `run()` is
frozen at task creation (`session_task_text`); incoming replies are appended
to the cached history instead of changing the text.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from mnemosyne.config import Config
from mnemosyne.logger import get_logger

log = get_logger("sessions")


def cache_base_dir(config: Config) -> Path:
    """stirrup's cache must survive container rebuilds: keep it on the data volume."""
    import stirrup.core.cache as stirrup_cache

    target = Path(config.data_path) / "stirrup-cache"
    if stirrup_cache.DEFAULT_CACHE_DIR != target:
        stirrup_cache.DEFAULT_CACHE_DIR = target
    return target


def session_task_text(agent: str, task: dict) -> str:
    """The FROZEN session text: same at every activation of (task, agent), so
    stirrup's cache key is stable and `resume=True` reopens the same session."""
    return f"[tâche #{task['id']} — agent {agent}]\n\n{task['objective']}"


def inject_reply(config: Config, agent: str, task: dict, reply_text: str | None = None) -> str:
    """Prepare the cached session for this activation; return the text to run.

    * a reply is appended to the cached history (the text itself stays FROZEN:
      changing it would change the cache key and open a fresh session);
    * `run_metadata_by_turn` is dropped from the cache: stirrup's logger
      aggregates it at run end, and a resumed session would mix cached JSON
      dicts with live `ToolUseCountMetadata` instances — `dict +
      ToolUseCountMetadata` crashes the whole run (seen on the DPLA task). It
      is display-only, so the cache never carries it.
    """
    from stirrup.core.cache import CacheManager, compute_task_hash
    from stirrup.core.models import UserMessage

    text = session_task_text(agent, task)
    task_hash = compute_task_hash(text)
    manager = CacheManager(cache_base_dir=cache_base_dir(config), clear_on_success=False)
    state = manager.load_state(task_hash)
    if state is None:
        if reply_text:
            log.info("première activation (%s, tâche #%s) avec réponse intégrée", agent, task["id"])
            return f"{text}\n\n{reply_text}"
        return text
    changed = False
    if reply_text:
        state.msgs.append(UserMessage(content=reply_text))
        changed = True
    if getattr(state, "run_metadata_by_turn", None):
        state.run_metadata_by_turn = {}
        changed = True
    if changed:
        manager.save_state(task_hash, state)
    if reply_text:
        log.info(
            "session réouverte (%s, tâche #%s) : %d messages d'historique",
            agent,
            task["id"],
            len(state.msgs),
        )
    return text


def persist_session(config: Config, agent, agent_name: str) -> None:
    """Save the session state AFTER a successful activation (finish included).

    stirrup only caches on non-success exits (`should_cache` in its __aexit__:
    exception, or no finish) — a clean finish writes NOTHING, which would kill
    the ping-pong (the next hop would find no session). The state is on the
    Agent instance after run(); we save it with the same CacheManager.
    """
    from stirrup.core.cache import CacheManager

    state = getattr(agent, "_current_run_state", None)
    task_hash = getattr(agent, "_current_task_hash", None)
    if state is None or task_hash is None:
        log.warning("aucun état de session à persister (%s)", agent_name)
        return
    if getattr(state, "run_metadata_by_turn", None):
        # never let cached metadata mix with live ToolUseCountMetadata on resume
        state.run_metadata_by_turn = {}
    CacheManager(cache_base_dir=cache_base_dir(config), clear_on_success=False).save_state(
        task_hash, state
    )


def drop_session_cache(config: Config, task: dict) -> None:
    """The temporary sessions die with the task (both agents, exact hashes)."""
    from stirrup.core.cache import compute_task_hash

    base = cache_base_dir(config)
    for agent in ("coder", "browser"):
        task_hash = compute_task_hash(session_task_text(agent, task))
        shutil.rmtree(base / task_hash, ignore_errors=True)
