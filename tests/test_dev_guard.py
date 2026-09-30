import pytest

from mnemosyne.config import DevConfig
from mnemosyne.dev.guard import (
    DevGuardError,
    check_git_args,
    check_writable,
    is_allowed,
    normalize_rel,
)

ALLOW = DevConfig().allow
DENY = DevConfig().deny


def test_normalize_rejects_escapes_and_absolute():
    assert normalize_rel("config/sources/x.yaml") == "config/sources/x.yaml"
    assert normalize_rel("./a//b") == "a/b"
    with pytest.raises(DevGuardError):
        normalize_rel("/etc/passwd")
    with pytest.raises(DevGuardError):
        normalize_rel("../outside")
    with pytest.raises(DevGuardError):
        normalize_rel("a/../../outside")


def test_allowed_paths():
    assert is_allowed("config/sources/europeana.yaml", ALLOW, DENY)
    assert is_allowed("src/mnemosyne/sources/europeana.py", ALLOW, DENY)
    assert is_allowed("tests/test_europeana.py", ALLOW, DENY)
    assert is_allowed("docs/x.md", ALLOW, DENY)


def test_denied_paths_win():
    for path in (
        ".env",
        "vault/vault.enc",
        "src/mnemosyne/heartbeat/scheduler.py",
        "src/mnemosyne/dev/tools.py",
        "src/mnemosyne/agents/tools.py",
        "AGENTS.md",
        "pyproject.toml",
        "src/mnemosyne/sources/europeana.key",
    ):
        assert not is_allowed(path, ALLOW, DENY), path


def test_check_writable_raises():
    assert check_writable("config/sources/x.yaml", ALLOW, DENY)
    with pytest.raises(DevGuardError):
        check_writable("src/mnemosyne/heartbeat/scheduler.py", ALLOW, DENY)


def test_git_args_guard_blocks_destructive():
    for args in (
        ["push", "--force", "origin", "main"],
        ["push", "-f", "origin", "main"],
        ["reset", "--hard"],
        ["clean", "-fd"],
        ["branch", "-D", "x"],
        ["rm", "-r", "x"],
    ):
        with pytest.raises(DevGuardError):
            check_git_args(args)


def test_git_args_guard_allows_normal():
    for args in (
        ["checkout", "-B", "agent/europeana"],
        ["add", "--", "config/sources/x.yaml"],
        ["commit", "-m", "msg"],
        ["push", "-u", "origin", "agent/europeana"],
        ["rev-parse", "HEAD"],
    ):
        check_git_args(args)
