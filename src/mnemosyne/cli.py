"""Command-line entry point (`mnemosyne ...`)."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from mnemosyne.config import get_config
from mnemosyne.engine import Engine
from mnemosyne.journal import Control, Journal
from mnemosyne.llm import LlmClient
from mnemosyne.logger import get_logger, set_level
from mnemosyne.notify import Notifier
from mnemosyne.vault import Vault, init_vault

log = get_logger("cli")


def _cmd_vault_init(args: argparse.Namespace) -> int:
    cfg = get_config()
    path = init_vault(cfg.vault_file, overwrite=args.force)
    print(f"vault ready: {path}")
    print("keep vault/vault.key secret (it is git-ignored).")
    return 0


def _cmd_vault_set(args: argparse.Namespace) -> int:
    cfg = get_config()
    vault = Vault(cfg.vault_file)
    vault.set(args.key, args.value)
    print(f"stored '{args.key}' in vault")
    return 0


def _cmd_vault_list(args: argparse.Namespace) -> int:
    cfg = get_config()
    vault = Vault(cfg.vault_file)
    for key in vault.keys():
        print(key)
    return 0


def _cmd_journal(args: argparse.Namespace) -> int:
    cfg = get_config()
    journal = Journal(cfg.journal_path)
    if getattr(args, "services", False):
        services = journal.list_services()
        if not services:
            print("(aucun journal de service)")
            return 0
        for service in services:
            print(service)
        return 0
    if getattr(args, "service", None):
        text = journal.read_service(args.service)
        if not text:
            print(f"(aucun journal pour le service '{args.service}')")
            return 0
        print(text)
        return 0
    if args.date:
        from datetime import date

        text = journal.read(date.fromisoformat(args.date))
    else:
        text = journal.read()
    if not text:
        print("(journal vide)")
        return 0
    print(text)
    return 0


def _cmd_say(args: argparse.Namespace) -> int:
    cfg = get_config()
    control = Control(cfg.control_path)
    control.post(args.message)
    print("message déposé dans control/inbox.md — il sera lu au prochain tick.")
    return 0


def _cmd_llm_test(args: argparse.Namespace) -> int:
    cfg = get_config()
    vault = Vault(cfg.vault_file) if cfg.vault_file.exists() else None
    client = LlmClient(cfg, session="mnemosyne-doctor", vault_get=vault.get if vault else None)
    print("auth:", client.describe())

    async def run() -> int:
        try:
            reply = await client.complete("Réponds uniquement par le mot: OK", temperature=0.0)
        except Exception as exc:  # noqa: BLE001
            print(f"LLM call failed: {exc}")
            return 1
        print("reply:", reply.strip()[:200] or "(vide)")
        print("usage:", client.last_usage or "(non fourni par le provider)")
        return 0

    return asyncio.run(run())


def _cmd_develop(args: argparse.Namespace) -> int:
    cfg = get_config()
    if not cfg.dev.enabled:
        print("self-extension is disabled (config.dev.enabled=false)")
        return 1
    from mnemosyne.dev.agent import run_dev_agent

    vault = Vault(cfg.vault_file) if cfg.vault_file.exists() else None
    vault_get = vault.get if vault else None
    token = (vault_get("github_token") if vault_get else None) or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Aucun jeton GitHub (vault 'github_token' ou env GITHUB_TOKEN).")
        print("L'agent pourra éditer/tester en local mais pas pousser. Stocke-le avec :")
        print("  make token")
        print("  # ou : .venv/bin/mnemosyne vault set github_token <token>")

    outcome = asyncio.run(
        run_dev_agent(
            cfg,
            args.task,
            vault_get=vault_get,
            journal=Journal(cfg.journal_path),
        )
    )
    print("finish:", outcome.finish or "(pas de résumé)")
    print("branch:", outcome.branch or "(aucune)")
    return 0


def _cmd_warmup(args: argparse.Namespace) -> int:
    cfg = get_config()
    from mnemosyne.agents.warmup import run_warmup

    vault = Vault(cfg.vault_file) if cfg.vault_file.exists() else None
    outcome = asyncio.run(
        run_warmup(
            cfg,
            minutes=args.minutes,
            journal=Journal(cfg.journal_path),
            vault_get=vault.get if vault else None,
        )
    )
    print("finish:", outcome.finish or "(pas de résumé)")
    print("usage:", outcome.outcome.get("usage"))
    return 0


def _cmd_telegram_test(args: argparse.Namespace) -> int:
    cfg = get_config()
    notifier = Notifier(cfg.notify.telegram)

    async def run() -> int:
        me = await notifier.get_me()
        print(f"bot: @{(me or {}).get('username', '?')}  enabled={notifier.enabled}")
        ok = await notifier.send("test de connexion — si tu vois ce message, tout marche ✅")
        print("send:", "ok" if ok else "échec")
        if not ok:
            print("→ ouvre la conversation du bot dans Telegram et envoie /start,")
            print("  puis vérifie MNEMOSYNE_TELEGRAM_CHAT_ID (mnemosyne telegram updates).")
        return 0 if ok else 1

    return asyncio.run(run())


def _cmd_telegram_updates(args: argparse.Namespace) -> int:
    cfg = get_config()
    notifier = Notifier(cfg.notify.telegram)

    async def run() -> int:
        me = await notifier.get_me()
        print(f"bot: @{(me or {}).get('username', '?')}")
        updates = await notifier.get_updates()
        print(f"updates: {len(updates)}  (chat_id configuré: {notifier.chat_id})")
        for update in updates[-10:]:
            msg = update.get("message") or {}
            chat = msg.get("chat") or {}
            print(f"  chat_id={chat.get('id')} text={(msg.get('text') or '')[:60]}")
        if not updates:
            print("→ Envoie /start au bot depuis Telegram, puis relance cette commande.")
        return 0

    return asyncio.run(run())


def _cmd_doctor(args: argparse.Namespace) -> int:
    cfg = get_config()
    print("=== mnemosyne doctor ===")
    print(f"root:        {cfg.root}")
    print(f"data dir:    {cfg.data_path}  (exists={cfg.data_path.exists()})")
    print(f"vault:       {cfg.vault_file}  (exists={cfg.vault_file.exists()})")
    print(f"journal:     {cfg.journal_path}")
    print(f"control:     {cfg.control_path}")

    vault = Vault(cfg.vault_file) if cfg.vault_file.exists() else None
    client = LlmClient(cfg, session="mnemosyne-doctor", vault_get=vault.get if vault else None)
    print(f"llm:         {client.describe()}")

    async def check_cdp() -> None:
        import httpx

        from mnemosyne.browser import cdp_url

        url = cdp_url().rstrip("/") + "/json/version"
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                resp = await c.get(url)
            print(f"chrome cdp:  OK ({resp.json().get('Browser', '?')})")
        except Exception as exc:  # noqa: BLE001
            print(f"chrome cdp:  unreachable at {url} — {exc}")

    notifier = Notifier(cfg.notify.telegram)

    async def check_telegram() -> None:
        me = await notifier.get_me()
        print(
            f"telegram:    enabled={notifier.enabled} chat_id={notifier.chat_id} "
            f"bot=@{((me or {}).get('username') or '?')}"
        )

    async def check_all() -> None:
        await check_cdp()
        await check_telegram()

    asyncio.run(check_all())
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
    vs = vsub.add_parser("set", help="store a secret (e.g. opencode_api_key)")
    vs.add_argument("key")
    vs.add_argument("value")
    vs.set_defaults(func=_cmd_vault_set)
    vl = vsub.add_parser("list", help="list stored secret keys")
    vl.set_defaults(func=_cmd_vault_list)

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

    pj = sub.add_parser("journal", help="show the daily journal or a service journal")
    pj.add_argument("--date", default=None, help="YYYY-MM-DD (default: today)")
    pj.add_argument("--service", default=None, help="show the journal of one service")
    pj.add_argument("--services", action="store_true", help="list service journals")
    pj.set_defaults(func=_cmd_journal)

    psay = sub.add_parser("say", help="send a message/instruction to the agent")
    psay.add_argument("message")
    psay.set_defaults(func=_cmd_say)

    pllm = sub.add_parser("llm", help="LLM (OpenCode Go) utilities")
    lsub = pllm.add_subparsers(dest="llm_command", required=True)
    lt = lsub.add_parser("test", help="check auth + one round-trip")
    lt.set_defaults(func=_cmd_llm_test)

    pw = sub.add_parser("warmup", help="human-like browsing session (reputation warmup)")
    pw.add_argument("--minutes", type=float, default=5.0)
    pw.set_defaults(func=_cmd_warmup)

    pdev = sub.add_parser("develop", help="self-extension: add a provider via PR")
    pdev.add_argument("task", help="what to build, e.g. 'Add the Europeana connector'")
    pdev.set_defaults(func=_cmd_develop)

    ptg = sub.add_parser("telegram", help="Telegram bot utilities")
    tg = ptg.add_subparsers(dest="telegram_command", required=True)
    tt = tg.add_parser("test", help="send a test message to the operator")
    tt.set_defaults(func=_cmd_telegram_test)
    tu = tg.add_parser("updates", help="show received messages and chat ids")
    tu.set_defaults(func=_cmd_telegram_updates)

    pd = sub.add_parser("doctor", help="diagnose config, vault, LLM auth and Chrome")
    pd.set_defaults(func=_cmd_doctor)

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
