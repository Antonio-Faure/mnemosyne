"""Resolver agent tools and result storage (offline)."""

from __future__ import annotations

import asyncio
import io
import json

import yaml
from PIL import Image
from stirrup.core.models import EmptyParams

from mnemosyne.agents.mailbox import Mailbox
from mnemosyne.db import Database
from mnemosyne.resolver.agent import (
    MAX_CATALOG_SEARCHES,
    CatalogSearchParams,
    CatalogToggleParams,
    ReadTranscriptParams,
    RecordIllustrationParams,
    RecordResultParams,
    RequestSourceParams,
    ResolverToolProvider,
    SearchTranscriptParams,
    VideoContextParams,
    WebResearchParams,
    _parse_bing_rss,
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


def _seed_asset(provider, asset_id: str, image_url: str, thumbnail_url: str = "") -> None:
    provider._catalog_assets[asset_id] = {
        "image_url": image_url,
        "thumbnail_url": thumbnail_url,
        "page_url": f"https://example.org/notice/{asset_id}",
        "source_id": "wikimedia",
    }


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
        db.update_task_payload(
            resolver_id, {"_search_calls": 6, "_source_search_calls": 4}
        )
        source_task_id = db.enqueue_task(
            "browser", "add the missing source", payload={"kind": "resolver_source"}
        )
        db.create_resolver_request(
            resolver_id,
            sentence_id="yt_demo_1",
            source_id="gallica",
            source_name="Gallica (BnF)",
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
        payload = __import__("json").loads(db.get_task(resolver_id)["payload"])
        assert payload["_search_calls"] == 0
        assert payload["_source_search_calls"] == 0
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
        db.upsert_resolver_illustration(
            task_id,
            segment_id="yt_demo_1",
            sentence="In 1914, Belgium was invaded.",
            context="Vidéo de démonstration",
            image_url="https://example.org/chosen.jpg",
            image_context="Troupes belges",
            asset_id="a1",
        )
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


def _png_bytes() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (1, 1), (0, 0, 0)).save(out, format="PNG")
    return out.getvalue()


def _fake_image_check(url: str, **kwargs):
    return {
        "ok": True,
        "image_url": url,
        "final_url": url,
        "content_type": "image/jpeg",
        "image_format": "JPEG",
        "width": 800,
        "height": 600,
        "image_bytes": 50000,
        "hard_failures": [],
        "warnings": [],
        "preview": _png_bytes(),
    }


def test_record_illustration_records_the_exact_image_and_result(config, monkeypatch):
    async def fake(url, **kwargs):
        return _fake_image_check(url)

    monkeypatch.setattr("mnemosyne.resolver.agent.inspect_image", fake)
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        _seed_asset(provider, "asset-photo", "https://example.org/photo.jpg")
        tools = {tool.name: tool for tool in asyncio.run(provider.__aenter__())}
        params = RecordIllustrationParams(
            image_url="https://example.org/photo.jpg#frag",
            sentence="In 1914, Belgium was invaded.",
            context="Vidéo de démonstration",
            image_context="Troupes belges traversant une place",
            status="partial",
            asset_id="asset-photo",
            page_url="https://example.org/notice",
            source_id="wikimedia",
            evidence="Domaine public, 1914",
        )
        result = asyncio.run(tools["record_illustration"].executor(params))
        assert result.success is True
        assert isinstance(result.content, list) and len(result.content) == 2
        stored = db.get_resolver_illustration_for_task(task_id)
        assert stored["image_url"] == "https://example.org/photo.jpg"
        assert stored["sentence"] == params.sentence
        assert stored["image_context"] == params.image_context
        assert stored["quality"] == []
        assert db.get_resolver_result(task_id)["status"] == "partial"
        assert db.get_resolver_result(task_id)["asset_id"] == "asset-photo"
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_record_illustration_refuses_a_reused_image(config, monkeypatch):
    async def fake(url, **kwargs):
        return _fake_image_check(url)

    monkeypatch.setattr("mnemosyne.resolver.agent.inspect_image", fake)
    db = _db(config)
    try:
        first = _seed_task(db, config)
        second = db.enqueue_task(
            "resolver",
            "another sentence",
            payload={"kind": "resolver", "segment_id": "yt_demo_1"},
        )
        db.set_task_status(second, "running", agent="resolver")
        for task_id, asset in ((first, "asset-a"), (second, "asset-b")):
            provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
            _seed_asset(provider, asset, "https://example.org/same.jpg")
            tools = {tool.name: tool for tool in asyncio.run(provider.__aenter__())}
            params = RecordIllustrationParams(
                image_url="https://example.org/same.jpg",
                sentence=f"sentence {task_id}",
                context="contexte",
                image_context="même image",
                asset_id=asset,
            )
            result = asyncio.run(tools["record_illustration"].executor(params))
            if task_id == first:
                assert result.success is True
            else:
                assert result.success is False
                assert "déjà utilisée" in result.content
            asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_record_result_match_requires_an_illustration(config):
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        tools = {tool.name: tool for tool in asyncio.run(provider.__aenter__())}
        result = asyncio.run(
            tools["record_result"].executor(
                RecordResultParams(status="match", asset_id="a1", evidence="ok")
            )
        )
        assert result.success is False
        assert "record_illustration" in result.content
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_record_illustration_refusal_carries_the_reason(config, monkeypatch):
    async def fake(url, **kwargs):
        return {
            "ok": False,
            "image_url": url,
            "final_url": url,
            "content_type": "text/html",
            "image_format": None,
            "width": None,
            "height": None,
            "image_bytes": 60,
            "hard_failures": ["le lien ne renvoie pas une image"],
            "warnings": [],
            "preview": None,
        }

    monkeypatch.setattr("mnemosyne.resolver.agent.inspect_image", fake)
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        _seed_asset(provider, "asset-page", "https://example.org/notice")
        tools = {tool.name: tool for tool in asyncio.run(provider.__aenter__())}
        result = asyncio.run(
            tools["record_illustration"].executor(
                RecordIllustrationParams(
                    image_url="https://example.org/notice",
                    sentence="In 1914, Belgium was invaded.",
                    context="contexte",
                    image_context="une page",
                    asset_id="asset-page",
                )
            )
        )
        assert result.success is False
        assert "ne renvoie pas une image" in result.content
        assert db.get_resolver_illustration_for_task(task_id) is None
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_no_match_clears_a_provisional_illustration(config, monkeypatch):
    async def fake(url, **kwargs):
        return _fake_image_check(url)

    monkeypatch.setattr("mnemosyne.resolver.agent.inspect_image", fake)
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        _seed_asset(provider, "asset-photo", "https://example.org/photo.jpg")
        tools = {tool.name: tool for tool in asyncio.run(provider.__aenter__())}
        recorded = asyncio.run(
            tools["record_illustration"].executor(
                RecordIllustrationParams(
                    image_url="https://example.org/photo.jpg",
                    sentence="In 1914, Belgium was invaded.",
                    context="contexte",
                    image_context="troupes",
                    asset_id="asset-photo",
                )
            )
        )
        assert recorded.success is True
        assert db.get_resolver_illustration_for_task(task_id) is not None
        result = asyncio.run(
            tools["record_result"].executor(
                RecordResultParams(status="no_match", evidence="finalement non")
            )
        )
        assert result.success is True
        assert db.get_resolver_illustration_for_task(task_id) is None
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_pending_operator_question_writes_nothing(config):
    """A validation guard is not an image: it must leave the database untouched."""
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        db.create_ask(
            "pending-1",
            task_id,
            "resolver",
            "Valide ?",
            [{"label": "Oui"}, {"label": "Non"}],
        )
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        _seed_asset(provider, "asset-photo", "https://example.org/photo.jpg")
        tools = {tool.name: tool for tool in asyncio.run(provider.__aenter__())}
        result = asyncio.run(
            tools["record_illustration"].executor(
                RecordIllustrationParams(
                    image_url="https://example.org/photo.jpg",
                    sentence="In 1914, Belgium was invaded.",
                    context="contexte",
                    image_context="troupes",
                    asset_id="asset-photo",
                )
            )
        )
        assert result.success is False
        assert "en attente" in result.content
        assert db.get_resolver_illustration_for_task(task_id) is None
        assert db.get_resolver_result(task_id) is None
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def _write_source(sources_dir, source_id: str, *, enabled: bool, notes: str) -> None:
    (sources_dir / f"{source_id}.yaml").write_text(
        yaml.safe_dump(
            {
                "id": source_id,
                "name": source_id.title(),
                "protocol": "rest",
                "base_url": f"https://{source_id}.example.invalid/api",
                "auth": "none",
                "enabled": enabled,
                "notes": notes,
                "seeds": ["test seed"],
            }
        ),
        encoding="utf-8",
    )


def test_catalog_toggle_flips_the_session_perimeter(config, sources_dir):
    _write_source(
        sources_dir,
        "local",
        enabled=False,
        notes="Fonds local désactivé pour raison de licence.",
    )
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        tools = {tool.name: tool for tool in asyncio.run(provider.__aenter__())}

        inventory = asyncio.run(tools["catalog_inventory"].executor(EmptyParams()))
        assert inventory.success is True
        assert "global=activée" in inventory.content
        assert "global=désactivée" in inventory.content
        assert "recherche=oui" in inventory.content
        assert "contexte: Bibliothèque nationale de France" in inventory.content
        assert "contexte: Fonds local désactivé" in inventory.content

        blocked = asyncio.run(
            tools["catalog_toggle"].executor(CatalogToggleParams(source_ids=["local"]))
        )
        assert blocked.success is False
        assert "désactivée globalement" in blocked.content

        off = asyncio.run(
            tools["catalog_toggle"].executor(CatalogToggleParams(source_ids=["gallica"]))
        )
        assert off.success is True
        assert "désactivée(s) : gallica" in off.content
        assert "0/1" in off.content

        empty = asyncio.run(
            tools["catalog_search"].executor(CatalogSearchParams(query="1900"))
        )
        assert empty.success is False
        assert "périmètre de recherche vide" in empty.content

        on = asyncio.run(
            tools["catalog_toggle"].executor(CatalogToggleParams(source_ids=["gallica"]))
        )
        assert on.success is True
        assert "activée(s) : gallica" in on.content
        assert "1/1" in on.content

        listed = asyncio.run(tools["catalog_inventory"].executor(EmptyParams()))
        assert "recherche=oui" in listed.content
    finally:
        db.close()


def test_catalog_toggle_flips_several_sources_and_search_uses_the_perimeter(
    config, sources_dir, monkeypatch
):
    _write_source(sources_dir, "other", enabled=True, notes="Autre fonds.")
    seen: list[list[str] | None] = []

    async def fake_search(self, query, source_ids=None, limit=20):
        seen.append(source_ids)
        return []

    monkeypatch.setattr("mnemosyne.resolver.agent.Engine.search", fake_search)
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        tools = {tool.name: tool for tool in asyncio.run(provider.__aenter__())}

        both_off = asyncio.run(
            tools["catalog_toggle"].executor(
                CatalogToggleParams(source_ids=["gallica", "other"])
            )
        )
        assert both_off.success is True
        assert "désactivée(s) : gallica, other" in both_off.content
        assert "0/2" in both_off.content

        asyncio.run(tools["catalog_search"].executor(CatalogSearchParams(query="1900")))
        assert seen == []  # the empty perimeter never reaches the engine

        asyncio.run(
            tools["catalog_toggle"].executor(CatalogToggleParams(source_ids=["gallica"]))
        )
        asyncio.run(tools["catalog_search"].executor(CatalogSearchParams(query="1900")))
        assert seen[-1] == ["gallica"]

        both_on = asyncio.run(
            tools["catalog_toggle"].executor(
                CatalogToggleParams(source_ids=["gallica", "other"])
            )
        )
        assert "activée(s) : other" in both_on.content
        assert "désactivée(s) : gallica" in both_on.content
        assert "1/2" in both_on.content
    finally:
        db.close()


def test_catalog_search_has_no_source_switch():
    assert "source_ids" not in CatalogSearchParams.model_fields
    assert "source_ids" in CatalogToggleParams.model_fields


def test_catalog_search_budget_stops_the_loop(config, monkeypatch):
    calls: list[str] = []

    async def fake_search(self, query, source_ids=None, limit=20):
        calls.append(query)
        return []

    monkeypatch.setattr("mnemosyne.resolver.agent.Engine.search", fake_search)
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        tools = {tool.name: tool for tool in asyncio.run(provider.__aenter__())}

        for number in range(1, MAX_CATALOG_SEARCHES + 1):
            result = asyncio.run(
                tools["catalog_search"].executor(
                    CatalogSearchParams(query=f"query {number}")
                )
            )
            assert result.success is True
            assert f"recherche {number}/{MAX_CATALOG_SEARCHES}" in result.content

        blocked = asyncio.run(
            tools["catalog_search"].executor(CatalogSearchParams(query="one too many"))
        )
        assert blocked.success is False
        assert "budget" in blocked.content
        assert len(calls) == MAX_CATALOG_SEARCHES
    finally:
        db.close()


def test_bing_rss_parser_returns_results():
    xml = """<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0"><channel>
      <item>
        <title>Archive Citroën 1901</title>
        <link>https://example.org/archive</link>
        <description>Photographies de l'atelier et des engrenages.</description>
      </item>
      <item>
        <title>Musée des Arts et Métiers</title>
        <link>https://example.org/musee</link>
        <description>Collections industrielles.</description>
      </item>
    </channel></rss>
    """
    rows = _parse_bing_rss(xml, limit=1)
    assert len(rows) == 1
    assert rows[0]["url"] == "https://example.org/archive"
    assert "engrenages" in rows[0]["snippet"]


def test_bing_rss_parser_rejects_garbage():
    assert _parse_bing_rss("<html>not rss</html>") == []
    assert _parse_bing_rss("<rss><channel></channel></rss>") == []


def test_record_illustration_refuses_an_image_not_seen_in_catalog(config):
    """A web result is not image provenance: the asset must come from catalog_search."""
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        tools = {tool.name: tool for tool in asyncio.run(provider.__aenter__())}
        result = asyncio.run(
            tools["record_illustration"].executor(
                RecordIllustrationParams(
                    image_url="https://example.org/web-image.jpg",
                    sentence="In 1914, Belgium was invaded.",
                    context="contexte",
                    image_context="image trouvée sur le web",
                    asset_id="asset-from-source-search",
                )
            )
        )
        assert result.success is False
        assert "provenance manquante" in result.content
        assert "source_search" in result.content
        assert db.get_resolver_illustration_for_task(task_id) is None
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_transient_image_failure_is_not_cached(config, monkeypatch):
    """A 403 must stay retryable: the second call must not reuse the cached failure."""
    calls = {"n": 0}

    async def fake(url, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"ok": False, "hard_failures": ["HTTP 403"], "warnings": []}
        return _fake_image_check(url)

    monkeypatch.setattr("mnemosyne.resolver.agent.inspect_image", fake)
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        _seed_asset(provider, "asset-photo", "https://example.org/photo.jpg")
        tools = {tool.name: tool for tool in asyncio.run(provider.__aenter__())}
        params = RecordIllustrationParams(
            image_url="https://example.org/photo.jpg",
            sentence="In 1914, Belgium was invaded.",
            context="contexte",
            image_context="troupes",
            asset_id="asset-photo",
        )
        first = asyncio.run(tools["record_illustration"].executor(params))
        assert first.success is False
        assert "403" in first.content
        second = asyncio.run(tools["record_illustration"].executor(params))
        assert second.success is True
        assert calls["n"] == 2
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_record_illustration_falls_back_to_the_official_thumbnail(config, monkeypatch):
    async def fake(url, **kwargs):
        if "native" in url:
            return {"ok": False, "hard_failures": ["HTTP 403"], "warnings": []}
        return _fake_image_check(url)

    monkeypatch.setattr("mnemosyne.resolver.agent.inspect_image", fake)
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        _seed_asset(
            provider,
            "asset-photo",
            "https://example.org/native.jpg",
            "https://example.org/thumb.jpg",
        )
        tools = {tool.name: tool for tool in asyncio.run(provider.__aenter__())}
        result = asyncio.run(
            tools["record_illustration"].executor(
                RecordIllustrationParams(
                    image_url="https://example.org/native.jpg",
                    thumbnail_url="https://example.org/thumb.jpg",
                    sentence="In 1914, Belgium was invaded.",
                    context="contexte",
                    image_context="troupes",
                    asset_id="asset-photo",
                )
            )
        )
        assert result.success is True
        stored = db.get_resolver_illustration_for_task(task_id)
        assert stored["image_url"] == "https://example.org/thumb.jpg"
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_search_budget_survives_a_new_activation(config, monkeypatch):
    async def fake_search(self, query, source_ids=None, limit=20):
        return []

    monkeypatch.setattr("mnemosyne.resolver.agent.Engine.search", fake_search)
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        first = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        tools = {tool.name: tool for tool in asyncio.run(first.__aenter__())}
        for number in range(2):
            result = asyncio.run(
                tools["catalog_search"].executor(
                    CatalogSearchParams(query=f"query {number}")
                )
            )
            assert result.success is True

        second = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        tools = {tool.name: tool for tool in asyncio.run(second.__aenter__())}
        assert second._search_calls == 2
        for number in range(4):
            result = asyncio.run(
                tools["catalog_search"].executor(
                    CatalogSearchParams(query=f"next {number}")
                )
            )
            assert result.success is True
        blocked = asyncio.run(
            tools["catalog_search"].executor(CatalogSearchParams(query="one too many"))
        )
        assert blocked.success is False
        assert "budget" in blocked.content
        assert second._search_calls == MAX_CATALOG_SEARCHES
    finally:
        db.close()


def test_catalog_assets_survive_a_new_activation(config):
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        first = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        first._catalog_assets["asset-from-first-activation"] = {
            "image_url": "https://example.org/first.jpg",
            "thumbnail_url": "",
            "page_url": "https://example.org/notice/first",
            "source_id": "wikimedia",
        }
        first._save_progress()

        second = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        assert "asset-from-first-activation" in second._catalog_assets
    finally:
        db.close()


def test_finished_source_task_without_a_catalog_source_is_failed(config, monkeypatch):
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
            source_id="not_in_catalog",
            source_name="Missing source",
            agent_task_id=source_task_id,
        )
    finally:
        db.close()

    asyncio.run(
        supervisor.run_pending_once(config, agents=("browser",), lease="agency")
    )

    db = _db(config)
    try:
        request = db.resolver_requests(resolver_id)[0]
        assert request["status"] == "failed"
        assert "absente du catalogue" in (request["note"] or "")
    finally:
        db.close()


def test_request_source_refuses_a_bypass_specialisation(config):
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        tools = {tool.name: tool for tool in asyncio.run(provider.__aenter__())}
        result = asyncio.run(
            tools["request_source"].executor(
                RequestSourceParams(
                    source_id="gallica_browser",
                    source_name="Gallica via navigateur",
                    reason="contournement du 403 Cloudflare",
                    api_url="https://example.invalid/iiif",
                    specialisation=True,
                )
            )
        )
        assert result.success is False
        assert "identifiant de source refusé" in result.content
        second = asyncio.run(
            tools["request_source"].executor(
                RequestSourceParams(
                    source_id="gallica_photos_bypass",
                    source_name="Gallica photos",
                    reason="contournement du 403 Cloudflare",
                    api_url="https://example.invalid/iiif",
                    specialisation=True,
                )
            )
        )
        assert second.success is False
        assert "spécialisation refusée" in second.content
        assert db.resolver_requests(task_id) == []
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_record_illustration_refuses_an_image_from_another_asset(config, monkeypatch):
    async def fake(url, **kwargs):
        return _fake_image_check(url)

    monkeypatch.setattr("mnemosyne.resolver.agent.inspect_image", fake)
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        _seed_asset(provider, "asset-a", "https://example.org/a.jpg")
        _seed_asset(provider, "asset-b", "https://example.org/b.jpg")
        tools = {tool.name: tool for tool in asyncio.run(provider.__aenter__())}
        result = asyncio.run(
            tools["record_illustration"].executor(
                RecordIllustrationParams(
                    image_url="https://example.org/b.jpg",
                    sentence="In 1914, Belgium was invaded.",
                    context="contexte",
                    image_context="mauvais asset",
                    asset_id="asset-a",
                )
            )
        )
        assert result.success is False
        assert "ne correspond pas à l'asset" in result.content
        assert db.get_resolver_illustration_for_task(task_id) is None
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_record_result_refuses_a_different_asset(config, monkeypatch):
    async def fake(url, **kwargs):
        return _fake_image_check(url)

    monkeypatch.setattr("mnemosyne.resolver.agent.inspect_image", fake)
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        _seed_asset(provider, "asset-a", "https://example.org/a.jpg")
        tools = {tool.name: tool for tool in asyncio.run(provider.__aenter__())}
        recorded = asyncio.run(
            tools["record_illustration"].executor(
                RecordIllustrationParams(
                    image_url="https://example.org/a.jpg",
                    sentence="In 1914, Belgium was invaded.",
                    context="contexte",
                    image_context="bon asset",
                    asset_id="asset-a",
                )
            )
        )
        assert recorded.success is True
        bad = asyncio.run(
            tools["record_result"].executor(
                RecordResultParams(status="match", asset_id="asset-b", evidence="faux")
            )
        )
        assert bad.success is False
        assert "asset_id incohérent" in bad.content
        good = asyncio.run(
            tools["record_result"].executor(
                RecordResultParams(status="match", asset_id="asset-a", evidence="ok")
            )
        )
        assert good.success is True
        assert db.get_resolver_result(task_id)["asset_id"] == "asset-a"
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_no_match_writes_no_asset_id(config, monkeypatch):
    async def fake(url, **kwargs):
        return _fake_image_check(url)

    monkeypatch.setattr("mnemosyne.resolver.agent.inspect_image", fake)
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        _seed_asset(provider, "asset-a", "https://example.org/a.jpg")
        tools = {tool.name: tool for tool in asyncio.run(provider.__aenter__())}
        asyncio.run(
            tools["record_illustration"].executor(
                RecordIllustrationParams(
                    image_url="https://example.org/a.jpg",
                    sentence="In 1914, Belgium was invaded.",
                    context="contexte",
                    image_context="provisoire",
                    asset_id="asset-a",
                )
            )
        )
        result = asyncio.run(
            tools["record_result"].executor(
                RecordResultParams(status="no_match", asset_id="bogus", evidence="non")
            )
        )
        assert result.success is True
        stored = db.get_resolver_result(task_id)
        assert stored["status"] == "no_match"
        assert stored["asset_id"] is None
        assert db.get_resolver_illustration_for_task(task_id) is None
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_specialisation_is_not_blocked_by_the_similar_name_check(config):
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        tools = {tool.name: tool for tool in asyncio.run(provider.__aenter__())}
        result = asyncio.run(
            tools["request_source"].executor(
                RequestSourceParams(
                    source_id="gallica_photos_v3",
                    source_name="Gallica (BnF)",
                    reason="photographies seulement, le connecteur général renvoie des livres",
                    api_url="https://example.invalid/iiif",
                    specialisation=True,
                )
            )
        )
        assert result.success is True
        assert len(db.resolver_requests(task_id)) == 1
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()


def test_web_research_is_context_only_and_budgeted(config, monkeypatch):
    async def fake_bing(query, limit=6):
        return [
            {
                "title": "Contexte industriel",
                "url": "https://example.org/contexte",
                "snippet": "Les usines de guerre en 1916.",
            }
        ]

    async def fake_page(url, max_chars=1200):
        return "Texte de contexte sur les munitionnettes."

    monkeypatch.setattr("mnemosyne.resolver.agent._bing_search", fake_bing)
    monkeypatch.setattr("mnemosyne.resolver.agent._fetch_page_text", fake_page)
    db = _db(config)
    try:
        task_id = _seed_task(db, config)
        provider = ResolverToolProvider(config, Mailbox(db), task_id=task_id)
        tools = {tool.name: tool for tool in asyncio.run(provider.__aenter__())}
        for number in range(4):
            result = asyncio.run(
                tools["web_research"].executor(
                    WebResearchParams(query=f"contexte {number}")
                )
            )
            assert result.success is True
            assert "contexte externe" in result.content
            assert "Texte seulement" in result.content
        blocked = asyncio.run(
            tools["web_research"].executor(WebResearchParams(query="trop"))
        )
        assert blocked.success is False
        assert "budget" in blocked.content
        assert provider._catalog_assets == {}
        asyncio.run(provider.__aexit__(None, None, None))
    finally:
        db.close()
