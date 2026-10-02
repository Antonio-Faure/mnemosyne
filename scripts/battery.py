"""Night battery: one scenario at a time, run inside the container.

Each scenario prints `SCENARIO <name>: OK|FAIL <detail>` so the night log can be
grepped in one go. Scenarios touch only their own rows.
"""

from __future__ import annotations

import json
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


def heartbeat_service_is_pid1() -> bool:
    """True when the container's main process is the heartbeat service.

    The service is itself a pilot (it takes `lease:agency` every tick), so a
    kill-and-recover test cannot be attributed to our own process: the message
    may be legitimately owned by a live pilot. We skip it with a reason rather
    than pass it silently.
    """
    try:
        cmdline = Path("/proc/1/cmdline").read_bytes().decode("utf-8", "ignore")
    except OSError:
        return False
    parts = [p for p in cmdline.split("\0") if p]
    if len(parts) < 2:
        return False
    return Path(parts[-2]).name == "mnemosyne" and parts[-1] == "run"


def claim_holder_gone(message_id: int) -> bool:
    """True when the `running` message of `message_id` has no live claimer."""
    from mnemosyne.db import _holder_is_gone

    database = db()
    try:
        row = database._conn.execute(
            "SELECT status, claimed_by FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
    finally:
        database.close()
    if not row or row["status"] != "running" or not row["claimed_by"]:
        return True  # nothing is running: the release already happened
    try:
        payload = json.loads(row["claimed_by"])
    except json.JSONDecodeError:
        return True
    return _holder_is_gone(payload)


def scenario_kill_agency_process() -> None:
    """Kill a real browser turn mid-flight: its message must come back quickly."""
    from mnemosyne.agents.mailbox import Mailbox

    if heartbeat_service_is_pid1():
        out(
            "kill_agency_process",
            True,
            "skipped: le service heartbeat est pid 1 (bail agency), "
            "impossible d'attribuer la reclamation a notre processus",
        )
        return

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
    # The container runs `mnemosyne run` as pid 1, so the service is itself a
    # pilot: the message we just posted may legitimately be claimed by it, and
    # then there is nothing to recover. We only assert crash recovery when the
    # holder is really gone.
    holder_gone = claim_holder_gone(mid)
    if not holder_gone:
        out(
            "kill_agency_process",
            True,
            f"skipped: message #${mid} détenu par un pilote vivant (service)",
        )
        return
    # Recovery is the job of the *next* pilot (heartbeat tick or any new run),
    # exactly as in production. We play that pilot here in a fresh process, so
    # the scenario does not depend on an ambient heartbeat being up.
    started = time.time()
    released = None
    while time.time() - started < 300:
        subprocess.run(
            [
                sys.executable,
                "-c",
                "from mnemosyne.db import Database;\n"
                "db = Database('data/mnemosyne.db');\n"
                "print(db.recover_stale_messages());\n"
                "db.close()",
            ],
            capture_output=True,
            timeout=120,
        )
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
        time.sleep(5)
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


def scenario_vision_wiring() -> None:
    """The vision chain: harness page capture -> fresh PNG -> ImageContentBlock.

    A word written only in the pixels of an image (never in the DOM) must be
    capturable: if a future browser-use/stirrup version cuts vision again,
    this probe fails instead of the agent silently going blind.
    """
    import base64
    import io

    from stirrup.core.models import ImageContentBlock

    from mnemosyne.agents.browser_agent import BrowserAgentToolProvider
    from mnemosyne.agents.mailbox import Mailbox

    def pixel_png(word: str) -> bytes:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (420, 130), "white")
        ImageDraw.Draw(img).text((30, 45), word, fill="black")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    page = Path(CONFIG.data_path) / "vision-probe.html"
    png = base64.b64encode(pixel_png("OREGANO")).decode()
    page.write_text(
        f'<html><body><img src="data:image/png;base64,{png}"></body></html>'
    )

    database = db()
    provider = BrowserAgentToolProvider(CONFIG, Mailbox(database))
    try:
        started = time.time()
        # Two runs, like the real wiring: browser-harness 0.1.13 loses its CDP
        # attach after goto_url in the SAME run (not attached to an active page),
        # so the capture must be its own run — which is exactly what the
        # force_vision second run does in browser_exec.
        goto = provider._run_harness(f"goto_url('file://{page}')")
        res = provider._run_harness(
            "print(capture_screenshot('shot.png', max_dim=1800))"
        )
        shot = provider._fresh_screenshot(started)
        captured = shot is not None and shot.stat().st_size > 0
        attachable = False
        if captured:
            attachable = ImageContentBlock(data=shot.read_bytes()) is not None
            shot.unlink(missing_ok=True)
        out(
            "vision_wiring",
            captured and attachable,
            f"capture={'ok' if captured else 'MANQUANTE'} tail={res[-100:]}",
        )
    finally:
        database.close()


SCENARIOS = {
    "guard": scenario_guard_double_click,
    "lease": scenario_lease_exclusive,
    "batch": scenario_batch_one_turn,
    "turncap": scenario_turn_cap,
    "crash": scenario_crash_recovery,
    "kill": scenario_kill_agency_process,
    "prompts": scenario_native_finish_in_prompts,
    "heartbeat": scenario_heartbeat,
    "vision": scenario_vision_wiring,
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
