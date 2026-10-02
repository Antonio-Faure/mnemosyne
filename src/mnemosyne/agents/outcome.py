"""Shared result type for one agent turn (browser + coder)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentOutcome:
    finish: str | None
    branch: str | None = None
    turns: int = 0
    outcome: dict = field(default_factory=dict)
