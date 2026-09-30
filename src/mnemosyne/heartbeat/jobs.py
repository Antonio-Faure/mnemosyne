"""Heartbeat job handlers.

A handler returns an optional dict of payload updates used when the job recurs.
"""

from __future__ import annotations

import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

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
    """Human-like warmup browsing: 1-2 randomized sessions/day inside a window.

    Each session picks one goal (Gmail, Wikipedia, INA, Gallica…) and wanders
    slowly to build the account's history/coherence. No outbound actions.
    """
    from mnemosyne.agents.warmup import run_warmup
    from mnemosyne.agents.warmup_schedule import (
        daily_session_target,
        pick_goal,
        seconds_until_next_slot,
        seconds_until_next_window,
    )

    cfg = ctx.config
    now = datetime.now()
    today = now.date().isoformat()
    key = f"warmup:{today}"
    count = ctx.engine.db.get_counter(key)
    target = daily_session_target(
        today, cfg.agents.warmup_per_day_min, cfg.agents.warmup_per_day_max
    )

    in_window = cfg.agents.warmup_window_start <= now.hour < cfg.agents.warmup_window_end
    if not in_window or count >= target:
        # outside human hours, or quota reached: sleep until the next window
        return {"interval_s": seconds_until_next_window(now, cfg.agents.warmup_window_start)}

    # humans don't do it on schedule every single time
    if random.random() < cfg.agents.warmup_skip_probability:
        ctx.journal.append("warmup : session sautée (au hasard)", source="warmup")
        return {
            "interval_s": seconds_until_next_slot(
                now, cfg.agents.warmup_window_start, cfg.agents.warmup_window_end
            )
        }

    if not await _browser_ready(ctx):
        ctx.journal.append("warmup : Chrome injoignable, reporté", level="warn", source="warmup")
        return {"interval_s": 1800}

    goal = pick_goal()
    minutes = random.uniform(cfg.agents.warmup_session_min, cfg.agents.warmup_session_max)
    note = f"warmup « {goal['name']} » ~{minutes:.0f} min (session {count + 1}/{target})"
    log.info(note)
    ctx.journal.append(note, source="warmup")
    result = await run_warmup(
        cfg, minutes=minutes, goal=goal, journal=ctx.journal, vault_get=_vault_get(ctx)
    )
    ctx.engine.db.incr_counter(key)
    ctx.engine.db.set_kv("warmup_last", job.run_at)
    ctx.journal.append(
        f"warmup « {goal['name']} » terminé — {result.finish or 'ok'}", source="warmup"
    )
    # next session later, still inside today's human window if possible
    return {
        "interval_s": seconds_until_next_slot(
            now, cfg.agents.warmup_window_start, cfg.agents.warmup_window_end
        )
    }


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


@handler("discover")
async def handle_discover(ctx: JobContext, job: Job) -> dict | None:
    """P3: find candidate providers and store the new ones."""
    from mnemosyne.discovery import host_of, run_discovery

    cfg = ctx.config
    if not cfg.discovery.enabled:
        return None
    records = await run_discovery(ctx.engine.http, limit=cfg.discovery.limit)

    known = {host_of(d.base_url) for d in ctx.engine.catalog.list()}
    known.discard("")

    def is_known(host: str) -> bool:
        return any(
            host == k or host.endswith("." + k) or k.endswith("." + host) for k in known
        )

    fresh = [r for r in records if not is_known(r.host)]
    added = ctx.engine.db.save_discoveries(fresh)
    total = ctx.engine.db.count_discoveries()
    note = f"discovery: {len(records)} candidats, {added} nouveaux (total {total})"
    log.info(note)
    ctx.journal.append(note, source="discover")
    if added:
        top = sorted(fresh, key=lambda r: r.item_count or 0, reverse=True)[:8]
        await ctx.notifier.send(
            "discovery — nouveaux fournisseurs : "
            + ", ".join(f"{r.host} ({r.item_count})" for r in top),
            "info",
        )
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
