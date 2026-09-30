"""Command-line entry point (`mnemosyne ...`)."""

from __future__ import annotations

import argparse
import asyncio
import sys

from mnemosyne.config import get_config
from mnemosyne.engine import Engine
from mnemosyne.logger import get_logger, set_level
from mnemosyne.vault import init_vault

log = get_logger("cli")


def _cmd_vault_init(args: argparse.Namespace) -> int:
    cfg = get_config()
    path = init_vault(cfg.vault_file, overwrite=args.force)
    print(f"vault ready: {path}")
    print("keep vault/vault.key secret (it is git-ignored).")
    return 0


def _cmd_sources(args: argparse.Namespace) -> int:
    cfg = get_config()
    engine = Engine(cfg)
    engine.catalog.sync()
    rows = engine.catalog.list()
    for d in rows:
        status = "enabled" if d.enabled else "disabled"
        print(f"{d.id:18} {d.protocol.value:7} auth={d.auth.value:8} [{status}] {d.name}")
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    cfg = get_config()

    async def run() -> int:
        engine = Engine(cfg)
        try:
            assets = await engine.search(args.query, source_ids=args.source, limit=args.limit)
        finally:
            await engine.aclose()
        if not assets:
            print("no results")
            return 1
        for a in assets:
            year = a.year or "----"
            print(f"[{a.source_id}] {year} {a.title[:70]}")
            print(f"    {a.page_url}")
        print(f"\n{len(assets)} results")
        return 0

    return asyncio.run(run())


def _cmd_harvest(args: argparse.Namespace) -> int:
    cfg = get_config()

    async def run() -> int:
        engine = Engine(cfg)
        try:
            engine.catalog.sync()
            saved = await engine.harvest(args.source, args.query, limit=args.limit)
        finally:
            await engine.aclose()
        print(f"harvested {saved} new assets from {args.source}")
        return 0

    return asyncio.run(run())


def _cmd_status(args: argparse.Namespace) -> int:
    cfg = get_config()
    engine = Engine(cfg)

    async def run() -> int:
        try:
            status = engine.status()
        finally:
            await engine.aclose()
        print(f"assets total: {status['assets_total']}")
        gov = status["governor"]
        print(
            f"governor: age={gov['account_age_days']}d pressure={gov['pressure']} "
            f"harvest today={gov['today']['harvest']}/{gov['warmup']['harvest_per_day']}"
        )
        for s in status["sources"]:
            print(f"  {s['id']:18} {s['state']:12} assets={s['asset_count']}")
        return 0

    return asyncio.run(run())


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    cfg = get_config()
    host = args.host or cfg.api.host
    port = args.port or cfg.api.port
    uvicorn.run("mnemosyne.api.app:app", host=host, port=port, log_level="info")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from mnemosyne.heartbeat import Heartbeat

    cfg = get_config()
    heartbeat = Heartbeat(cfg)

    async def run() -> int:
        try:
            await heartbeat.run_forever()
        finally:
            await heartbeat.aclose()
        return 0

    try:
        return asyncio.run(run())
    except KeyboardInterrupt:
        print("\nheartbeat stopped")
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mnemosyne", description="Archive image provider aggregator"
    )
    parser.add_argument("--log-level", default=None, help="DEBUG/INFO/WARNING/ERROR")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("vault", help="credential vault")
    vsub = p.add_subparsers(dest="vault_command", required=True)
    vi = vsub.add_parser("init", help="create the encrypted vault + key")
    vi.add_argument("--force", action="store_true", help="overwrite an existing key")
    vi.set_defaults(func=_cmd_vault_init)

    ps = sub.add_parser("sources", help="list configured providers")
    ps.set_defaults(func=_cmd_sources)

    psearch = sub.add_parser("search", help="one-shot live search across providers")
    psearch.add_argument("query")
    psearch.add_argument("--source", action="append", default=None, help="restrict to a source id")
    psearch.add_argument("--limit", type=int, default=20)
    psearch.set_defaults(func=_cmd_search)

    ph = sub.add_parser("harvest", help="fetch and store assets from one provider")
    ph.add_argument("--source", required=True)
    ph.add_argument("--query", required=True)
    ph.add_argument("--limit", type=int, default=20)
    ph.set_defaults(func=_cmd_harvest)

    pst = sub.add_parser("status", help="catalog + governor status")
    pst.set_defaults(func=_cmd_status)

    pserve = sub.add_parser("serve", help="run the aggregation API")
    pserve.add_argument("--host", default=None)
    pserve.add_argument("--port", type=int, default=None)
    pserve.set_defaults(func=_cmd_serve)

    prun = sub.add_parser("run", help="run the perpetual heartbeat")
    prun.set_defaults(func=_cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.log_level:
        set_level(args.log_level)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
