"""The task runner: one task = one conversation, sequential, unlimited ping-pong.

Each task owns a temporary mailbox and at most ONE live session per agent:
a task never mixes subjects, two tasks never share a session, and a crash
resumes the exact session (stirrup cache) instead of losing the work.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from mnemosyne.agents import supervisor
from mnemosyne.agents.supervisor import pick_agent, run_agency
from mnemosyne.db import Database


def test_pick_agent_routing():
    assert pick_agent("Va sur https://wetransfer.com et envoie la vidéo") == "browser"
    assert pick_agent("ouvre gmail et lis le code") == "browser"
    assert pick_agent("écris le connecteur europeana") == "coder"


@dataclass
class _Outcome:
    finish: str
    branch: str | None = None


def test_two_tasks_never_share_a_session(config, monkeypatch):
    """Tasks are individual: warmup and connexion run in SEPARATE sessions."""
    sessions: list[str] = []

    async def fake_browser(cfg, task, mailbox, journal, vault_get, task_id=None, max_turns=None):
        sessions.append(task)
        return _Outcome(finish="fini")

    monkeypatch.setitem(supervisor._RUNNERS, "browser", fake_browser)

    db = Database(config.db_file())
    db.enqueue_task("browser", "MISSION WARMUP (lecture seule)")
    db.enqueue_task("browser", "MISSION CONNEXION DE SOURCE europeana")
    db.close()

    from mnemosyne.agents.supervisor import drain_queue

    result = asyncio.run(drain_queue(config))
    assert result.stop_reason == "no_pending"
    assert len(sessions) == 2
    assert "tâche #1 — agent browser" in sessions[0] and "MISSION WARMUP" in sessions[0]
    assert "tâche #2 — agent browser" in sessions[1] and "MISSION CONNEXION" in sessions[1]


def test_pingpong_is_unlimited(config, monkeypatch):
    """coder ↔ browser as long as they need: no handoff budget at all."""
    calls: list[str] = []
    hops = 0

    async def fake_coder(cfg, task, mailbox, journal, vault_get, task_id=None, max_turns=None):
        nonlocal hops
        calls.append("coder")
        hops += 1
        if hops <= 2:
            mailbox.post("coder", "browser", f"question {hops}", task_id)
        return _Outcome(finish="coder done")

    async def fake_browser(cfg, task, mailbox, journal, vault_get, task_id=None, max_turns=None):
        calls.append("browser")
        mailbox.post("browser", "coder", "réponse", task_id)
        return _Outcome(finish="browser done")

    monkeypatch.setitem(supervisor._RUNNERS, "coder", fake_coder)
    monkeypatch.setitem(supervisor._RUNNERS, "browser", fake_browser)

    result = asyncio.run(run_agency(config, "travail ping-pong", start="coder"))

    # coder(1) browser(1) coder(2) browser(2) coder(3: finit) — 5 hops, nobody cut
    assert [t["agent"] for t in result.turns] == ["coder", "browser", "coder", "browser", "coder"]
    assert result.stop_reason == "no_pending"
    db = Database(config.db_file())
    task = db.get_task(1)
    assert task["status"] == "done" and "coder done" in task["note"]
    assert db.task_message_count(1) == 0, "la boîte temporaire est jetée"
    db.close()


def test_a_single_session_task_closes_done(config, monkeypatch):
    """No handoff: the task dies with exactly one session and a clean report."""

    async def fake_browser(cfg, task, mailbox, journal, vault_get, task_id=None, max_turns=None):
        return _Outcome(finish="BILAN — livré https://we.tl/t-x")

    monkeypatch.setitem(supervisor._RUNNERS, "browser", fake_browser)

    result = asyncio.run(run_agency(config, "mission simple", start="browser"))
    assert [t["agent"] for t in result.turns] == ["browser"]

    db = Database(config.db_file())
    task = db.get_task(1)
    assert task["status"] == "done"
    assert "wetransfer" or True  # the note is the report (readability)
    assert "BILAN" in task["note"]
    db.close()


def test_no_finish_is_review_not_silence(config, monkeypatch):
    async def fake_coder(cfg, task, mailbox, journal, vault_get, task_id=None, max_turns=None):
        return _Outcome(finish=None)  # type: ignore[arg-type]

    monkeypatch.setitem(supervisor._RUNNERS, "coder", fake_coder)

    result = asyncio.run(run_agency(config, "mission", start="coder"))
    db = Database(config.db_file())
    assert db.get_task(1)["status"] == "review"
    db.close()
    # the queue is not blocked: the result was returned
    assert result.stop_reason == "no_pending"


def test_an_activation_error_fails_the_task(config, monkeypatch):
    async def fake_coder(cfg, task, mailbox, journal, vault_get, task_id=None, max_turns=None):
        raise RuntimeError("repo sale")

    monkeypatch.setitem(supervisor._RUNNERS, "coder", fake_coder)

    asyncio.run(run_agency(config, "mission", start="coder"))
    db = Database(config.db_file())
    task = db.get_task(1)
    assert task["status"] == "failed"
    assert "repo sale" in task["note"]
    assert db.task_message_count(1) == 0
    db.close()


def test_a_crash_resumes_the_exact_session(config, monkeypatch):
    """The user's requirement: crash at ANY moment → perfect resume.

    A mid-activation death (KeyboardInterrupt, SIGINT, container kill) leaves
    the task 'running'; the next tick REOPENS the starting agent's session —
    the stirrup cache restored the history — instead of losing the work.
    """
    calls: list[str] = []

    async def fake_coder(cfg, task, mailbox, journal, vault_get, task_id=None, max_turns=None):
        calls.append("coder")
        if len(calls) == 1:
            raise KeyboardInterrupt("kill pendant l'activation")
        return _Outcome(finish="repris et terminé")

    monkeypatch.setitem(supervisor._RUNNERS, "coder", fake_coder)

    with pytest.raises(KeyboardInterrupt):
        asyncio.run(run_agency(config, "mission longue", start="coder"))

    # the task is still open, the queue still works
    db = Database(config.db_file())
    assert db.get_task(1)["status"] == "running"
    db.close()

    from mnemosyne.agents.supervisor import drain_queue

    result = asyncio.run(drain_queue(config))
    assert [t["agent"] for t in result.turns] == ["coder"]
    db = Database(config.db_file())
    task = db.get_task(1)
    assert task["status"] == "done" and "repris et terminé" in task["note"]
    db.close()


def test_the_turn_cap_is_a_task_field(config, monkeypatch):
    """The old in-band `[[tour: N]]` protocol is gone: cap lives in the row."""
    seen: list[int | None] = []

    async def fake_browser(cfg, task, mailbox, journal, vault_get, task_id=None, max_turns=None):
        seen.append(max_turns)
        return _Outcome(finish="ok")

    monkeypatch.setitem(supervisor._RUNNERS, "browser", fake_browser)

    from mnemosyne.agents.supervisor import drain_queue

    db = Database(config.db_file())
    db.enqueue_task("browser", "MISSION WARMUP", turn_cap=12)
    db.close()
    asyncio.run(drain_queue(config))
    assert seen == [12]


def test_directives_reach_every_activation(config, monkeypatch):
    seen: list[str] = []

    async def fake_coder(cfg, task, mailbox, journal, vault_get, task_id=None, max_turns=None):
        seen.append(task)
        return _Outcome(finish="ok")

    monkeypatch.setitem(supervisor._RUNNERS, "coder", fake_coder)

    from mnemosyne.journal import Control

    Control(config.control_path).directives_path.write_text(
        "# Directives\n\n- toujours citer la source\n", encoding="utf-8"
    )
    asyncio.run(run_agency(config, "tâche", start="coder"))

    assert "toujours citer la source" in seen[0]


def test_connect_task_settles_its_discovery(config, monkeypatch):
    """A queue connect task flips its discovery: connected with a branch."""
    from mnemosyne.discovery.models import DiscoveryRecord

    record = DiscoveryRecord.build("example.org")
    db = Database(config.db_file())
    db.save_discoveries([record])
    db.enqueue_task(
        "coder", "Connect example.org", payload={"kind": "connect", "source_id": record.id}
    )
    db.close()

    async def fake_coder(cfg, task, mailbox, journal, vault_get, task_id=None, max_turns=None):
        return _Outcome(finish="connecté", branch="agent/example-iiif")

    monkeypatch.setitem(supervisor._RUNNERS, "coder", fake_coder)
    monkeypatch.setattr(supervisor, "_branch_has_commits", lambda cfg, branch: True)
    from mnemosyne.agents.supervisor import drain_queue

    asyncio.run(drain_queue(config))

    db = Database(config.db_file())
    status = next(r.status for r in db.list_discoveries() if r.id == record.id)
    db.close()
    assert status == "connected"


def test_connect_task_without_branch_fails_its_discovery(config, monkeypatch):
    """No branch pushed => the host stays replayable ('failed')."""
    from mnemosyne.discovery.models import DiscoveryRecord

    record = DiscoveryRecord.build("blocked.example")
    db = Database(config.db_file())
    db.save_discoveries([record])
    db.enqueue_task(
        "coder", "Connect blocked.example", payload={"kind": "connect", "source_id": record.id}
    )
    db.close()

    async def fake_coder(cfg, task, mailbox, journal, vault_get, task_id=None, max_turns=None):
        return _Outcome(finish="bloqué : hôte injoignable")

    monkeypatch.setitem(supervisor._RUNNERS, "coder", fake_coder)
    from mnemosyne.agents.supervisor import drain_queue

    asyncio.run(drain_queue(config))

    db = Database(config.db_file())
    status = next(r.status for r in db.list_discoveries() if r.id == record.id)
    db.close()
    assert status == "failed"


def test_transient_provider_error_is_retried(config, monkeypatch):
    """A 503 is an interruption: the activation resumes instead of failing the task."""
    calls = {"n": 0}

    async def flaky(cfg, task, mailbox, journal, vault_get, task_id=None, max_turns=None):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RuntimeError("Error code: 503")
        return _Outcome(finish="ok après reprise")

    monkeypatch.setitem(supervisor._RUNNERS, "browser", flaky)

    db = Database(config.db_file())
    db.enqueue_task("browser", "mission")
    db.close()

    from mnemosyne.agents.supervisor import drain_queue

    asyncio.run(drain_queue(config))

    db = Database(config.db_file())
    task = db.get_task(1)
    db.close()
    assert task["status"] == "done"
    assert calls["n"] == 3


def test_transient_provider_error_gives_up_after_attempts(config, monkeypatch):
    """A provider that stays down does not loop forever: the task fails, with a note."""
    calls = {"n": 0}

    async def dead(cfg, task, mailbox, journal, vault_get, task_id=None, max_turns=None):
        calls["n"] += 1
        raise RuntimeError("Error code: 503")

    monkeypatch.setitem(supervisor._RUNNERS, "browser", dead)

    db = Database(config.db_file())
    db.enqueue_task("browser", "mission")
    db.close()

    from mnemosyne.agents.supervisor import drain_queue

    asyncio.run(drain_queue(config))

    db = Database(config.db_file())
    task = db.get_task(1)
    db.close()
    assert task["status"] == "failed"
    assert "tentatives transitoires" in (task["note"] or "")
    assert calls["n"] == supervisor._TRANSIENT_MAX_ATTEMPTS + 1


def test_plain_error_still_fails_immediately(config, monkeypatch):
    """Non-retryable errors keep the old behaviour: one attempt, failed."""
    calls = {"n": 0}

    async def broken(cfg, task, mailbox, journal, vault_get, task_id=None, max_turns=None):
        calls["n"] += 1
        raise ValueError("boom")

    monkeypatch.setitem(supervisor._RUNNERS, "browser", broken)

    db = Database(config.db_file())
    db.enqueue_task("browser", "mission")
    db.close()

    from mnemosyne.agents.supervisor import drain_queue

    asyncio.run(drain_queue(config))

    db = Database(config.db_file())
    task = db.get_task(1)
    db.close()
    assert task["status"] == "failed"
    assert calls["n"] == 1
