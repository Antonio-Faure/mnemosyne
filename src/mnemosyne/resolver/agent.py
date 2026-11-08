"""Resolver agent (Stirrup): one session per historical sentence.

It reads the biagent meta API (catalog search), asks the operator to validate
candidates, and requests missing sources as ordinary biagent tasks. It is
activated by its own permanent heartbeat job, in parallel with the agency.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field
from stirrup import Agent
from stirrup.core.models import (
    EmptyParams,
    Tool,
    ToolProvider,
    ToolResult,
    ToolUseCountMetadata,
)

from mnemosyne.agents.mailbox import Mailbox
from mnemosyne.agents.outcome import AgentOutcome
from mnemosyne.agents.progress import ProgressWatch, watch_provider
from mnemosyne.agents.session_cache import cache_base_dir, persist_session
from mnemosyne.browser.stirrup_client import build_agent_client
from mnemosyne.config import Config
from mnemosyne.db import Database
from mnemosyne.engine import Engine
from mnemosyne.http import domain_of
from mnemosyne.journal import Journal
from mnemosyne.logger import get_logger
from mnemosyne.operator.models import AskOperatorParams
from mnemosyne.operator.telegram import ask_operator
from mnemosyne.resolver.ranking import rank as rank_assets
from mnemosyne.util import ensure_dir, finish_text, load_prompt

log = get_logger("resolver.agent")

#: Context budget for one search answer. A 52-source query returns hundreds of
#: rows: the tool ranks them, keeps the best and *never* cuts JSON mid-record
#: (the model used to receive a truncated, unparsable blob).
_RESULT_BUDGET = 12000
_MAX_ROWS = 40

_FALLBACK = (
    "You are {name}, the adversarial resolver. MISSION: {task}. "
    "Use catalog_search, ask the operator, request sources, then wait_for_sources."
)


def _ok(content: str) -> ToolResult[ToolUseCountMetadata]:
    return ToolResult(content=content, metadata=ToolUseCountMetadata())


def _fail(content: str) -> ToolResult[ToolUseCountMetadata]:
    return ToolResult(content=content, success=False, metadata=ToolUseCountMetadata())


#: Connector words only: "Library of Congress" and "Library of Congress — Prints"
#: stay different sources, while "Gallica (BnF)" and "gallica_bnf" are the same.
_GLUE = frozenset(
    {
        "the", "of", "de", "la", "le", "les", "des", "du", "and", "et", "a", "à",
        "en", "for", "pour", "sur", "collections", "collection", "fonds",
    }
)


def _name_tokens(*values: str | None) -> set[str]:
    words: set[str] = set()
    for value in values:
        for raw in str(value or "").replace("_", " ").replace("-", " ").split():
            word = raw.strip("()[].,;:!?/\\'\"").lower()
            if len(word) >= 3 and word not in _GLUE:
                words.add(word)
    return words


def _same_source(a: set[str], b: set[str], threshold: float = 0.6) -> bool:
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= threshold


class CatalogSearchParams(BaseModel):
    query: str = Field(description="Historical search query (entities, place, period, synonyms)")
    limit: int = Field(default=10, ge=1, le=30)
    source_ids: list[str] | None = Field(
        default=None, description="Optional source ids to restrict the search"
    )


class RequestSourceParams(BaseModel):
    source_id: str = Field(description="Stable proposed source id, e.g. 'kbr_be'")
    source_name: str = Field(description="Human-readable source name")
    reason: str = Field(description="Why this source is needed for the sentence")
    agent: Literal["coder", "browser"] = Field(
        default="coder", description="Biagent to use (browser if auth/API research is needed)"
    )
    api_url: str = Field(default="", description="Optional API/docs URL to attach to the task")
    specialisation: bool = Field(
        default=False,
        description=(
            "true only for a deliberate sibling of an existing source (e.g. a "
            "photo-only connector when the existing one returns books). Explain "
            "the different scope in `reason`."
        ),
    )


class RecordResultParams(BaseModel):
    status: Literal["match", "partial", "no_match", "ambiguous"]
    asset_id: str | None = Field(default=None, description="Chosen asset id, if any")
    evidence: str = Field(
        default="", description="Evidence, source links, why this match is defendable"
    )


def _compact_row(asset) -> dict[str, Any]:
    row = {
        "asset_id": asset.id,
        "source_id": asset.source_id,
        "title": (asset.title or "")[:200],
        "creator": asset.creator,
        "year": asset.year,
        "date_text": asset.date_text,
        "license": asset.license,
        "page_url": asset.page_url,
        "image_url": asset.image_url,
    }
    if asset.description:
        row["description"] = asset.description[:240]
    return {key: value for key, value in row.items() if value not in (None, "")}


def _fit_rows(rows: list[dict[str, Any]], budget: int = _RESULT_BUDGET) -> list[dict[str, Any]]:
    """Longest prefix that still serialises inside `budget` (never mid-JSON)."""
    shown = rows
    while len(shown) > 1 and len(json.dumps(shown, ensure_ascii=False)) > budget:
        shown = shown[: max(1, len(shown) * 2 // 3)]
    return shown


class ResolverToolProvider(ToolProvider):
    def __init__(
        self,
        config: Config,
        mailbox: Mailbox,
        *,
        task_id: int | None = None,
        journal: Journal | None = None,
        vault_get=None,
    ):
        self.config = config
        self.mailbox = mailbox
        self.db = mailbox.db
        self.task_id = task_id
        self.journal = journal
        self.vault_get = vault_get

    async def __aenter__(self):
        return self._tools()

    async def __aexit__(self, *exc):
        return None

    def _payload(self) -> dict[str, Any]:
        if self.task_id is None:
            return {}
        task = self.db.get_task(self.task_id)
        if task is None:
            return {}
        try:
            return json.loads(task.get("payload") or "{}")
        except (TypeError, ValueError):
            return {}

    def _segment_id(self) -> str | None:
        payload = self._payload()
        return payload.get("segment_id") or payload.get("id")

    def _known_sources(self) -> dict[str, object]:
        """The catalogue as the resolver must see it before asking for a source.

        Reads the descriptor files (not the synced registry): a source added by
        the biagent is known immediately, even before the next `catalog.sync()`.
        """
        from mnemosyne.catalog import Catalog

        catalog = Catalog(self.config.sources_path, self.db)
        return {descriptor.id: descriptor for descriptor in catalog.load_descriptors()}

    def _tools(self):
        async def catalog_search_exec(p: CatalogSearchParams):
            engine = Engine(self.config)
            try:
                assets = await engine.search(
                    p.query, source_ids=p.source_ids, limit=p.limit
                )
            except Exception as exc:  # noqa: BLE001 - a search failure is recoverable
                return _fail(f"recherche catalogue impossible : {exc}")
            finally:
                await engine.aclose()
                engine.db.close()
            if not assets:
                return _ok(f"aucun résultat pour {p.query!r} dans la meta API.")
            ranked = rank_assets(p.query, assets)
            rows = [_compact_row(asset) for asset in ranked[:_MAX_ROWS]]
            shown = _fit_rows(rows)
            header = (
                f"{len(assets)} résultat(s) — {len(shown)} meilleurs candidats par "
                f"pertinence (titres/dates), sources du catalogue."
            )
            payload = header + "\n" + json.dumps(shown, ensure_ascii=False)
            hidden = len(ranked) - len(shown)
            if hidden > 0:
                payload += f"\n… {hidden} autre(s) candidat(s) non affiché(s)."
            return _ok(payload)

        async def request_source_exec(p: RequestSourceParams):
            if self.task_id is None:
                return _fail("aucune session resolver ouverte")
            known = self._known_sources()
            wanted = _name_tokens(p.source_id, p.source_name)
            if p.source_id in known:
                descriptor = known[p.source_id]
                state = "activée" if descriptor.enabled else "désactivée"
                return _fail(
                    f"la source {p.source_id} est déjà au catalogue ({state}). "
                    "Interroge-la avec catalog_search(source_ids=[...]) au lieu de "
                    "la redemander ; si elle ne renvoie rien, c'est un trou de "
                    "couverture interne, pas une source manquante."
                )
            requested_id = p.source_id.strip().lower()
            for descriptor in known.values():
                existing_id = descriptor.id.lower()
                # `gallica_bnf` is `gallica` + a qualifier: same provider, new name.
                same_family = requested_id.startswith(f"{existing_id}_") or existing_id.startswith(
                    f"{requested_id}_"
                )
                if (same_family and not p.specialisation) or _same_source(
                    wanted, _name_tokens(descriptor.id, descriptor.name)
                ):
                    state = "activée" if descriptor.enabled else "désactivée"
                    return _fail(
                        f"la source demandée ({p.source_name}) est déjà couverte par "
                        f"`{descriptor.id}` — {state}. Interroge-la avec "
                        f"catalog_search(source_ids=['{descriptor.id}']) ; un "
                        "résultat vide n'autorise pas à recréer la même source. "
                        "Si c'est une vraie spécialisation (périmètre différent), "
                        "rappelle request_source avec specialisation=true et "
                        "explique la différence dans `reason`."
                    )
            for request in self.db.open_resolver_requests():
                if request.get("source_id") == p.source_id or _same_source(
                    wanted, _name_tokens(request.get("source_id"), request.get("source_name"))
                ):
                    return _fail(
                        f"cette source est déjà demandée (request #{request['id']}, "
                        f"tâche #{request.get('biagent_task_id')}) : ne la redemande pas, "
                        "elle sera ajoutée par le biagent."
                    )
            # Same host is allowed: a photo-only sibling of a text connector is
            # a legitimate specialisation (see wikimedia_commons_photos). The
            # duplicate *id* is the only hard error.
            host = domain_of(p.api_url) if p.api_url else ""
            same_host = [
                descriptor
                for descriptor in known.values()
                if host and domain_of(descriptor.base_url) == host
            ]
            segment_id = self._segment_id()
            objective = (
                "Source demandée par le résolveur adversarial"
                + (f" (phrase {segment_id})" if segment_id else "")
                + f" : {p.source_name} ({p.source_id}).\n"
                f"Raison : {p.reason}\n"
                + (f"API/docs : {p.api_url}\n" if p.api_url else "")
                + "Ajoute la source au catalogue (descripteur, connecteur, tests, doc, PR). "
                "Une fois la source terminée, le résolveur sera réveillé et retestera "
                "la phrase avec la meta API à jour."
            )
            try:
                biagent_task_id = self.db.enqueue_task(
                    p.agent,
                    objective,
                    payload={
                        "kind": "resolver_source",
                        "resolver_task_id": self.task_id,
                        "segment_id": segment_id,
                        "source_id": p.source_id,
                        "source_name": p.source_name,
                        "reason": p.reason,
                        "api_url": p.api_url,
                    },
                )
                request_id = self.db.create_resolver_request(
                    self.task_id,
                    sentence_id=segment_id,
                    source_id=p.source_id,
                    source_name=p.source_name,
                    biagent_task_id=biagent_task_id,
                )
            except Exception as exc:  # noqa: BLE001 - never break the session
                return _fail(f"demande de source non enregistrée : {exc}")
            note = ""
            if same_host:
                note = (
                    f" Note : l'hôte {host} est déjà couvert par {same_host[0].id} — "
                    "précise dans la raison en quoi ce profil de recherche diffère."
                )
            return _ok(
                f"tâche biagent #{biagent_task_id} créée (request #{request_id}) pour "
                f"{p.source_name} ; la session resolver sera parquée tant que la source "
                f"n'est pas terminale.{note}"
            )

        async def wait_for_sources_exec(p: EmptyParams):
            if self.task_id is None:
                return _fail("aucune session resolver ouverte")
            pending = self.db.pending_resolver_requests(self.task_id)
            if not pending:
                return _ok("aucune source en attente : tu peux continuer.")
            names = ", ".join(
                str(row.get("source_name") or row.get("source_id") or "?")
                for row in pending
            )
            return _ok(
                f"{len(pending)} source(s) en attente ({names}) — arrête ton tour. "
                "Le supervisor te réveillera quand toutes seront terminales."
            )

        async def record_result_exec(p: RecordResultParams):
            if self.task_id is None:
                return _fail("aucune session resolver ouverte")
            if p.status in ("match", "partial"):
                pending = self.db.pending_asks_for(self.task_id)
                if pending:
                    # `ask_operator` ends the turn; a verdict that needs the
                    # human cannot be self-validated while the ask is open.
                    return _fail(
                        "une question est en attente auprès de l'opérateur "
                        f"(#{pending[0]['id']}) : attends sa réponse avant "
                        "d'enregistrer un match/partial."
                    )
            try:
                self.db.record_resolver_result(
                    self.task_id,
                    segment_id=self._segment_id(),
                    status=p.status,
                    asset_id=p.asset_id,
                    evidence=p.evidence[:4000],
                )
            except Exception as exc:  # noqa: BLE001
                return _fail(f"résultat non enregistré : {exc}")
            return _ok(f"résultat enregistré : {p.status}")

        async def ask_exec(p: AskOperatorParams):
            if self.task_id is None:
                return _fail("aucune session resolver ouverte")
            try:
                ask_id = await ask_operator(
                    self.config,
                    self.db,
                    self.vault_get,
                    agent="resolver",
                    task_id=self.task_id,
                    question=p.question,
                    options=[o.model_dump() for o in p.options],
                    bot_agent="browser",
                )
            except Exception as exc:  # noqa: BLE001 - never break the session
                return _fail(f"question non enregistrée : {exc}")
            return _ok(
                f"question #{ask_id} posée à l'opérateur — arrête ton tour, "
                "tu seras réactivé avec sa réponse."
            )

        return [
            Tool(
                name="catalog_search",
                description=(
                    "Search the biagent meta API (catalog connectors). Results are "
                    "relevance-ranked best-first and truncated: use source_ids to "
                    "drill into one provider, and vary the query wording."
                ),
                parameters=CatalogSearchParams,
                executor=catalog_search_exec,
            ),
            Tool(
                name="request_source",
                description=(
                    "Ask the biagent to add one missing source; creates one biagent "
                    "task and one resolver dependency."
                ),
                parameters=RequestSourceParams,
                executor=request_source_exec,
            ),
            Tool(
                name="wait_for_sources",
                description=(
                    "Park this resolver session until all requested sources are "
                    "terminal. Ends your turn."
                ),
                parameters=EmptyParams,
                executor=wait_for_sources_exec,
            ),
            Tool(
                name="record_result",
                description="Store the structured resolver result for this sentence.",
                parameters=RecordResultParams,
                executor=record_result_exec,
            ),
            Tool(
                name="ask_operator",
                description=(
                    "Ask the human operator a multiple-choice question (candidate "
                    "validation, ambiguity). Ends your turn until the answer."
                ),
                parameters=AskOperatorParams,
                executor=ask_exec,
            ),
        ]


async def run_resolver_agent(
    config: Config,
    task: str,
    *,
    mailbox: Mailbox,
    journal: Journal | None = None,
    vault_get=None,
    task_id: int | None = None,
    max_turns: int | None = None,
) -> AgentOutcome:
    cache_base_dir(config)
    client = build_agent_client(
        config, session="resolver", vault_get=vault_get, model=config.resolver.model
    )
    watch_db = Database(config.db_file())
    try:
        progress = ProgressWatch(
            agent="resolver",
            db=watch_db,
            stall_after_s=config.agents.stall_after_s,
            stall_repeat=config.agents.stall_repeat,
        )
        provider = ResolverToolProvider(
            config,
            mailbox,
            task_id=task_id,
            journal=journal,
            vault_get=vault_get,
        )
        watched = watch_provider(provider, progress, "résolveur")
        agent = Agent(
            client=client,
            name="mnemosyne_resolver",
            system_prompt=load_prompt(
                config.root / "agents" / "resolver.md",
                fallback=_FALLBACK,
                name=config.identity.name,
                task=task,
            ),
            tools=[watched],
            max_turns=max_turns or config.resolver.max_turns,
        )
        out_dir = config.root / config.agents.output_dir
        ensure_dir(out_dir)
        async with agent.session(
            output_dir=str(out_dir),
            cache_on_interrupt=True,
            resume=True,
            clear_cache_on_success=False,
        ) as session:
            finish, history, _metadata = await session.run(task)
        persist_session(config, agent, "resolver")
    finally:
        watch_db.close()
        await client.close()
    usage = client.usage.summary()
    turns = int(usage.get("calls") or 0) or len(history)
    log.info("resolver usage (cache-aware): %s (tours=%d)", usage, turns)
    if journal:
        journal.append(f"resolver usage: {usage}", source="resolver")
    return AgentOutcome(finish=finish_text(finish), turns=turns)
