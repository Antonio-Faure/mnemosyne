"""Browser agent (Stirrup) — drives the real Chrome through browser-harness.

Owns everything web: navigation, warmup, precise research, emails, forms,
obtaining access/keys, AND improving its own harness (helpers) and making videos.
It cannot edit the product code; it reports to the coder through the mailbox.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field
from stirrup import Agent
from stirrup.core.models import (
    EmptyParams,
    ImageContentBlock,
    Tool,
    ToolProvider,
    ToolResult,
    ToolUseCountMetadata,
)

from mnemosyne.agents.mailbox import Mailbox
from mnemosyne.agents.outcome import AgentOutcome
from mnemosyne.agents.progress import ProgressWatch, watch_provider
from mnemosyne.browser.recordings import prune_recordings
from mnemosyne.browser.stirrup_client import build_agent_client
from mnemosyne.config import Config
from mnemosyne.dev.git_ops import Git, GitError
from mnemosyne.dev.worktree import add_worktree
from mnemosyne.identity import disclosure
from mnemosyne.journal import Journal
from mnemosyne.logger import get_logger
from mnemosyne.util import atomic_write_text, ensure_dir, finish_text, load_prompt
from mnemosyne.vault import Vault

log = get_logger("browser_agent")

_MAX_OUTPUT = 4000
_SKILLS_MAX_CHARS = 12000

_FALLBACK = "You are {name}, the browser agent of mnemosyne. {disclosure} {skills}"


class BrowserCodeParams(BaseModel):
    code: str = Field(description="Python code executed against Chrome via browser-harness")


class HelperNameParams(BaseModel):
    name: str = Field(description="Helper file name, e.g. 'europeana.py'")


class WriteHelperParams(BaseModel):
    name: str = Field(description="Helper file name, e.g. 'europeana.py'")
    code: str = Field(description="Full Python content of the helper")


class PublishParams(BaseModel):
    summary: str = Field(description="Commit/PR message describing the helper change")


class SendMessageParams(BaseModel):
    to: str = Field(description="Recipient: 'coder'")
    body: str = Field(description="Message (never include secrets — use vault references)")


class RememberParams(BaseModel):
    key: str = Field(description="Vault key, e.g. 'europeana_api_key'")
    value: str = Field(description="Secret value to store (never sent in a message)")


#: vault entries only the operator may set
_RESERVED_VAULT_KEYS = frozenset({"github_token", "opencode_api_key"})

#: env vars never handed to the harness subprocess (secrets stay in our process)
_SECRET_ENV_RE = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)", re.I)

#: `browser(code)` is a navigation tool, never a shell: a rogue snippet once ran
#: git in /repo (checkout + commit + PR). Refuse the escape vectors; the
#: `browser-harness video …` CLI stays allowed.
_FORBIDDEN_CODE = re.compile(
    r"\b__import__\b|\bos\.system\b|\bos\.popen\b|"
    r"\bsubprocess\b[\s\S]*\bgit\b|\bgit\b[\s\S]*\bsubprocess\b|"
    r"\bgit\s+(add|commit|push|checkout|switch|branch|remote|reset|clean)\b",
    re.IGNORECASE,
)

#: One canonical action path: `click_at_xy` for clicks, js()/cdp() for reading
#: only. Prepended to every browser(code) snippet — executing in the harness
#: process, where the helpers are already imported — so retrying a submission
#: through another mechanism (or re-clicking the same spot) fails loudly instead
#: of duplicating the action.
_HARNESS_GUARD = '''
# --- mnemosyne guard: one click path, observations only via js()/cdp() ---
import re as _mn_re, time as _mn_time

if all(name in globals() for name in ("click_at_xy", "js", "cdp")):
    _mn_recent_clicks = []
    _mn_real_click = click_at_xy

    def click_at_xy(x, y, button="left", clicks=1):
        now = _mn_time.monotonic()
        while _mn_recent_clicks and now - _mn_recent_clicks[0][2] > 3.0:
            _mn_recent_clicks.pop(0)
        for px, py, _t in _mn_recent_clicks:
            if abs(px - float(x)) <= 3 and abs(py - float(y)) <= 3:
                raise RuntimeError(
                    "mnemosyne: double clic refuse vers (%s, %s) — verifie l'etat "
                    "de la page (capture_screenshot/read_page) au lieu de "
                    "recliquer, ne resoumets jamais" % (x, y)
                )
        _mn_recent_clicks.append((float(x), float(y), now))
        return _mn_real_click(x, y, button=button, clicks=clicks)

    _mn_real_js = js
    _mn_submit_js = _mn_re.compile(
        r"\\.click\\s*\\(|requestSubmit|\\.submit\\s*\\(|MouseEvent", _mn_re.I
    )

    def js(expression, target_id=None):
        if _mn_submit_js.search(expression or ""):
            raise RuntimeError(
                "mnemosyne: clic/soumission via js() interdit — js() sert a LIRE ; "
                "clique avec click_at_xy (une seule fois, puis verifie)"
            )
        return _mn_real_js(expression, target_id=target_id)

    _mn_real_cdp = cdp

    def cdp(method, *args, **kwargs):
        if method == "Input.dispatchMouseEvent":
            raise RuntimeError(
                "mnemosyne: clic via cdp() interdit — utilise click_at_xy ; "
                "cdp() sert a observer"
            )
        return _mn_real_cdp(method, *args, **kwargs)

if all(name in globals() for name in ("goto_url", "wait_for_load")):
    # upstream #879: goto_url() is non-blocking; a capture in the same run can
    # hit the navigation transition (-32000 "Not attached to an active page").
    # Settle the page before anything else observes it.
    _mn_real_goto = goto_url

    def goto_url(url):
        result = _mn_real_goto(url)
        try:
            wait_for_load(timeout=15.0)
        except Exception:
            pass
        return result
# --- end guard ---
'''


def _ok(content: str) -> ToolResult[ToolUseCountMetadata]:
    return ToolResult(content=content, metadata=ToolUseCountMetadata())


def _fail(content: str) -> ToolResult[ToolUseCountMetadata]:
    return ToolResult(content=content, success=False, metadata=ToolUseCountMetadata())


def _load_skills(repo: Path, limit: int = _SKILLS_MAX_CHARS) -> str:
    skills_dir = repo / "harness" / "skills"
    if not skills_dir.exists():
        return "(no skills available)"
    chunks: list[str] = []
    total = 0
    for path in sorted(skills_dir.glob("*.md")):
        if path.name.upper().startswith("README"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            continue
        block = f"### {path.stem}\n{text}\n"
        if total + len(block) > limit:
            break
        chunks.append(block)
        total += len(block)
    return "\n".join(chunks) or "(no skills available)"


class BrowserAgentToolProvider(ToolProvider):
    def __init__(
        self,
        config: Config,
        mailbox: Mailbox,
        *,
        token: str | None = None,
        journal: Journal | None = None,
        task_id: int | None = None,
    ):
        self.config = config
        self.mailbox = mailbox
        # messages live INSIDE the task's temporary mailbox
        self.task_id = task_id
        # the supervisor's database handle: one connection per turn, closed by
        # whoever opened it (run_pending_once) — no dedicated leak here
        self._db = mailbox.db
        self.journal = journal
        self.repo = Path(config.dev.repo_path or config.root)
        self.worktree = Path(config.data_path) / "agent-workspace" / "helpers-worktree"
        self._ensure_worktree()
        self._refresh_worktree()
        self._prune_recordings()
        self.helpers_dir = self.worktree / "harness" / "helpers"
        ensure_dir(self.helpers_dir)
        self.token = token
        self.git = Git(self.worktree, token)
        #: Stuck detection, not a deadline: a long mission that advances is left
        #: alone; only a freeze or a loop gets the honest-report nudge.
        self.progress = ProgressWatch(
            agent="browser",
            db=self._db,
            stall_after_s=config.agents.stall_after_s,
            stall_repeat=config.agents.stall_repeat,
        )

    def _prune_recordings(self) -> None:
        """Bound the disk: the harness never deletes its own recordings."""
        try:
            result = prune_recordings(keep=self.config.agents.recordings_keep)
        except Exception as exc:  # noqa: BLE001 - housekeeping must never block a run
            log.debug("prune recordings failed (%s)", exc)
            return
        if result.removed:
            log.info(
                "recordings: %d conservés, %d supprimés (%.0f Mo libérés)",
                result.kept,
                len(result.removed),
                result.freed_bytes / 1e6,
            )

    def _refresh_worktree(self) -> None:
        """Track the base branch so helpers published on main become visible.

        The worktree follows an `agent/*` branch after a publish, and a squash
        merge makes that branch diverge, so a fast-forward alone would never
        bring new helpers. We therefore re-point a local branch at the base
        branch (published commits stay in the repo), and we never touch a
        worktree that has uncommitted helper edits.
        """
        if not self._worktree_is_usable():
            return
        try:
            dirty = subprocess.run(
                ["git", "-C", str(self.worktree), "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("helpers worktree refresh failed (%s)", exc)
            return
        if dirty.returncode == 0 and dirty.stdout.strip():
            log.debug("helpers worktree has local changes; keeping it as is")
            return
        base = self.config.dev.base_branch
        for args in (
            ["fetch", "--quiet", "origin", base],
            ["checkout", "-B", f"helpers/{base}", "--quiet", f"origin/{base}"],
        ):
            try:
                probe = subprocess.run(
                    ["git", "-C", str(self.worktree), *args],
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
            except Exception as exc:  # noqa: BLE001
                log.debug("helpers worktree refresh failed (%s)", exc)
                return
            if probe.returncode != 0:
                log.debug("helpers worktree refresh: %s", probe.stderr.strip()[:160])
                return
        log.info("helpers worktree aligned on origin/%s", base)

    def _worktree_is_usable(self) -> bool:
        """A .git file is not enough: the gitdir it points at must exist.

        The repo is also used from the host (different absolute path), so a
        worktree registered inside the container looks broken outside — and a
        stray `git worktree prune` on the host can drop its registration.
        """
        if not (self.worktree / ".git").exists():
            return False
        probe = subprocess.run(
            ["git", "-C", str(self.worktree), "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return probe.returncode == 0

    def _ensure_worktree(self) -> None:
        if self._worktree_is_usable():
            return
        if self.worktree.exists():
            log.warning("helpers worktree unusable; recreating it")
            subprocess.run(
                ["git", "-C", str(self.repo), "worktree", "remove", "--force", str(self.worktree)],
                capture_output=True,
                text=True,
                timeout=60,
            )
        try:
            add_worktree(self.repo, self.worktree, self.config.dev.base_branch)
        except Exception as exc:  # noqa: BLE001
            log.warning("helpers worktree unavailable (%s); using data dir", exc)
            ensure_dir(self.worktree)
            # make it a plain dir clone of the repo? fall back to no-git helpers
            self.worktree = Path(self.config.data_path) / "agent-workspace" / "helpers-worktree"

    async def __aenter__(self):
        return self._tools()

    async def __aexit__(self, *exc):
        return None

    def _helper_path(self, name: str) -> Path:
        safe = name.strip().replace("/", "_").replace("\\", "_")
        if not safe.endswith(".py"):
            safe += ".py"
        return self.helpers_dir / safe

    def _run_harness(self, code: str) -> str:
        exe = shutil.which("browser-harness")
        cmd = [exe] if exe else [sys.executable, "-m", "browser_harness.run"]
        env = {k: v for k, v in os.environ.items() if not _SECRET_ENV_RE.search(k)}
        try:
            res = subprocess.run(
                cmd, input=code, capture_output=True, text=True, timeout=300,
                cwd=str(self.helpers_dir), env=env,
            )
        except subprocess.TimeoutExpired:
            return "[timeout] browser-harness exceeded 300s"
        out = (res.stdout or "") + (("\n[stderr]\n" + res.stderr) if res.stderr.strip() else "")
        return out[-_MAX_OUTPUT:] or "(no output)"

    def _fresh_screenshot(self, started_epoch: float) -> Path | None:
        """Newest PNG the harness wrote during this run (harness cwd = helpers
        dir, so a relative `capture_screenshot('shot.png')` lands there)."""
        newest: tuple[float, Path] | None = None
        for path in self.helpers_dir.glob("*.png"):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime >= started_epoch and (newest is None or mtime > newest[0]):
                newest = (mtime, path)
        return newest[1] if newest else None

    def _tools(self) -> list[Tool]:
        async def browser_exec(p: BrowserCodeParams):
            if _FORBIDDEN_CODE.search(p.code):
                return _fail(
                    "refusé — browser(code) pilote Chrome : jamais de git ni de commande "
                    "système hors browser-harness. Pour modifier le dépôt, écris au "
                    "codeur (send_message to='coder')."
                )
            started = time.time()
            text = await asyncio.to_thread(self._run_harness, _HARNESS_GUARD + p.code)
            shot = self._fresh_screenshot(started)
            if shot is None and self.config.agents.force_vision:
                # vision on: every browser step arrives with a page capture.
                # The second run is passive (Page.captureScreenshot never
                # disturbs the page), and only fires when the step produced
                # no capture of its own.
                await asyncio.to_thread(
                    self._run_harness, "capture_screenshot('shot.png', max_dim=1800)"
                )
                shot = self._fresh_screenshot(started)
            if shot is None:
                return _ok(text)
            png = shot.read_bytes()
            shot.unlink(missing_ok=True)  # consumed: no re-attach on the next step
            log.info(
                "vision: capture %s (%.0f ko) attachée au résultat",
                shot.name,
                len(png) / 1024,
            )
            return ToolResult(
                content=[text or "(no output)", ImageContentBlock(data=png)],
                metadata=ToolUseCountMetadata(),
            )

        async def list_exec(_: EmptyParams):
            names = sorted(f.name for f in self.helpers_dir.glob("*.py"))
            return _ok("\n".join(names) or "(no helper yet)")

        async def read_exec(p: HelperNameParams):
            path = self._helper_path(p.name)
            if not path.is_file():
                return _fail(f"no helper {p.name}")
            text = path.read_text(encoding="utf-8")[:4000]
            return _ok(text)

        async def write_exec(p: WriteHelperParams):
            atomic_write_text(self._helper_path(p.name), p.code)
            return _ok(f"wrote helper {p.name}")

        async def publish_exec(p: PublishParams):
            if not self.token:
                return _fail("no GitHub token (vault github_token) — cannot publish helpers")
            branch = f"agent/harness-helpers-{datetime.now():%Y%m%d-%H%M%S}"
            try:
                self.git.start_branch(branch)
                files = self.git.changed_files()
                keep = [f for f in files if f.replace("\\", "/").startswith("harness/helpers/")]
                if not keep:
                    return _ok("no helper changes to publish")
                self.git.stage(keep)
                self.git.commit(p.summary)
                self.git.push(branch)
                url = self.git.open_pr(
                    title=f"harness helpers: {p.summary[:60]}",
                    body=p.summary,
                    head=branch,
                    base=self.config.dev.base_branch,
                    repo=self.config.dev.github_repo,
                )
            except GitError as exc:
                return _fail(str(exc))
            return _ok(f"helpers published: {url}")

        async def send_exec(p: SendMessageParams):
            if self.task_id is None:
                return _fail(
                    "aucune tâche ouverte : impossible d'écrire dans une boîte de messages"
                )
            try:
                mid = self.mailbox.post("browser", p.to, p.body, self.task_id)
            except ValueError as exc:
                return _fail(str(exc))
            return _ok(f"message #{mid} envoyé (tâche #{self.task_id})")

        async def remember_exec(p: RememberParams):
            if p.key in _RESERVED_VAULT_KEYS:
                return _fail(f"'{p.key}' is reserved; ask the operator instead")
            try:
                Vault(self.config.vault_file).set(p.key, p.value)
            except Exception as exc:  # noqa: BLE001
                return _fail(f"vault write failed: {exc}")
            return _ok(f"stored '{p.key}' in the vault")

        return [
            Tool(name="browser", description="Run Python against Chrome via browser-harness.",
                 parameters=BrowserCodeParams, executor=browser_exec),
            Tool(name="list_helpers", description="List your helper files.",
                 parameters=EmptyParams, executor=list_exec),
            Tool(name="read_helper", description="Read a helper file.",
                 parameters=HelperNameParams, executor=read_exec),
            Tool(name="write_helper", description="Write/replace a helper file.",
                 parameters=WriteHelperParams, executor=write_exec),
            Tool(name="publish_helpers", description="Commit+push helpers and open a PR.",
                 parameters=PublishParams, executor=publish_exec),
            Tool(name="remember", description="Store a secret in the encrypted vault.",
                 parameters=RememberParams, executor=remember_exec),
            Tool(name="send_message", description="Message the coder agent.",
                 parameters=SendMessageParams, executor=send_exec),
        ]

async def run_browser_agent(
    config: Config,
    task: str,
    *,
    mailbox: Mailbox,
    journal: Journal | None = None,
    vault_get=None,
    task_id: int | None = None,
    max_turns: int | None = None,
) -> AgentOutcome:
    from mnemosyne.agents.session_cache import cache_base_dir, persist_session

    cache_base_dir(config)  # sessions persistantes : le cache vit sur le volume data
    client = build_agent_client(config, session="browser-agent", vault_get=vault_get)
    token = (vault_get("github_token") if vault_get else None) or os.environ.get("GITHUB_TOKEN")
    provider = BrowserAgentToolProvider(
        config, mailbox, token=token, journal=journal, task_id=task_id
    )
    skills = _load_skills(provider.repo)
    agent = Agent(
        client=client,
        name="browser_agent",
        system_prompt=load_prompt(
            provider.repo / "agents" / "browser.md",
            fallback=_FALLBACK,
            name=config.identity.name,
            disclosure=disclosure(config.identity),
            skills=skills,
        ),
        tools=[watch_provider(provider, provider.progress, "navigateur")],
        max_turns=max_turns or config.agents.max_turns,
    )
    out_dir = config.root / config.agents.output_dir
    ensure_dir(out_dir)
    # persistent session: resume=True reopens the same history at every
    # activation of this task; clear_cache_on_success=False keeps it for the
    # next ping-pong hop (the supervisor deletes it when the task closes)
    async with agent.session(
        output_dir=str(out_dir),
        cache_on_interrupt=True,
        resume=True,
        clear_cache_on_success=False,
    ) as session:
        finish, history, _metadata = await session.run(task)
    persist_session(config, agent, "browser")  # le finish doit aussi laisser un cache
    usage = client.usage.summary()
    # one generation per turn: the usage counter is the reliable turn count
    turns = int(usage.get("calls") or 0) or len(history)
    log.info("browser agent usage: %s (tours=%d)", usage, turns)
    summary = finish_text(finish)
    if journal:
        journal.append(f"navigateur usage: {usage}", source="browser")
        if summary:
            journal.append(f"navigateur — {summary}", source="browser")
    return AgentOutcome(finish=summary, turns=turns, outcome={"usage": usage})
