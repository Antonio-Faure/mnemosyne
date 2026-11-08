"""Resolver agent tools and result storage (offline)."""

from __future__ import annotations

import asyncio
import json

from stirrup.core.models import EmptyParams

from mnemosyne.agents.mailbox import Mailbox
from mnemosyne.db import Database
from mnemosyne.resolver.agent import RecordResultParams, RequestSourceParams, ResolverToolProvider


def _db(config) -> Database:
    return Database(config.db_file())


def _seed_task(db: Database, config) -> int:
    label = {
        "id": "yt_demo_1",
        "video": {
            "id": "demo",
            "title": "Demo",
            "channel": "History",
            "url": "https://www.youtube.com/watch?v=demo",
        },
        "segment": {"start_s": 1.0, "end_s": 4.0, "text": "In 1914, Belgium was invaded."},
        "gold": {"status": "no_match", "images": []},
    }
    db.upsert_resolver_golden([label])
    task_id = db.enqueue_task(
        "resolver",
        "illustrate the sentence",
        payload={"kind": "resolver", "segment_id": "yt_demo_1", "label": label},
    )
    db.set_task_status(task_id, "running", agent="resolver")
    return task_id


def test_golden_get_and_result_roundtrip(config):
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        assert db.get_resolver_golden("yt_demo_1")["segment"]["text"].startswith("In 1914")
        assert db.get_resolver_golden("missing") is None
        db.record_resolver_result(
            task_id,
            segment_id="yt_demo_1",
            status="ambiguous",
            evidence="candidate looks like 1918",
        )
        result = db.get_resolver_result(task_id)
        assert result["status"] == "ambiguous"
        assert result["segment_id"] == "yt_demo_1"
    finally:
        db.close()


def test_request_source_creates_biagent_task_and_dependency(config):
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        tools = asyncio.run(provider.__aenter__())
        by_name = {tool.name: tool for tool in tools}
        result = asyncio.run(
            by_name["request_source"].executor(
                RequestSourceParams(
                    source_id="kbr_be",
                    source_name="KBR Belgium",
                    reason="1914 Belgium photos",
                    agent="coder",
                    api_url="https://api.kbr.be/",
                )
            )
        )
        assert result.success is True
        biagent = db.next_task(agents=("coder", "browser"))
        assert biagent is not None
        assert biagent["start_agent"] == "coder"
        payload = json.loads(biagent["payload"])
        assert payload["kind"] == "resolver_source"
        assert payload["resolver_task_id"] == task_id
        assert payload["source_id"] == "kbr_be"
        requests = db.resolver_requests(task_id)
        assert len(requests) == 1
        assert requests[0]["biagent_task_id"] == biagent["id"]
        assert db.task_waiting_on_sources(task_id) is True
        wait_msg = asyncio.run(by_name["wait_for_sources"].executor(EmptyParams()))
        assert wait_msg.success is True
        assert "1 source" in wait_msg.content
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_record_result_tool(config):
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        tools = asyncio.run(provider.__aenter__())
        by_name = {tool.name: tool for tool in tools}
        result = asyncio.run(
            by_name["record_result"].executor(
                RecordResultParams(
                    status="no_match",
                    evidence="nothing in the meta API for this claim",
                )
            )
        )
        assert result.success is True
        stored = db.get_resolver_result(task_id)
        assert stored["status"] == "no_match"
        assert stored["segment_id"] == "yt_demo_1"
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_resolver_loop_uses_its_own_runner_and_lease(config, monkeypatch):
    from mnemosyne.agents import supervisor
    from mnemosyne.agents.outcome import AgentOutcome

    ran: list[int] = []

    async def fake_resolver(
        cfg, task, mailbox, journal, vault_get, task_id=None, max_turns=None
    ):
        ran.append(task_id)
        return AgentOutcome(finish="résolu")

    monkeypatch.setitem(supervisor._RUNNERS, "resolver", fake_resolver)

    db = _db(config)
    try:
        task_id = db.enqueue_task("resolver", "illustrate one sentence")
    finally:
        db.close()

    info = asyncio.run(
        supervisor.run_pending_once(
            config, agents=("resolver",), lease="resolver"
        )
    )

    assert info is not None and info["task_id"] == task_id
    assert ran == [task_id]
    db = _db(config)
    try:
        assert db.get_task(task_id)["status"] == "done"
    finally:
        db.close()
