import asyncio

from mnemosyne.config import DevConfig
from mnemosyne.dev.tools import CommitParam, DevToolProvider, PathParam


def _provider(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    return repo, DevToolProvider(repo, DevConfig(), None)


def _read_tool(provider):
    return {t.name: t for t in provider._tools()}["read_file"]


def test_read_file_pages_long_files(tmp_path):
    """A long file is served in offset pages — no need to slice it with grep."""
    repo, provider = _provider(tmp_path)
    text = "".join(f"line {i:04d}\n" for i in range(400))
    (repo / "src" / "big.py").write_text(text)

    tool = _read_tool(provider)
    first = asyncio.run(tool.executor(PathParam(path="src/big.py")))
    assert first.success
    assert "call read_file with offset=" in first.content
    offset = int(first.content.rsplit("offset=", 1)[1].split(" ")[0])
    assert offset == DevConfig().read_max_chars

    second = asyncio.run(tool.executor(PathParam(path="src/big.py", offset=offset)))
    assert second.success
    assert "call read_file with offset=" not in second.content
    assert (first.content.split("\n…(", 1)[0] + second.content) == text


def test_read_file_short_file_has_no_footer(tmp_path):
    repo, provider = _provider(tmp_path)
    (repo / "src" / "small.py").write_text("print('hi')\n")

    tool = _read_tool(provider)
    res = asyncio.run(tool.executor(PathParam(path="src/small.py")))
    assert res.success and res.content == "print('hi')\n"

    past = asyncio.run(tool.executor(PathParam(path="src/small.py", offset=999)))
    assert past.success and "past the end" in past.content


def test_commit_refuses_until_lint_and_tests_pass(tmp_path):
    """coder.md's hard rule, enforced in code: no commit without green checks."""
    repo, provider = _provider(tmp_path)
    provider.branch = "agent/x"
    tool = {t.name: t for t in provider._tools()}["commit"]

    res = asyncio.run(tool.executor(CommitParam(message="wip")))
    assert not res.success
    assert "run_lint and run_tests" in res.content


def test_coder_does_not_get_the_email_wait_tool(config, tmp_path):
    """Email belongs to the browser agent; the coder must not park on IMAP."""
    from mnemosyne.agents.mailbox import Mailbox
    from mnemosyne.db import Database

    db = Database(config.db_file())
    try:
        repo, _ = _provider(tmp_path)
        provider = DevToolProvider(
            repo, config.dev, None, mailbox=Mailbox(db), task_id=None
        )
        names = {tool.name for tool in provider._tools()}
        assert "wait_for_email" not in names
        assert "send_message" in names
        assert "ask_operator" in names
    finally:
        db.close()
