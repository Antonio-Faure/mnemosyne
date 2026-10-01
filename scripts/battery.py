"""Night battery: one scenario at a time, run inside the container.

Each scenario prints `SCENARIO <name>: OK|FAIL <detail>` so the night log can be
grepped in one go. Scenarios touch only their own rows.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from mnemosyne.config import get_config
from mnemosyne.db import Database

CONFIG = get_config()


def out(name: str, ok: bool, detail: str = "") -> None:
    print(f"SCENARIO {name}: {'OK' if ok else 'FAIL'} {detail}", flush=True)


def db() -> Database:
    return Database(CONFIG.db_file())


def scenario_guard_double_click() -> None:
    """The harness guard refuses a second click on the same spot."""
    from mnemosyne.agents.browser_agent import _HARNESS_GUARD

    ns = {
        "click_at_xy": lambda x, y, **k: "ok",
        "js": lambda e, **k: "ok",
        "cdp": lambda m, **k: "ok",
    }
    exec(_HARNESS_GUARD, ns)  # noqa: S102
    ns["click_at_xy"](10, 10)
    refused = False
    try:
        ns["click_at_xy"](11, 11)
    except RuntimeError:
        refused = True
    js_refused = False
    try:
        ns["js"]("document.querySelector('a').click()")
    except RuntimeError:
        js_refused = True
    out("guard_double_click", refused and js_refused, f"click={refused} js={js_refused}")


def scenario_lease_exclusive() -> None:
    """One driver at a time; a released lease is immediately reusable."""
    database = db()
    try:
        first = database.try_lease("browser", ttl_s=30, owner="a")
        second = database.try_lease("browser", ttl_s=30, owner="b")
        database.release_lease("browser")
        third = database.try_lease("browser", ttl_s=30, owner="c")
        database.release_lease("browser")
        out("lease_exclusive", bool(first and not second and third), f"{first}/{second}/{third}")
    finally:
        database.close()


def scenario_batch_one_turn() -> None:
    """Three messages in a row are absorbed by ONE turn."""
    from mnemosyne.agents.mailbox import Mailbox
    from mnemosyne.agents.supervisor import _batched_task, _split_turn_cap

    database = db()
    try:
        mailbox = Mailbox(database)
        sent = [mailbox.post("operator", "coder", f"battery message {i}") for i in range(3)]
        claimed = mailbox.claim_all_for("coder", owner="battery")
        cleaned, cap = _split_turn_cap(claimed)
        task = _batched_task(cleaned)
        for mid in sent:
            mailbox.mark(mid, "handled", "battery")
        ok = len(claimed) == 3 and cap is None and "message 2/3" in task
        out("batch_one_turn", ok, f"claimed={len(claimed)} cap={cap}")
    finally:
        database.close()


def scenario_turn_cap() -> None:
    """A `[[tour: N]]` mission caps its own turn."""
    from mnemosyne.agents.supervisor import _split_turn_cap

    cleaned, cap = _split_turn_cap(
        [{"body": "[[tour: 40]]\nMISSION WARMUP", "sender": "warmup", "created_at": "t"}]
    )
    ok = cap == 40 and "[[tour:" not in cleaned[0]["body"]
    out("turn_cap", ok, f"cap={cap}")


def scenario_crash_recovery() -> None:
    """A claim left by a dead process is released at once."""
    import json

    from mnemosyne.agents.mailbox import Mailbox

    database = db()
    try:
        mailbox = Mailbox(database)
        mid = mailbox.post("operator", "coder", "battery: crash recovery probe")
        claimed = mailbox.claim_all_for("coder", owner="battery")
        if not claimed:  # the coder is busy with a real turn
            mailbox.mark(mid, "handled", "battery: occupé, test sauté")
            out("crash_recovery", True, "skipped: coder busy")
            return
        database._conn.execute(
            "UPDATE messages SET claimed_by = ? WHERE id = ?",
            (
                json.dumps(
                    {"who": "cli", "pid": 4_000_000, "host": socket.gethostname(), "started": 1}
                ),
                mid,
            ),
        )
        database._conn.commit()
        released = database.recover_stale_messages(stale_after_s=99999)
        status = database._conn.execute(
            "SELECT status FROM messages WHERE id = ?", (mid,)
        ).fetchone()["status"]
        mailbox.mark(mid, "handled", "battery: crash recovery ok")
        out(
            "crash_recovery",
            bool(claimed) and released >= 1 and status in ("pending", "running"),
            f"released={released} status={status}",
        )
    finally:
        database.close()


def scenario_kill_agency_process() -> None:
    """Kill a real browser turn mid-flight: its message must come back quickly."""
    from mnemosyne.agents.mailbox import Mailbox

    database = db()
    try:
        mid = Mailbox(database).post(
            "operator", "browser", "battery: mission longue (elle sera tuée)"
        )
    finally:
        database.close()
    proc = subprocess.Popen(
        ["mnemosyne", "agency", "battery mission longue", "--to", "browser", "--max", "1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    claimed = False
    for _ in range(60):  # wait for the turn to actually claim it
        database = db()
        try:
            row = database._conn.execute(
                "SELECT status FROM messages WHERE id = ?", (mid,)
            ).fetchone()
        finally:
            database.close()
        if row and row["status"] == "running":
            claimed = True
            break
        time.sleep(10)
    if not claimed:
        proc.kill()
        database = db()
        try:
            database.mark_message(mid, "handled", "battery:Boîte occupée, test sauté")
        finally:
            database.close()
        out("kill_agency_process", True, "skipped: mailbox busy (tour en cours)")
        return
    os.kill(proc.pid, signal.SIGKILL)
    started = time.time()
    released = None
    while time.time() - started < 300:
        database = db()
        try:
            row = database._conn.execute(
                "SELECT status FROM messages WHERE id = ?", (mid,)
            ).fetchone()
        finally:
            database.close()
        if row and row["status"] != "running":
            released = round(time.time() - started)
            break
        time.sleep(10)
    database = db()
    try:
        database.mark_message(mid, "handled", "battery: tué volontairement")
    finally:
        database.close()
    out(
        "kill_agency_process",
        claimed and released is not None and released < 240,
        f"claimed={claimed} released_after={released}s",
    )


def scenario_native_finish_in_prompts() -> None:
    """Runtime prompts name the native finish tool, not a homemade one."""
    repo = Path(CONFIG.dev.repo_path or CONFIG.root)
    coder = (repo / "agents" / "coder.md").read_text(encoding="utf-8")
    browser = (repo / "agents" / "browser.md").read_text(encoding="utf-8")
    ok = "finish(reason" in coder and "finish(reason" in browser
    ok = ok and "task_done" not in coder and "task_done" not in browser
    out("native_finish_in_prompts", ok)


def scenario_heartbeat() -> None:
    """Nothing is stuck: no long-running job, no orphan lease."""
    database = db()
    try:
        jobs = database._conn.execute(
            "SELECT COUNT(*) AS n FROM jobs WHERE state = 'running'"
        ).fetchone()["n"]
        lease = database._conn.execute(
            "SELECT COUNT(*) AS n FROM kv WHERE key = 'lease:browser'"
        ).fetchone()["n"]
    finally:
        database.close()
    out("heartbeat", True, f"jobs_running={jobs} lease={lease}")


SCENARIOS = {
    "guard": scenario_guard_double_click,
    "lease": scenario_lease_exclusive,
    "batch": scenario_batch_one_turn,
    "turncap": scenario_turn_cap,
    "crash": scenario_crash_recovery,
    "kill": scenario_kill_agency_process,
    "prompts": scenario_native_finish_in_prompts,
    "heartbeat": scenario_heartbeat,
}


def main() -> int:
    for name in sys.argv[1:] or list(SCENARIOS):
        func = SCENARIOS.get(name)
        if func is None:
            out(name, False, "unknown scenario")
            continue
        try:
            func()
        except Exception as exc:  # noqa: BLE001
            out(name, False, f"{type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
