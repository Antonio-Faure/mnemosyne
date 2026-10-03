"""Heartbeat job handlers.

A handler returns an optional dict of payload updates used when the job recurs.
"""

from __future__ import annotations

import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from mnemosyne.config import Config
from mnemosyne.engine import Engine
from mnemosyne.journal import Control, Journal
from mnemosyne.logger import get_logger
from mnemosyne.models import Job
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
    """The mission cycle: 1 warmup → 1 source connection, alternating.

    Both legs are ordinary TASKS in the operator's queue (start=browser) —
    never mixed into one session. This job only decides *when* and which leg
    to post; a connexion leg with no candidate falls back to a warmup (the
    daily quota applies to warmup legs only). The session itself runs under
    the agency job.
    """
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
    if not in_window:
        # outside human hours: sleep until the next window
        return {"interval_s": seconds_until_next_window(now, cfg.agents.warmup_window_start)}

    db = ctx.engine.db
    cycle = db.get_kv("mission_cycle", 0)
    candidate = _connexion_candidate(ctx) if cycle % 2 == 1 else None
    if candidate is None and count >= target:
        # warmup quota reached and nothing to connect: sleep until tomorrow
        return {"interval_s": seconds_until_next_window(now, cfg.agents.warmup_window_start)}

    if not await _browser_ready(ctx):
        ctx.journal.append("cycle : Chrome injoignable, reporté", level="warn", source="warmup")
        return {"interval_s": 1800}

    minutes = random.uniform(cfg.agents.warmup_session_min, cfg.agents.warmup_session_max)

    if candidate is not None:
        mission = (
            f"MISSION CONNEXION DE SOURCE (~{minutes:.0f} min) — "
            f"objectif « {candidate.name} ».\n"
            f"Portail : {candidate.base_url} (auth={candidate.auth.value}).\n"
            f"Obtiens un accès légitime pour le compte archivist "
            f"({ctx.config.identity.agent_email}) : inscris-toi ou connecte-toi, "
            f"récupère la clé ou le jeton nécessaire, puis "
            f"remember('{candidate.id}_api_key', …) et écris au codeur pour "
            "brancher le connecteur si besoin.\n"
            "Règles : UNIQUEMENT l'objectif de cette mission — pas d'autre "
            "inscription, pas d'envoi sortant. Termine par finish avec un bilan "
            "factuel (ce qui a été obtenu, où, sous quel nom)."
        )
        db.enqueue_task(
            "browser", mission, turn_cap=cfg.agents.warmup_max_turns,
            payload={"kind": "connexion", "source_id": candidate.id},
        )
        note = f"connexion « {candidate.name} » postée au navigateur (cycle {cycle + 1})"
    else:
        # humans don't do it on schedule every single time
        if random.random() < cfg.agents.warmup_skip_probability:
            ctx.journal.append("cycle : session sautée (au hasard)", source="warmup")
            return {
                "interval_s": seconds_until_next_slot(
                    now, cfg.agents.warmup_window_start, cfg.agents.warmup_window_end
                )
            }
        goal = pick_goal()
        sites = goal.get("sites") or cfg.agents.warmup_sites
        mission = (
            f"MISSION WARMUP (~{minutes:.0f} min, lecture seule) — "
            f"objectif « {goal['name']} ».\n"
            f"Sites : {', '.join(sites)}\n"
            f"{goal.get('instruction', 'Parcourt ces sites comme un curieux.')}\n"
            "\nRègles : navigation lente et humaine (attentes de 5 à 20 s, "
            "défilement par petites pages, une recherche ou deux, suivi d'un "
            "lien ou deux). AUCUNE action sortante : pas de compte, pas de "
            "formulaire, pas d'e-mail. Ne crée aucun helper, n'écris à "
            "personne. Termine par finish avec un bilan factuel."
        )
        db.enqueue_task(
            "browser", mission, turn_cap=cfg.agents.warmup_max_turns,
            payload={"kind": "warmup"},
        )
        db.incr_counter(key)
        note = (
            f"warmup « {goal['name']} » ~{minutes:.0f} min posté au navigateur "
            f"(session {count + 1}/{target})"
        )
    db.set_kv("mission_cycle", cycle + 1)
    log.info(note)
    ctx.journal.append(note, source="warmup")
    return {
        "interval_s": seconds_until_next_slot(
            now, cfg.agents.warmup_window_start, cfg.agents.warmup_window_end
        )
    }


def _connexion_candidate(ctx: JobContext):
    """A source that needs an access the vault does not hold, with no task open."""
    from mnemosyne.models import AuthKind

    db = ctx.engine.db
    vault = _vault_get(ctx)
    for descriptor in ctx.engine.catalog.sync():
        if descriptor.auth == AuthKind.NONE:
            continue
        if db.has_open_task(source_id=descriptor.id):
            continue
        if vault and vault(f"{descriptor.id}_api_key"):
            continue  # access already obtained
        return descriptor
    return None


@handler("agency")
async def handle_agency(ctx: JobContext, job: Job) -> dict | None:
    """Background bi-agent turn: run one pending agent message (turn-taking)."""
    from mnemosyne.agents.supervisor import run_pending_once

    ran = await run_pending_once(ctx.config, journal=ctx.journal, vault_get=_vault_get(ctx))
    if ran:
        log.info("agency background ran agent: %s", ran.get("agent"))
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


@handler("watchdog")
async def handle_watchdog(ctx: JobContext, job: Job) -> dict | None:
    """Check the invariants and log one line, every 5 minutes.

    Runs inside the service (not as a side process), so it survives a restart
    and cannot be forgotten. Alerts are information only: nothing is stopped.
    """
    from mnemosyne.monitor import report

    out = Path(ctx.config.data_path) / "outbox" / "soak.log"
    out.parent.mkdir(parents=True, exist_ok=True)
    line, alerts = report(ctx.config, out)
    if alerts:
        log.warning("watchdog: %d alerte(s)\n  %s", len(alerts), "\n  ".join(alerts))
    # No return: the log is the contract. Returning the line/alerts would grow
    # the next run's job payload every 5 minutes, with no reader.
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
