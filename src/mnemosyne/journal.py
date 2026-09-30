"""Daily markdown journal + operator steering channel.

The agent writes one markdown file per day (`journal/YYYY-MM-DD.md`). The operator
steers it through two plain files it can edit by hand:

* `control/directives.md` — standing instructions, re-read on every start;
* `control/inbox.md`      — one-off messages, consumed and acknowledged.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from pathlib import Path

from mnemosyne.logger import get_logger
from mnemosyne.util import ensure_dir

log = get_logger("journal")

_SAFE_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _today() -> date:
    return datetime.now().date()


def _stamp(when: datetime | None = None) -> str:
    # Full date + time: every journal entry is timestamped.
    return (when or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")


def _safe(text: str) -> str:
    return _SAFE_RE.sub("_", text).strip("_") or "unknown"


class Journal:
    def __init__(self, root: str | Path):
        self.dir = Path(root)
        ensure_dir(self.dir)

    def path_for(self, day: date | None = None) -> Path:
        return self.dir / f"{(day or _today()).isoformat()}.md"

    def append(
        self,
        text: str,
        *,
        level: str = "info",
        source: str = "heartbeat",
        when: datetime | None = None,
    ) -> None:
        path = self.path_for()
        if not path.exists():
            header = f"# mnemosyne — journal {_today().isoformat()}\n\n"
            path.write_text(header, encoding="utf-8")
        line = f"- {_stamp(when)} [{level}] {source}: {text}\n"
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError as exc:  # journal must never crash the heartbeat
            log.warning("cannot write journal: %s", exc)

    def read(self, day: date | None = None) -> str:
        path = self.path_for(day)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def latest(self) -> Path | None:
        files = sorted(self.dir.glob("*.md"))
        return files[-1] if files else None

    # ── per-service journals (one md per provider the agent wants to access) ──
    @property
    def services_dir(self) -> Path:
        return self.dir / "services"

    def service_path(self, service_id: str) -> Path:
        return self.services_dir / f"{_safe(service_id)}.md"

    def append_service(
        self,
        service_id: str,
        text: str,
        *,
        title: str | None = None,
        level: str = "info",
        source: str = "agent",
        when: datetime | None = None,
    ) -> None:
        path = self.service_path(service_id)
        ensure_dir(path.parent)
        if not path.exists():
            header = f"# Journal de service — {title or service_id}\n\n"
            path.write_text(header, encoding="utf-8")
        line = f"- {_stamp(when)} [{level}] {source}: {text}\n"
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError as exc:  # journal must never crash the heartbeat
            log.warning("cannot write service journal: %s", exc)

    def read_service(self, service_id: str) -> str:
        path = self.service_path(service_id)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def list_services(self) -> list[str]:
        if not self.services_dir.exists():
            return []
        return sorted(p.stem for p in self.services_dir.glob("*.md"))


class Control:
    """Operator → agent channel: directives (standing) + inbox (one-off)."""

    def __init__(self, control_dir: str | Path):
        self.dir = Path(control_dir)
        ensure_dir(self.dir)
        self.directives_path = self.dir / "directives.md"
        self.inbox_path = self.dir / "inbox.md"
        self._idx_path = self.dir / ".inbox.idx"
        for p, header in (
            (
                self.directives_path,
                "# Directives\n\n<!-- Standing instructions for the agent. -->\n",
            ),
            (
                self.inbox_path,
                "# Inbox\n\n"
                "<!-- One-off messages. Blocks start with a line `## <timestamp>`. -->\n",
            ),
        ):
            if not p.exists():
                p.write_text(header, encoding="utf-8")

    # ── directives ───────────────────────────────────────────────────────
    def directives(self) -> str:
        if not self.directives_path.exists():
            return ""
        body = self.directives_path.read_text(encoding="utf-8")
        keep = [
            ln
            for ln in body.splitlines()
            if ln.strip()
            and not ln.lstrip().startswith(("#", "<!--", "-->"))
        ]
        return "\n".join(keep).strip()

    # ── inbox ────────────────────────────────────────────────────────────
    def post(self, text: str) -> None:
        stamp = datetime.now().isoformat(timespec="seconds")
        with open(self.inbox_path, "a", encoding="utf-8") as fh:
            fh.write(f"\n## {stamp}\n{text.strip()}\n")

    def _read_index(self) -> int:
        try:
            return int(self._idx_path.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            return 0

    def _write_index(self, value: int) -> None:
        tmp = self._idx_path.with_name(self._idx_path.name + f".{os.getpid()}.tmp")
        tmp.write_text(str(value), encoding="utf-8")
        os.replace(tmp, self._idx_path)

    def _blocks(self) -> list[str]:
        if not self.inbox_path.exists():
            return []
        body = self.inbox_path.read_text(encoding="utf-8")
        blocks: list[str] = []
        current: list[str] | None = None  # None until the first `## ` header
        for line in body.splitlines():
            if line.startswith("## "):
                if current:
                    blocks.append("\n".join(current).strip())
                current = []
            elif current is not None:
                current.append(line)
        if current:
            blocks.append("\n".join(current).strip())
        return [b for b in blocks if b]

    def pending(self) -> list[str]:
        blocks = self._blocks()
        return blocks[self._read_index():]

    def consume(self) -> list[str]:
        blocks = self._blocks()
        pending = blocks[self._read_index():]
        if pending:
            self._write_index(len(blocks))
        return pending
