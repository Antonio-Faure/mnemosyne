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
from mnemosyne.models import Job, SourceState
from mnemosyne.notify import Notifier

log = get_logger("heartbeat")


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
    # P2: browser-use agent signs up / requests an API key / sends the email.
    source_id = job.payload["source_id"]
    log.info("onboard requested for %s (P2 — not yet implemented)", source_id)
    ctx.engine.catalog.set_state(source_id, SourceState.ONBOARDING)
    ctx.journal.append(f"onboarding demandé pour `{source_id}` (P2)")
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
