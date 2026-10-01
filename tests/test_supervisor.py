import asyncio
from dataclasses import dataclass

import pytest

from mnemosyne.agents import supervisor
from mnemosyne.agents.supervisor import pick_agent, run_agency


def test_pick_agent_routing():
    assert pick_agent("Va sur https://wetransfer.com et envoie la vidéo") == "browser"
    assert pick_agent("ouvre gmail et lis le code") == "browser"
    assert pick_agent("écris le connecteur europeana") == "coder"


@dataclass
class _Outcome:
    finish: str


def test_run_agency_handoff(config, monkeypatch):
    """coder asks the browser agent, which answers; the coder resumes."""
    calls: list[str] = []

    async def fake_coder(cfg, task, mailbox, journal, vault_get):
        calls.append("coder")
        if "browser" not in calls:
            mailbox.post("coder", "browser", "j'ai besoin de la clé api europeana")
        return _Outcome(finish="coder done")

    async def fake_browser(cfg, task, mailbox, journal, vault_get):
        calls.append("browser")
        mailbox.post("browser", "coder", "clé dispo : vault:europeana_api_key")
        return _Outcome(finish="browser done")

    monkeypatch.setitem(supervisor._RUNNERS, "coder", fake_coder)
    monkeypatch.setitem(supervisor._RUNNERS, "browser", fake_browser)

    result = asyncio.run(run_agency(config, "connecte europeana", start="coder", max_handoffs=4))

    assert [t["agent"] for t in result.turns] == ["coder", "browser", "coder"]
    assert result.stop_reason == "no_pending"


def test_run_agency_marks_review_without_finish(config, monkeypatch):
    """An agent that stops without task_done is not reported as done."""

    async def silent(cfg, task, mailbox, journal, vault_get):
        return _Outcome(finish=None)

    monkeypatch.setitem(supervisor._RUNNERS, "coder", silent)

    result = asyncio.run(run_agency(config, "tâche", start="coder"))

    assert [t["agent"] for t in result.turns] == ["coder"]
    from mnemosyne.db import Database

    db = Database(config.db_file())
    messages = db.list_messages()
    db.close()
    assert messages[-1]["status"] == "review"
    assert "task_done" in messages[-1]["note"]


def test_run_agency_reports_failure(config, monkeypatch):
    async def boom(cfg, task, mailbox, journal, vault_get):
        raise RuntimeError("boom")

    monkeypatch.setitem(supervisor._RUNNERS, "coder", boom)

    result = asyncio.run(run_agency(config, "tâche", start="coder"))

    assert result.stop_reason == "failed"
    assert result.turns[0]["error"] == "boom"

    from mnemosyne.db import Database

    db = Database(config.db_file())
    assert db.list_messages()[-1]["status"] == "failed"
    db.close()


@pytest.mark.asyncio
async def test_run_agency_respects_max_handoffs(config, monkeypatch):
    async def loop_agent(cfg, task, mailbox, journal, vault_get):
        mailbox.post("coder", "browser", "again")
        return _Outcome(finish="loop")

    async def browser_agent(cfg, task, mailbox, journal, vault_get):
        mailbox.post("browser", "coder", "again")
        return _Outcome(finish="loop")

    monkeypatch.setitem(supervisor._RUNNERS, "coder", loop_agent)
    monkeypatch.setitem(supervisor._RUNNERS, "browser", browser_agent)

    result = await run_agency(config, "ping-pong", start="coder", max_handoffs=3)
    assert result.stop_reason == "max_handoffs"
    assert len(result.turns) == 3
