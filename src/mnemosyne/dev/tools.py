"""Stirrup tools for the self-extension (developer) agent.

No browser here: the agent edits files in its own repo, runs lint/tests, commits
on an `agent/*` branch, pushes and opens a pull request. Writes are allowlisted
and destructive git operations are refused (see `dev/guard.py`).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import httpx
from pydantic import BaseModel, Field
from stirrup.core.models import EmptyParams, Tool, ToolProvider, ToolResult, ToolUseCountMetadata

from mnemosyne.config import DevConfig
from mnemosyne.dev.git_ops import Git, GitError
from mnemosyne.dev.guard import DevGuardError, check_writable
from mnemosyne.journal import Journal
from mnemosyne.notify import Notifier
from mnemosyne.util import atomic_write_text


class PathParam(BaseModel):
    path: str = Field(description="Repo-relative path")


class DirParam(BaseModel):
    directory: str = Field(default="", description="Repo-relative directory ('' = repo root)")


class GrepParam(BaseModel):
    pattern: str = Field(description="Regex to search for")
    path: str = Field(default=".", description="Repo-relative file or directory")


class FetchParam(BaseModel):
    url: str = Field(description="URL to fetch (API docs, schema…)")


class WriteParam(BaseModel):
    path: str = Field(description="Repo-relative path (allowlisted only)")
    content: str = Field(description="Full file content to write")


class BranchParam(BaseModel):
    name: str = Field(description="Short branch slug, e.g. 'europeana-connector'")


class CommitParam(BaseModel):
    message: str = Field(description="Commit message")


class PrParam(BaseModel):
    title: str = Field(description="Pull request title")
    body: str = Field(default="", description="Pull request body")


class DoneParam(BaseModel):
    summary: str = Field(description="What was done")


class QuestionParam(BaseModel):
    message: str = Field(description="Question for the operator (Telegram)")


def _ok(content: str) -> ToolResult[ToolUseCountMetadata]:
    return ToolResult(content=content, metadata=ToolUseCountMetadata())


def _fail(content: str) -> ToolResult[ToolUseCountMetadata]:
    return ToolResult(content=content, success=False, metadata=ToolUseCountMetadata())


class DevToolProvider(ToolProvider):
    def __init__(
        self,
        repo: Path,
        config: DevConfig,
        token: str | None,
        *,
        notifier: Notifier | None = None,
        journal: Journal | None = None,
    ):
        self.repo = Path(repo)
        self.config = config
        self.token = token
        self.git = Git(self.repo, self.token)
        self.notifier = notifier
        self.journal = journal
        self.branch: str | None = None
        self.finish: str | None = None

    async def __aenter__(self):
        return self._tools()

    async def __aexit__(self, *exc):
        return None

    # ── helpers ──────────────────────────────────────────────────────────
    def _abs(self, rel: str) -> Path:
        return (self.repo / rel).resolve()

    def _check_inside(self, rel: str) -> Path:
        target = self._abs(rel)
        if not str(target).startswith(str(self.repo.resolve())):
            raise DevGuardError(f"path outside the repository: {rel}")
        return target

    def _run_cmd(self, args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
        return subprocess.run(
            args, cwd=self.repo, capture_output=True, text=True, timeout=timeout
        )

    async def _escalate(self, message: str) -> None:
        # a git/write failure is not a question the operator can answer — alert,
        # don't ask. (The explicit `ask_operator` tool still asks.)
        if self.notifier and self.notifier.enabled:
            await self.notifier.send(message, "warn")
        if self.journal:
            self.journal.append(message, level="warn", source="dev")

    # ── tools ────────────────────────────────────────────────────────────
    def _tools(self) -> list[Tool]:
        async def list_exec(p: DirParam):
            base = self._check_inside(p.directory or ".")
            if not base.is_dir():
                return _fail(f"not a directory: {p.directory}")
            lines = []
            for child in sorted(base.iterdir()):
                if child.name in {".git", "__pycache__", "node_modules", ".venv", "data"}:
                    continue
                rel = child.relative_to(self.repo)
                lines.append(f"{'d' if child.is_dir() else 'f'} {rel}")
            return _ok("\n".join(lines[: self.config.list_max_entries]) or "(empty)")

        async def read_exec(p: PathParam):
            target = self._check_inside(p.path)
            if not target.is_file():
                return _fail(f"no such file: {p.path}")
            try:
                text = target.read_text(encoding="utf-8")
            except OSError as exc:
                return _fail(f"read failed: {exc}")
            cap = self.config.read_max_chars
            return _ok(text[:cap] + ("\n…(truncated)" if len(text) > cap else ""))

        async def grep_exec(p: GrepParam):
            # never scan .venv/.git/data: huge and irrelevant
            res = self._run_cmd(
                [
                    "grep",
                    "-rnI",
                    "-m",
                    "3",
                    "--exclude-dir=.venv",
                    "--exclude-dir=.git",
                    "--exclude-dir=data",
                    "--exclude-dir=node_modules",
                    "--exclude-dir=__pycache__",
                    "--exclude-dir=.pytest_cache",
                    "--exclude-dir=.ruff_cache",
                    p.pattern,
                    p.path,
                ]
            )
            if res.returncode not in (0, 1):
                return _fail(f"grep failed: {res.stderr[:200]}")
            return _ok(res.stdout[: self.config.grep_max_chars] or "(no match)")

        async def fetch_exec(p: FetchParam):
            try:
                async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                    resp = await client.get(p.url)
                resp.raise_for_status()
                return _ok(resp.text[: self.config.fetch_max_chars])
            except httpx.HTTPError as exc:
                return _fail(f"fetch failed: {exc}")

        async def write_exec(p: WriteParam):
            try:
                rel = check_writable(p.path, self.config.allow, self.config.deny)
            except DevGuardError as exc:
                await self._escalate(f"self-dev write refused: {exc}")
                return _fail(str(exc))
            target = self._check_inside(rel)
            atomic_write_text(target, p.content)
            return _ok(f"wrote {rel}")

        async def lint_exec(_: EmptyParams):
            res = self._run_cmd([sys.executable, "-m", "ruff", "check", "."])
            body = (res.stdout + res.stderr)[:3000]
            return _ok(f"ruff exit {res.returncode}\n{body}") if res.returncode == 0 else _fail(
                f"ruff exit {res.returncode}\n{body}"
            )

        async def test_exec(_: EmptyParams):
            res = self._run_cmd([sys.executable, "-m", "pytest", "-q"], timeout=600)
            body = (res.stdout + res.stderr)[-3000:]
            return _ok(f"pytest exit {res.returncode}\n{body}") if res.returncode == 0 else _fail(
                f"pytest exit {res.returncode}\n{body}"
            )

        async def branch_exec(p: BranchParam):
            name = p.name if p.name.startswith(self.config.branch_prefix) else (
                self.config.branch_prefix + p.name
            )
            self.git.start_branch(name)
            self.branch = name
            return _ok(f"on branch {name}")

        async def status_exec(_: EmptyParams):
            files = self.git.changed_files()
            return _ok("\n".join(files) or "(clean)")

        async def commit_exec(p: CommitParam):
            if not self.branch:
                return _fail("start a branch first (start_branch)")
            try:
                files = self.git.changed_files()
                bad = [f for f in files if not _writable(f, self.config)]
                if bad:
                    return _fail(f"refusing to commit non-allowlisted files: {bad}")
                if not files:
                    return _ok("nothing to commit")
                self.git.stage(files)
                sha = self.git.commit(p.message)
            except (GitError, DevGuardError) as exc:
                return _fail(str(exc))
            return _ok(f"committed {sha[:10]} ({len(files)} files)")

        async def push_exec(_: EmptyParams):
            if not self.branch or not self.branch.startswith(self.config.branch_prefix):
                return _fail("not on an agent/* branch")
            try:
                self.git.push(self.branch)
            except GitError as exc:
                await self._escalate(f"self-dev push failed: {exc}")
                return _fail(str(exc))
            return _ok(f"pushed {self.branch}")

        async def pr_exec(p: PrParam):
            if not self.branch:
                return _fail("no branch")
            try:
                url = self.git.open_pr(
                    title=p.title,
                    body=p.body,
                    head=self.branch,
                    base=self.config.base_branch,
                    repo=self.config.github_repo,
                )
            except GitError as exc:
                await self._escalate(f"self-dev PR failed: {exc}")
                return _fail(str(exc))
            if self.notifier and self.notifier.enabled:
                await self.notifier.send(f"PR ouverte : {url}", "info")
            if self.journal:
                self.journal.append(f"self-dev PR : {url}", source="dev")
            return _ok(f"PR opened: {url}")

        async def ask_exec(p: QuestionParam):
            await self._escalate(p.message)
            return _ok("question sent to the operator on Telegram")

        async def done_exec(p: DoneParam):
            self.finish = p.summary
            return _ok("done")

        return [
            Tool(name="list_files", description="List files in a directory.",
                 parameters=DirParam, executor=list_exec),
            Tool(name="read_file", description="Read a repo file.",
                 parameters=PathParam, executor=read_exec),
            Tool(name="grep", description="Search the repo.",
                 parameters=GrepParam, executor=grep_exec),
            Tool(name="fetch_url", description="Fetch a URL (API docs, schema).",
                 parameters=FetchParam, executor=fetch_exec),
            Tool(name="write_file", description="Write a file (allowlisted paths only).",
                 parameters=WriteParam, executor=write_exec),
            Tool(name="run_lint", description="Run ruff.",
                 parameters=EmptyParams, executor=lint_exec),
            Tool(name="run_tests", description="Run pytest.",
                 parameters=EmptyParams, executor=test_exec),
            Tool(name="start_branch", description="Create/switch to an agent branch.",
                 parameters=BranchParam, executor=branch_exec),
            Tool(name="git_status", description="List changed files.",
                 parameters=EmptyParams, executor=status_exec),
            Tool(name="commit", description="Commit allowlisted changes.",
                 parameters=CommitParam, executor=commit_exec),
            Tool(name="push", description="Push the current agent branch.",
                 parameters=EmptyParams, executor=push_exec),
            Tool(name="open_pr", description="Open a pull request for the branch.",
                 parameters=PrParam, executor=pr_exec),
            Tool(name="ask_operator", description="Ask the operator on Telegram.",
                 parameters=QuestionParam, executor=ask_exec),
            Tool(name="task_done", description="Finish.",
                 parameters=DoneParam, executor=done_exec),
        ]


def _writable(rel: str, config: DevConfig) -> bool:
    from mnemosyne.dev.guard import is_allowed

    try:
        return is_allowed(rel, config.allow, config.deny)
    except DevGuardError:
        return False
