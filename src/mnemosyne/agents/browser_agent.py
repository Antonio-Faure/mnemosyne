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
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field
from stirrup import Agent
from stirrup.core.models import EmptyParams, Tool, ToolProvider, ToolResult, ToolUseCountMetadata

from mnemosyne.agents.mailbox import Mailbox
from mnemosyne.agents.outcome import AgentOutcome
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


class DoneParams(BaseModel):
    summary: str = Field(description="Short factual summary of what was done")


class RememberParams(BaseModel):
    key: str = Field(description="Vault key, e.g. 'europeana_api_key'")
    value: str = Field(description="Secret value to store (never sent in a message)")


#: vault entries only the operator may set
_RESERVED_VAULT_KEYS = frozenset({"github_token", "opencode_api_key"})

#: env vars never handed to the harness subprocess (secrets stay in our process)
_SECRET_ENV_RE = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)", re.I)


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
    ):
        self.config = config
        self.mailbox = mailbox
        self.journal = journal
        self.repo = Path(config.dev.repo_path or config.root)
        self.worktree = Path(config.data_path) / "agent-workspace" / "helpers-worktree"
        self._ensure_worktree()
        self.helpers_dir = self.worktree / "harness" / "helpers"
        ensure_dir(self.helpers_dir)
        self.token = token
        self.git = Git(self.worktree, token)
        self.finish: str | None = None

    def _ensure_worktree(self) -> None:
        if (self.worktree / ".git").exists():
            return
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

    def _tools(self) -> list[Tool]:
        async def browser_exec(p: BrowserCodeParams):
            return _ok(await asyncio.to_thread(self._run_harness, p.code))

        async def list_exec(_: EmptyParams):
            names = sorted(f.name for f in self.helpers_dir.glob("*.py"))
            return _ok("\n".join(names) or "(no helper yet)")

        async def read_exec(p: HelperNameParams):
            path = self._helper_path(p.name)
            if not path.is_file():
                return _fail(f"no helper {p.name}")
            return _ok(path.read_text(encoding="utf-8")[:4000])

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
            try:
                mid = self.mailbox.post("browser", p.to, p.body)
            except ValueError as exc:
                return _fail(str(exc))
            return _ok(f"message #{mid} sent to {p.to}")

        async def remember_exec(p: RememberParams):
            if p.key in _RESERVED_VAULT_KEYS:
                return _fail(f"'{p.key}' is reserved; ask the operator instead")
            try:
                Vault(self.config.vault_file).set(p.key, p.value)
            except Exception as exc:  # noqa: BLE001
                return _fail(f"vault write failed: {exc}")
            return _ok(f"stored '{p.key}' in the vault")

        async def done_exec(p: DoneParams):
            self.finish = p.summary
            if self.journal:
                self.journal.append(f"navigateur — {p.summary}", source="browser")
            return _ok("done")

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
            Tool(name="task_done", description="Finish with a factual summary.",
                 parameters=DoneParams, executor=done_exec),
        ]


async def run_browser_agent(
    config: Config,
    task: str,
    *,
    mailbox: Mailbox,
    journal: Journal | None = None,
    vault_get=None,
) -> AgentOutcome:
    client = build_agent_client(config, session="browser-agent", vault_get=vault_get)
    token = (vault_get("github_token") if vault_get else None) or os.environ.get("GITHUB_TOKEN")
    provider = BrowserAgentToolProvider(config, mailbox, token=token, journal=journal)
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
        tools=[provider],
        max_turns=config.agents.max_turns,
    )
    out_dir = config.root / config.agents.output_dir
    ensure_dir(out_dir)
    async with agent.session(output_dir=str(out_dir), cache_on_interrupt=True) as session:
        finish, _history, _metadata = await session.run(task)
    usage = client.usage.summary()
    log.info("browser agent usage: %s", usage)
    if journal:
        journal.append(f"navigateur usage: {usage}", source="browser")
    return AgentOutcome(
        finish=provider.finish or finish_text(finish), outcome={"usage": usage}
    )
