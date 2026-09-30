"""Heartbeat job handlers.

A handler returns an optional dict of payload updates used when the job recurs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from mnemosyne.config import Config
from mnemosyne.engine import Engine
from mnemosyne.journal import Control, Journal
from mnemosyne.logger import get_logger
from mnemosyne.models import AuthKind, Job, SourceState
from mnemosyne.notify import Notifier
from mnemosyne.vault import Vault

log = get_logger("heartbeat")


def _vault_get(ctx: JobContext):
    if not ctx.config.vault_file.exists():
        return None
    vault = Vault(ctx.config.vault_file)
    return vault.get


async def _browser_ready(ctx: JobContext) -> bool:
    """True when the dedicated Chrome CDP endpoint responds."""
    import httpx

    from mnemosyne.browser import cdp_url

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(cdp_url().rstrip("/") + "/json/version")
        return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


@dataclass
class JobContext:
    config: Config
    engine: Engine
    journal: Journal
    control: Control
    notifier: Notifier


Handler = Callable[[JobContext, Job], Awaitable[dict | None]]

HANDLERS: dict[str, Handler] = {}


def handler(kind: str):
    def wrap(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn

    return wrap


@handler("verify")
async def handle_verify(ctx: JobContext, job: Job) -> dict | None:
    source_id = job.payload["source_id"]
    ok = await ctx.engine.verify(source_id)
    state = "ok" if ok else "degraded"
    log.info("verify %s → %s", source_id, state)
    if not ok:
        ctx.journal.append(f"source `{source_id}` degraded/failing", level="warn", source="verify")
        await ctx.notifier.send(f"source `{source_id}` is degraded/failing", "warn")
    return None


@handler("harvest")
async def handle_harvest(ctx: JobContext, job: Job) -> dict | None:
    source_id = job.payload["source_id"]
    descriptor = ctx.engine.catalog.get(source_id)
    if not descriptor or not descriptor.seeds:
        return None
    index = int(job.payload.get("seed_index", 0))
    seed = descriptor.seeds[index % len(descriptor.seeds)]
    saved = await ctx.engine.harvest(source_id, seed, limit=int(job.payload.get("limit", 20)))
    log.info("harvest %s [%s] → %d new assets", source_id, seed, saved)
    if saved:
        ctx.journal.append(f"harvest `{source_id}` « {seed} » → {saved} nouveaux assets")
    return {"seed_index": index + 1}


@handler("warmup")
async def handle_warmup(ctx: JobContext, job: Job) -> dict | None:
    # P2: drive light, human-like navigation in the dedicated browser to build
    # account reputation before any outbound action.
    phase = ctx.engine.governor.phase()
    log.info(
        "warmup tick (phase until_day=%s, harvest=%d/day, outbound=%d/day)",
        phase.until_day,
        phase.harvest_per_day,
        phase.outbound_per_day,
    )
    ctx.engine.db.set_kv("warmup_last", job.run_at)
    return None


@handler("onboard")
async def handle_onboard(ctx: JobContext, job: Job) -> dict | None:
    """Run the Stirrup onboarding agent to obtain access to a provider."""
    source_id = job.payload["source_id"]
    descriptor = ctx.engine.catalog.get(source_id)
    if descriptor is None or descriptor.auth == AuthKind.NONE:
        return None
    if not ctx.engine.governor.allowed("onboard"):
        log.info("onboard cap reached; skipping %s", source_id)
        return None
    if not await _browser_ready(ctx):
        msg = "Chrome CDP unreachable; cannot run onboarding"
        log.warning(msg)
        ctx.journal.append(msg, level="warn", source="onboard")
        return None

    from mnemosyne.agents.onboarding import run_onboarding

    ctx.engine.catalog.set_state(source_id, SourceState.ONBOARDING)
    ctx.journal.append(f"onboarding `{source_id}` démarré (agent navigateur)")
    ctx.journal.append_service(
        source_id,
        f"début de la tentative d'accès via {descriptor.base_url}",
        title=descriptor.name,
        source="onboard",
    )
    result = await run_onboarding(
        ctx.config, descriptor, vault_get=_vault_get(ctx), journal=ctx.journal
    )
    ctx.engine.governor.record("onboard")

    outcome = result.outcome or {}
    if outcome.get("api_key"):
        ctx.engine.catalog.set_state(source_id, SourceState.CREDENTIALED)
        note = f"onboarding `{source_id}` : accès obtenu, clé stockée"
        await ctx.notifier.send(note, "info")
    elif outcome.get("contact_email") or outcome.get("contact_form_url"):
        ctx.engine.catalog.set_state(source_id, SourceState.PENDING)
        note = f"onboarding `{source_id}` : accès à demander par email/formulaire"
    else:
        ctx.engine.catalog.set_state(source_id, SourceState.DEGRADED)
        note = f"onboarding `{source_id}` : échec — {result.finish or 'sans détail'}"
    ctx.journal.append(note)
    ctx.journal.append_service(
        source_id,
        note + (f" — {result.finish}" if result.finish else ""),
        level="warn" if "échec" in note else "info",
        source="onboard",
    )
    log.info(note)
    return None


@handler("outreach")
async def handle_outreach(ctx: JobContext, job: Job) -> dict | None:
    """Run the Stirrup outreach agent (email / contact form) for a provider."""
    source_id = job.payload["source_id"]
    descriptor = ctx.engine.catalog.get(source_id)
    if descriptor is None:
        return None
    if not ctx.engine.governor.allowed("outbound"):
        log.info("outbound cap reached; skipping outreach to %s", source_id)
        return None
    if not await _browser_ready(ctx):
        log.warning("Chrome CDP unreachable; cannot run outreach")
        return None

    from mnemosyne.agents.outreach import run_outreach

    ask = job.payload.get("ask") or (
        "Je construis un index ouvert d'images d'archives historiques. "
        "Comment obtenir un accès API ou une autorisation pour indexer une partie "
        "de vos collections ? Je cite et relie systématiquement la source."
    )
    ctx.journal.append_service(
        source_id,
        "préparation d'un message de demande d'accès",
        title=descriptor.name,
        source="outreach",
    )
    result = await run_outreach(
        ctx.config,
        descriptor,
        ask,
        contact_email=job.payload.get("contact_email"),
        contact_form_url=job.payload.get("contact_form_url"),
        vault_get=_vault_get(ctx),
        journal=ctx.journal,
    )
    ctx.engine.governor.record("outbound")
    note = f"outreach `{source_id}` : {result.finish or 'terminé'}"
    ctx.journal.append(note)
    ctx.journal.append_service(
        source_id,
        f"message de demande d'accès : {result.finish or 'envoyé'}",
        title=descriptor.name,
        source="outreach",
    )
    await ctx.notifier.send(note, "info")
    return None


@handler("journal")
async def handle_journal(ctx: JobContext, job: Job) -> dict | None:
    """Periodic status digest written to the daily journal."""
    status = ctx.engine.status()
    ctx.journal.append(
        f"status: {status['assets_total']} assets, "
        f"{len(status['sources'])} sources, pressure {status['governor']['pressure']}",
        source="digest",
    )
    return None
