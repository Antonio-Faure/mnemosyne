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
    """Human-like warmup browsing: 1-2 randomized sessions/day inside a window.

    The session itself is a normal mission for the BROWSER agent (read-only
    wandering on archive/history sites); this job only decides *when* and posts
    it to the mailbox, with a tight turn cap.
    """
    from mnemosyne.agents.mailbox import Mailbox
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
    sites = goal.get("sites") or cfg.agents.warmup_sites
    db = ctx.engine.db
    if db.count_pending_from("warmup"):
        ctx.journal.append("warmup : mission déjà en attente", source="warmup")
        return {
            "interval_s": seconds_until_next_slot(
                now, cfg.agents.warmup_window_start, cfg.agents.warmup_window_end
            )
        }

    mission = (
        f"[[tour: {cfg.agents.warmup_max_turns}]]\n"
        f"MISSION WARMUP (~{minutes:.0f} min, lecture seule) — objectif « {goal['name']} ».\n"
        f"Sites : {', '.join(sites)}\n"
        f"{goal.get('instruction', 'Parcourt ces sites comme un curieux.')}\n"
        "\nRègles : navigation lente et humaine (attentes de 5 à 20 s, défilement par\n"
        "petites pages, une recherche Max 2-3, suivi d'un lien ou deux). AUCUNE action\n"
        "sortante : pas de compte, pas de formulaire, pas d'e-mail, pas d'envoi. Ne\n"
        "crée aucun helper, n'écris à personne. Quand le temps est écoulé, termine par\n"
        "finish avec un bilan factuel de ce que tu as parcouru."
    )
    mailbox = Mailbox(db)
    mailbox.post("warmup", "browser", mission)
    db.incr_counter(key)
    db.set_kv("warmup_last", job.run_at)
    note = (
        f"warmup « {goal['name']} » ~{minutes:.0f} min posté au navigateur "
        f"(session {count + 1}/{target})"
    )
    log.info(note)
    ctx.journal.append(note, source="warmup")
    return {
        "interval_s": seconds_until_next_slot(
            now, cfg.agents.warmup_window_start, cfg.agents.warmup_window_end
        )
    }


@handler("agency")
async def handle_agency(ctx: JobContext, job: Job) -> dict | None:
    """Background bi-agent turn: run one pending agent message (turn-taking)."""
    from mnemosyne.agents.supervisor import run_pending_once

    ran = await run_pending_once(ctx.config, journal=ctx.journal, vault_get=_vault_get(ctx))
    if ran:
        log.info("agency background ran agent: %s", ran)
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
    return {"line": line, "alerts": alerts}


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
