"""Resolver agent tools and result storage (offline)."""

from __future__ import annotations

import asyncio
import json

from stirrup.core.models import EmptyParams

from mnemosyne.agents.mailbox import Mailbox
from mnemosyne.db import Database
from mnemosyne.resolver.agent import (
    ReadTranscriptParams,
    RecordResultParams,
    RequestSourceParams,
    ResolverToolProvider,
    SearchTranscriptParams,
    VideoContextParams,
)


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


def test_request_source_creates_agent_task_and_dependency(config):
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
        agent_task = db.next_task(agents=("coder", "browser"))
        assert agent_task is not None
        assert agent_task["start_agent"] == "coder"
        payload = json.loads(agent_task["payload"])
        assert payload["kind"] == "resolver_source"
        assert payload["resolver_task_id"] == task_id
        assert payload["source_id"] == "kbr_be"
        requests = db.resolver_requests(task_id)
        assert len(requests) == 1
        assert requests[0]["agent_task_id"] == agent_task["id"]
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


def test_request_source_refuses_a_source_already_in_the_catalog(config):
    """Wikimedia is already onboarded: asking for it again must fail loudly."""
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        tools = asyncio.run(provider.__aenter__())
        by_name = {tool.name: tool for tool in tools}
        result = asyncio.run(
            by_name["request_source"].executor(
                RequestSourceParams(
                    source_id="gallica",
                    source_name="Gallica again",
                    reason="1914 photos",
                    api_url="https://example.invalid/SRU",
                )
            )
        )
        assert result.success is False
        assert "déjà au catalogue" in result.content
        assert db.resolver_requests(task_id) == []
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_request_source_allows_a_same_host_specialisation(config):
    """A photo-only sibling of a text connector is legitimate (PR #74)."""
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        tools = asyncio.run(provider.__aenter__())
        by_name = {tool.name: tool for tool in tools}
        result = asyncio.run(
            by_name["request_source"].executor(
                RequestSourceParams(
                    source_id="gallica_photos_v2",
                    source_name="Gallica again",
                    reason="photos only, the sibling returns books",
                    api_url="https://example.invalid/iiif/search",
                    specialisation=True,
                )
            )
        )
        assert result.success is True
        assert "déjà couvert" in result.content
        assert "profil de recherche" in result.content
        assert len(db.resolver_requests(task_id)) == 1
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_closing_an_agent_task_wakes_the_parked_resolver(config, monkeypatch):
    """The half that was missing: a finished source task must free the resolver."""
    from mnemosyne.agents import supervisor
    from mnemosyne.agents.outcome import AgentOutcome

    async def fake_browser(cfg, task, mailbox, journal, vault_get, task_id=None, max_turns=None):
        return AgentOutcome(finish="source added")

    monkeypatch.setitem(supervisor._RUNNERS, "browser", fake_browser)

    db = _db(config)
    try:
        resolver_id = db.enqueue_task("resolver", "illustrate a sentence")
        db.set_task_status(resolver_id, "running", agent="resolver")
        source_task_id = db.enqueue_task(
            "browser", "add the missing source", payload={"kind": "resolver_source"}
        )
        db.create_resolver_request(
            resolver_id,
            sentence_id="yt_demo_1",
            source_id="loc_wwi_photos",
            source_name="Library of Congress photos",
            agent_task_id=source_task_id,
        )
        assert db.task_waiting_on_sources(resolver_id) is True
    finally:
        db.close()

    info = asyncio.run(
        supervisor.run_pending_once(config, agents=("browser",), lease="agency")
    )
    assert info is not None and info["task_id"] == source_task_id

    db = _db(config)
    try:
        request = db.resolver_requests(resolver_id)[0]
        assert request["status"] == "done"
        assert db.task_waiting_on_sources(resolver_id) is False
        wake = [
            message
            for message in db.list_messages()
            if message["task_id"] == resolver_id and "[SOURCES READY]" in message["body"]
        ]
        assert wake, "the resolver must receive a [SOURCES READY] message"
        assert wake[0]["sender"] == "system"
    finally:
        db.close()


def test_record_result_cannot_self_validate_while_a_question_is_open(config):
    """match/partial need the answer: never record the verdict you asked about."""
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        db.create_ask(
            "ask-1",
            task_id,
            "resolver",
            "Valide ce candidat ?",
            [{"label": "Valide"}, {"label": "Refuse"}],
        )
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        tools = asyncio.run(provider.__aenter__())
        by_name = {tool.name: tool for tool in tools}
        blocked = asyncio.run(
            by_name["record_result"].executor(
                RecordResultParams(status="match", asset_id="a1", evidence="looks right")
            )
        )
        assert blocked.success is False
        assert "en attente" in blocked.content
        assert db.get_resolver_result(task_id) is None

        db.answer_ask("ask-1", "Valide")
        allowed = asyncio.run(
            by_name["record_result"].executor(
                RecordResultParams(status="match", asset_id="a1", evidence="validé")
            )
        )
        assert allowed.success is True
        assert db.get_resolver_result(task_id)["status"] == "match"
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_request_source_refuses_a_similar_name(config):
    """`gallica_bnf` / `wellcome_collection`: same source under a new id."""
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        tools = asyncio.run(provider.__aenter__())
        by_name = {tool.name: tool for tool in tools}
        result = asyncio.run(
            by_name["request_source"].executor(
                RequestSourceParams(
                    source_id="gallica_bnf",
                    source_name="Gallica (BnF) — presse & photographie",
                    reason="press photos",
                    api_url="https://api.bnf.fr/",
                )
            )
        )
        assert result.success is False
        assert "déjà couverte" in result.content
        assert db.resolver_requests(task_id) == []
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_request_source_refuses_a_source_already_requested(config):
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        tools = asyncio.run(provider.__aenter__())
        by_name = {tool.name: tool for tool in tools}
        params = RequestSourceParams(
            source_id="kbr_be",
            source_name="KBR Belgium",
            reason="1914 Belgium photos",
            api_url="https://api.kbr.be/",
        )
        first = asyncio.run(by_name["request_source"].executor(params))
        assert first.success is True
        second = asyncio.run(by_name["request_source"].executor(params))
        assert second.success is False
        assert "déjà demandée" in second.content
        assert len(db.resolver_requests(task_id)) == 1
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_request_source_is_refused_while_onboarding_is_frozen(config):
    """Quota freeze: the resolver abstains instead of queueing a new source."""
    config.dev.sources_freeze = True
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
                    api_url="https://api.kbr.be/",
                )
            )
        )
        assert result.success is False
        assert "gelé" in result.content
        assert db.resolver_requests(task_id) == []
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_context_and_transcript_tools(config):
    """The resolver can widen the context and search the full transcript."""
    db = _db(config)
    try:
        entries = [
            {
                "id": f"yt_ctx_{i}",
                "text": "Le pétrole de Pechelbronn." if i == 2 else f"Phrase {i}.",
                "start_s": float(i * 10),
                "end_s": float(i * 10 + 8),
                "video": {"id": "ctx", "title": "La France et le pétrole"},
                "claim": {},
            }
            for i in range(6)
        ]
        db.upsert_resolver_corpus(entries)
        db.upsert_video_context(
            "ctx",
            title="La France et le pétrole",
            duration_s=60,
            summary="Le pétrole français oublié.",
            outline=[{"start_s": 0, "end_s": 60, "title": "Le gisement", "summary": ""}],
            meta={"period": "1920", "places": ["Alsace"], "entities": ["Pechelbronn"]},
            model="fake",
        )
        task_id = db.enqueue_task(
            "resolver",
            "illustrate the sentence",
            payload={
                "kind": "resolver",
                "segment_id": "yt_ctx_2",
                "corpus": entries[2],
            },
        )
        db.set_task_status(task_id, "running", agent="resolver")

        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        tools = asyncio.run(provider.__aenter__())
        by_name = {tool.name: tool for tool in tools}

        context = asyncio.run(
            by_name["video_context"].executor(VideoContextParams(before=1, after=1))
        )
        assert context.success is True
        assert "Résumé : Le pétrole français oublié." in context.content
        assert "← phrase" in context.content

        found = asyncio.run(
            by_name["search_transcript"].executor(
                SearchTranscriptParams(query="Pechelbronn")
            )
        )
        assert found.success is True
        assert "yt_ctx_2" not in found.content  # compact display, not the raw id
        assert "Pechelbronn" in found.content

        window = asyncio.run(
            by_name["read_transcript"].executor(
                ReadTranscriptParams(start_s=10, end_s=20)
            )
        )
        assert window.success is True
        assert "Phrase 1." in window.content
        assert "Pechelbronn" in window.content

        catalog = asyncio.run(by_name["catalog_inventory"].executor(EmptyParams()))
        assert catalog.success is True
        assert "gallica" in catalog.content
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()
