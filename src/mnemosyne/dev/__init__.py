"""Self-extension (developer agent) — guardrails are import-light.

`mnemosyne.dev.agent` (which needs the `agent` extra: stirrup) is imported
lazily by the CLI, so importing the guard does not require stirrup.
"""

from mnemosyne.dev.guard import (
    DevGuardError,
    check_git_args,
    check_writable,
    is_allowed,
    normalize_rel,
)

__all__ = [
    "DevGuardError",
    "check_git_args",
    "check_writable",
    "is_allowed",
    "normalize_rel",
]
