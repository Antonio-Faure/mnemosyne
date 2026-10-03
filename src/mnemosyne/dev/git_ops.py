"""Git operations for the developer agent, with credentials kept out of argv."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import httpx

from mnemosyne.dev.guard import check_git_args
from mnemosyne.logger import get_logger

log = get_logger("dev.git")

_CRED_HELPER = "!f() { echo username=x-access-token; echo password=$MNEMOSYNE_GIT_TOKEN; }; f"


class GitError(RuntimeError):
    pass


@dataclass
class Git:
    repo: Path
    token: str | None = None
    remote: str = "origin"
    author_name: str = "mnemosyne agent"
    author_email: str = "agent@mnemosyne.local"

    def run(
        self, args: list[str], *, check: bool = True, with_creds: bool = False
    ) -> subprocess.CompletedProcess:
        check_git_args(args)
        cmd = ["git"]
        if with_creds and self.token:
            # token passed via env + credential helper, never in argv
            cmd += ["-c", f"credential.helper={_CRED_HELPER}"]
        cmd += [
            "-c",
            f"user.name={self.author_name}",
            "-c",
            f"user.email={self.author_email}",
            *args,
        ]
        env = os.environ.copy()
        if self.token:
            env["MNEMOSYNE_GIT_TOKEN"] = self.token
        res = subprocess.run(cmd, cwd=self.repo, env=env, capture_output=True, text=True)
        if check and res.returncode != 0:
            detail = (res.stderr or res.stdout).strip()[:300]
            raise GitError(f"git {' '.join(args)} failed: {detail}")
        return res

    def start_branch(self, name: str) -> str:
        self.run(["checkout", "-B", name])
        return name

    def changed_files(self) -> list[str]:
        out = self.run(["status", "--porcelain"]).stdout
        files = []
        for line in out.splitlines():
            path = line[3:].strip().strip('"')
            if " -> " in path:  # renames
                path = path.split(" -> ")[-1]
            if path:
                files.append(path)
        return files

    def stage(self, paths: list[str]) -> None:
        if not paths:
            raise GitError("nothing to stage")
        self.run(["add", "--", *paths])

    def commit(self, message: str) -> str:
        self.run(["commit", "-m", message])
        return self.run(["rev-parse", "HEAD"]).stdout.strip()

    def push(self, branch: str) -> None:
        self.run(["push", "-u", self.remote, branch], with_creds=True)

    def open_pr(self, *, title: str, body: str, head: str, base: str, repo: str) -> str:
        if not self.token:
            raise GitError("no GitHub token to open a pull request")
        resp = httpx.post(
            f"https://api.github.com/repos/{repo}/pulls",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
            },
            json={"title": title, "body": body, "head": head, "base": base},
            timeout=30,
        )
        if resp.status_code >= 300:
            raise GitError(f"PR creation failed ({resp.status_code}): {resp.text[:200]}")
        return resp.json()["html_url"]
