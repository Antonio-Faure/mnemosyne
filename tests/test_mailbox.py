import pytest

from mnemosyne.agents.mailbox import Mailbox
from mnemosyne.db import Database


def _mailbox(config) -> tuple[Database, Mailbox]:
    db = Database(config.db_file())
    return db, Mailbox(db)


def test_post_and_next(config):
    db, mb = _mailbox(config)
    mid = mb.post("operator", "coder", "connect europeana")
    msg = mb.next_for("coder")
    assert msg is not None and msg["id"] == mid and msg["status"] == "pending"
    assert mb.next_for("browser") is None
    db.close()


def test_mark_handled(config):
    db, mb = _mailbox(config)
    mid = mb.post("coder", "browser", "need the europeana api key")
    mb.mark(mid, "handled", "done")
    assert mb.next_for("browser") is None
    history = mb.history()
    assert history[-1]["status"] == "handled" and history[-1]["note"] == "done"
    db.close()


def test_invalid_recipient(config):
    db, mb = _mailbox(config)
    with pytest.raises(ValueError):
        mb.post("coder", "nobody", "hello")
    db.close()


def test_other_and_pending(config):
    db, mb = _mailbox(config)
    assert Mailbox.other("coder") == "browser"
    mb.post("operator", "browser", "go to x")
    assert mb.pending_recipients() == ["browser"]
    db.close()
