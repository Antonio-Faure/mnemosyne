"""Browser agent (Stirrup) — drives the real Chrome through browser-harness.

Owns everything web: navigation, warmup, precise research, emails, forms,
obtaining access/keys, AND improving its own harness (helpers) and making videos.
It cannot edit the product code; it reports to the coder through the mailbox.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel, Field
from stirrup import Agent
from stirrup.core.models import EmptyParams, Tool, ToolProvider, ToolResult, ToolUseCountMetadata

from mnemosyne.agents.mailbox import Mailbox
from mnemosyne.agents.onboarding import AgentOutcome
from mnemosyne.browser.stirrup_client import build_agent_client
from mnemosyne.config import Config
from mnemosyne.identity import disclosure
from mnemosyne.journal import Journal
from mnemosyne.logger import get_logger
from mnemosyne.util import atomic_write_text, ensure_dir, finish_text

log = get_logger("browser_agent")

_MAX_OUTPUT = 4000

_SYSTEM = """You are {name}, the BROWSER agent of an autonomous system that
aggregates historical image archives. You own everything web-related: navigating
sites, warming up the account, precise research, sending emails, filling forms,
obtaining access/API keys — and improving your OWN harness (helpers) and making
videos. You act in your own name and are transparent: {disclosure}

TOOLS:
- browser(code): run Python against the real Chrome, via browser-harness. Helpers
  are pre-imported, e.g. goto_url(url), scroll(x,y,dy), type_text(...),
  click_at_xy(...), fill_input(...), upload_file(...), new_tab(...), switch_tab(
  ...), list_tabs(), capture_screenshot(), wait(s), wait_for_load(),
  start_recording(name=None,title=None), stop_recording(), recording_dir(),
  js("..."), cdp("Method", key=val...). Print what you need to see.
- list_helpers() / read_helper(name) / write_helper(name, code): your helper
  toolbox (keep reusable functions there; they persist).
- send_message(to, body): message the OTHER agent (to="coder") or the operator
  (to="operator"). Do this when you need code/decisions or when you finish.
- task_done(summary): finish.

TO VIDEO: start_recording() → do the session → stop_recording() → then use
browser() to run `video init <dir>` / write edit-brief.json / `video review` /
`video export --reviewed` (plan 2-5 items, privacy.reviewedFiles, narration only
when it changes).

RULES: never edit product code (you only write helpers). Never put secrets in a
message — store them in the vault and send a reference. If blocked by a captcha
you cannot pass, ask the operator. Keep going until the task is done, then
task_done with a factual summary."""


class BrowserCodeParams(BaseModel):
    code: str = Field(description="Python code executed against Chrome via browser-harness")


class HelperNameParams(BaseModel):
    name: str = Field(description="Helper file name, e.g. 'europeana.py'")


class WriteHelperParams(BaseModel):
    name: str = Field(description="Helper file name, e.g. 'europeana.py'")
    code: str = Field(description="Full Python content of the helper")


class SendMessageParams(BaseModel):
    to: str = Field(description="Recipient: 'coder' or 'operator'")
    body: str = Field(description="Message (never include secrets — use vault references)")


class DoneParams(BaseModel):
    summary: str = Field(description="Short factual summary of what was done")


def _ok(content: str) -> ToolResult[ToolUseCountMetadata]:
    return ToolResult(content=content, metadata=ToolUseCountMetadata())


def _fail(content: str) -> ToolResult[ToolUseCountMetadata]:
    return ToolResult(content=content, success=False, metadata=ToolUseCountMetadata())


class BrowserAgentToolProvider(ToolProvider):
    def __init__(self, config: Config, mailbox: Mailbox, journal: Journal | None = None):
        self.config = config
        self.mailbox = mailbox
        self.journal = journal
        self.helpers_dir = Path(config.data_path) / "agent-workspace" / "helpers"
        ensure_dir(self.helpers_dir)
        self.finish: str | None = None

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
        try:
            res = subprocess.run(
                cmd, input=code, capture_output=True, text=True, timeout=300,
                cwd=str(self.helpers_dir),
            )
        except subprocess.TimeoutExpired:
            return "[timeout] browser-harness exceeded 300s"
        out = (res.stdout or "") + (("\n[stderr]\n" + res.stderr) if res.stderr.strip() else "")
        return out[-_MAX_OUTPUT:] or "(no output)"

    def _tools(self) -> list[Tool]:
        async def browser_exec(p: BrowserCodeParams):
            out = await asyncio.to_thread(self._run_harness, p.code)
            return _ok(out)

        async def list_exec(_: EmptyParams):
            names = sorted(f.name for f in self.helpers_dir.glob("*.py"))
            return _ok("\n".join(names) or "(no helper yet)")

        async def read_exec(p: HelperNameParams):
            path = self._helper_path(p.name)
            if not path.is_file():
                return _fail(f"no helper {p.name}")
            return _ok(path.read_text(encoding="utf-8")[:4000])

        async def write_exec(p: WriteHelperParams):
            path = self._helper_path(p.name)
            atomic_write_text(path, p.code)
            return _ok(f"wrote helper {path.name}")

        async def send_exec(p: SendMessageParams):
            try:
                mid = self.mailbox.post("browser", p.to, p.body)
            except ValueError as exc:
                return _fail(str(exc))
            return _ok(f"message #{mid} sent to {p.to}")

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
            Tool(name="send_message", description="Message the coder or the operator.",
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
    provider = BrowserAgentToolProvider(config, mailbox, journal=journal)
    agent = Agent(
        client=client,
        name="browser_agent",
        system_prompt=_SYSTEM.format(
            name=config.identity.name, disclosure=disclosure(config.identity)
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
