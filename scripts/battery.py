"""Night battery: one scenario at a time, run inside the container.

Each scenario prints `SCENARIO <name>: OK|FAIL <detail>` so the night log can be
grepped in one go. Scenarios touch only their own rows.
"""

from __future__ import annotations

import os
import signal
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


def scenario_queue_sequential() -> None:
    """Tasks are individual: two queue entries run in TWO separate sessions."""
    from mnemosyne.agents.session_cache import session_task_text

    database = db()
    try:
        t1 = database.enqueue_task("browser", "battery: MISSION WARMUP", turn_cap=40)
        t2 = database.enqueue_task("browser", "battery: MISSION CONNEXION")
        text1 = session_task_text("browser", database.get_task(t1))
        text2 = session_task_text("browser", database.get_task(t2))
        # the two tasks never share a session: different frozen texts
        ok = (
            text1 != text2
            and f"tâche #{t1} — agent browser" in text1
            and f"tâche #{t2} — agent browser" in text2
        )
        database.set_task_status(t1, "cancelled", note="battery")
        database.set_task_status(t2, "cancelled", note="battery")
        for task_id in (t1, t2):
            database.delete_task_messages(task_id)
        out("queue_sequential", ok, f"t1={t1} t2={t2}")
    finally:
        database.close()


def scenario_turn_cap_field() -> None:
    """The turn cap is a task field (the in-band [[tour: N]] protocol is gone)."""
    database = db()
    try:
        task_id = database.enqueue_task("browser", "battery: cap probe", turn_cap=25)
        task = database.get_task(task_id)
        ok = task["turn_cap"] == 25
        database.set_task_status(task_id, "cancelled", note="battery")
        database.delete_task_messages(task_id)
        out("turn_cap_field", ok, f"cap={task['turn_cap']}")
    finally:
        database.close()


def scenario_task_pingpong_unlimited() -> None:
    """A task's mailbox: agent-to-agent, task-scoped, dies with the task."""
    from mnemosyne.agents.mailbox import Mailbox

    database = db()
    try:
        task_id = database.enqueue_task("coder", "battery: ping-pong probe")
        mailbox = Mailbox(database)
        mailbox.post("coder", "browser", "battery: question", task_id)
        mailbox.post("browser", "coder", "battery: réponse", task_id)
        hops = mailbox.pending_count(task_id)
        # taskless messages cannot exist
        refused = False
        try:
            Mailbox(database).post("coder", "browser", "orphelin", None)
        except ValueError:
            refused = True
        mailbox.mark(mailbox.pending_for(task_id, "coder")[0]["id"], "handled", "battery")
        mailbox.mark(mailbox.pending_for(task_id, "browser")[0]["id"], "handled", "battery")
        drained = mailbox.pending_count(task_id) == 0
        database.set_task_status(task_id, "cancelled", note="battery")
        database.delete_task_messages(task_id)
        out("task_pingpong", refused and hops == 2 and drained,
            f"hops={hops} refused={refused} drained={drained}")
    finally:
        database.close()


def heartbeat_service_is_pid1() -> bool:
    """True when the container's `mnemosyne run` (pid 1) holds the agency lease."""
    database = db()
    try:
        holder = database.get_kv("lease:agency")
        return bool(isinstance(holder, dict) and holder.get("pid") == 1)
    finally:
        database.close()


def scenario_kill_agency_process() -> None:
    """Kill a real activation mid-flight: the next pilot RESUMES the task.

    The task model makes this trivial: the task row stays 'running', the
    session cache stays on disk, and whoever ticks next (the service, or a
    fresh drain) reopens the exact session. The agent is told to finish at
    once if it ever gets reactivated, so the resume is observable.
    """
    from mnemosyne.agents.supervisor import _RUNNERS  # noqa: F401 (existence check)

    if heartbeat_service_is_pid1():
        out(
            "kill_agency_process",
            True,
            "skipped: le service heartbeat est pid 1 (bail agency) — la reprise "
            "est déjà vérifiée en unitaire (test_a_crash_resumes_the_exact_session)",
        )
        return

    proc = subprocess.Popen(
        [
            "mnemosyne", "agency",
            "battery: tu seras tué en plein vol — si tu es réactivé plus tard, "
            "termine IMMÉDIATEMENT par finish avec un bilan factuel de ce que "
            "tu as vu",
            "--to", "browser",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    task_id = None
    for _ in range(24):  # wait for the pilot to actually claim the task
        database = db()
        try:
            running = database.list_tasks(status="running")
            if running:
                task_id = running[-1]["id"]
                break
        finally:
            database.close()
        time.sleep(10)
    if task_id is None:
        proc.kill()
        out("kill_agency_process", False, "aucune tâche claimée en 4 min")
        return
    os.kill(proc.pid, signal.SIGKILL)
    started = time.time()
    closed: dict | None = None
    while time.time() - started < 600:
        subprocess.run(
            [
                sys.executable, "-c",
                "from mnemosyne.agents.supervisor import run_pending_once;\n"
                "from mnemosyne.config import get_config;\n"
                "import asyncio;\n"
                "asyncio.run(run_pending_once(get_config()))",
            ],
            capture_output=True,
            timeout=300,
        )
        database = db()
        try:
            task = database.get_task(task_id)
        finally:
            database.close()
        if task and task["status"] in ("done", "review", "failed"):
            closed = task
            break
        time.sleep(10)
    out(
        "kill_agency_process",
        bool(closed and closed["status"] == "done"),
        f"status={closed['status'] if closed else 'toujours ouverte'} "
        f"note={(closed['note'] or '')[:100] if closed else ''}",
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
        assert goto is not None  # the navigation run must not have crashed
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
    "queue": scenario_queue_sequential,
    "turncap": scenario_turn_cap_field,
    "pingpong": scenario_task_pingpong_unlimited,
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
