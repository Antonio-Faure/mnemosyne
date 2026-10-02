"""Per-task persistent sessions: the stirrup cache keyed by frozen task text.

The ping-pong contract: a reply NEVER changes the session (the frozen text
keeps the cache key stable); the history grows in the cache; the cache dies
with the task.
"""

from __future__ import annotations

import types

import pytest

from mnemosyne.agents.session_cache import (
    cache_base_dir,
    drop_session_cache,
    inject_reply,
    persist_session,
    session_task_text,
)
from mnemosyne.config import get_config


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    config = get_config()
    monkeypatch.setattr(type(config), "data_path", property(lambda self: tmp_path))
    return config


def _fake_agent(task: dict, agent: str):
    from stirrup.core.cache import CacheState, compute_task_hash
    from stirrup.core.models import SystemMessage, UserMessage

    text = session_task_text(agent, task)
    task_hash = compute_task_hash(text)
    state = CacheState(
        msgs=[SystemMessage(content="sys"), UserMessage(content=text)],
        full_msg_history=[],
        task_hash=task_hash,
        agent_name=agent,
    )
    return types.SimpleNamespace(_current_run_state=state, _current_task_hash=task_hash), text


def test_session_text_is_frozen_per_task_and_agent(cfg):
    task = {"id": 3, "objective": "l'objectif de la tâche"}
    browser_text = session_task_text("browser", task)
    coder_text = session_task_text("coder", task)
    assert browser_text != coder_text, "les deux têtes ont chacune leur cache"
    assert session_task_text("browser", task) == browser_text, "le texte ne bouge jamais"
    assert "l'objectif de la tâche" in browser_text


def test_persist_then_inject_then_resume(cfg):
    """finish → persist → reply → inject → resume: the same session, enriched."""
    task = {"id": 3, "objective": "demande le titre de example.com"}
    fake, text = _fake_agent(task, "browser")

    persist_session(cfg, fake, "browser")  # stirrup alone would NOT cache a finish

    run_text = inject_reply(cfg, "browser", task, "réponse du codeur : Example Domain")
    assert run_text == text, "le texte figé ne doit pas changer (clé de cache stable)"

    from stirrup.core.cache import CacheManager, compute_task_hash

    manager = CacheManager(cache_base_dir=cache_base_dir(cfg), clear_on_success=False)
    loaded = manager.load_state(compute_task_hash(text))
    assert loaded is not None
    assert loaded.msgs[-1].content == "réponse du codeur : Example Domain"


def test_inject_without_session_rides_along_on_the_first_activation(cfg):
    """No cache yet: the reply joins the task text (it becomes the opening msg)."""
    task = {"id": 4, "objective": "l'objectif"}
    run_text = inject_reply(cfg, "browser", task, "la réponse")
    assert run_text == f"{session_task_text('browser', task)}\n\nla réponse"


def test_the_sessions_die_with_the_task(cfg):
    task = {"id": 5, "objective": "l'objectif"}
    fake, _ = _fake_agent(task, "browser")
    persist_session(cfg, fake, "browser")

    from stirrup.core.cache import CacheManager, compute_task_hash

    manager = CacheManager(cache_base_dir=cache_base_dir(cfg), clear_on_success=False)
    assert manager.load_state(compute_task_hash(session_task_text("browser", task))) is not None
    drop_session_cache(cfg, task)
    assert manager.load_state(compute_task_hash(session_task_text("browser", task))) is None
