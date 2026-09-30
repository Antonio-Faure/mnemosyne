"""Hard guardrails for the self-extension (developer) agent.

These are enforced in code, not in the prompt: the agent can only write to an
allowlisted set of paths, and can never run destructive git operations.
"""

from __future__ import annotations

#: git subcommands/tokens the agent may never use
_FORBIDDEN_GIT_TOKENS = {
    "--force",
    "-f",
    "--hard",
    "--delete",
    "-D",
    "-d",
    "reset",
    "clean",
    "rebase",
    "filter-branch",
    "gc",
    "rm",
    "restore",
}
_FORBIDDEN_GIT_SUBSTR = ("--force", "--hard", "--delete")


class DevGuardError(PermissionError):
    pass


def normalize_rel(path: str) -> str:
    """Clean a repo-relative path, rejecting absolute paths and escapes."""
    raw = str(path).replace("\\", "/").strip()
    if not raw:
        raise DevGuardError("empty path")
    if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):
        raise DevGuardError(f"absolute paths are not allowed: {path}")
    parts: list[str] = []
    for part in raw.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise DevGuardError(f"path escapes the repository: {path}")
            parts.pop()
        else:
            parts.append(part)
    if not parts:
        raise DevGuardError(f"invalid path: {path}")
    return "/".join(parts)


def _hits(rel: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        p = pattern.rstrip("/")
        if rel == p or rel.startswith(p + "/"):
            return True
    return False


def is_allowed(path: str, allow: list[str], deny: list[str]) -> bool:
    rel = normalize_rel(path)
    # absolute hard rules, independent of configuration
    if rel == ".env" or rel.endswith(".env") or rel.endswith(".key") or rel.endswith(".enc"):
        return False
    if _hits(rel, deny):
        return False
    return _hits(rel, allow)


def check_writable(path: str, allow: list[str], deny: list[str]) -> str:
    rel = normalize_rel(path)
    if not is_allowed(rel, allow, deny):
        raise DevGuardError(
            f"writing '{rel}' is not allowed (only {allow}); refusing."
        )
    return rel


def check_git_args(args: list[str]) -> None:
    """Raise if the git command line contains a destructive operation."""
    joined = " ".join(args)
    if any(token in joined for token in _FORBIDDEN_GIT_SUBSTR):
        raise DevGuardError(f"refusing destructive git operation: {joined}")
    for arg in args:
        if arg in _FORBIDDEN_GIT_TOKENS:
            raise DevGuardError(f"refusing destructive git operation: {arg}")
