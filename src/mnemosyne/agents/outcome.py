"""Shared result type for one agent turn."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentOutcome:
    finish: str | None
    outcome: dict = field(default_factory=dict)
