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


def test_operator_channel_is_disabled(config):
    db, mb = _mailbox(config)
    with pytest.raises(ValueError):
        mb.post("browser", "operator", "rapport")  # disabled for now
    with pytest.raises(ValueError):
        mb.post("coder", "coder", "self")  # no self-messages
    db.close()


def test_other_and_pending(config):
    db, mb = _mailbox(config)
    assert Mailbox.other("coder") == "browser"
    mb.post("operator", "browser", "go to x")
    assert mb.pending_recipients() == ["browser"]
    db.close()


def test_claim_is_single_writer(config):
    """A claimed message cannot be claimed twice, nor while a turn is running."""
    db, mb = _mailbox(config)
    other = Database(config.db_file())
    mid = mb.post("operator", "coder", "travail")
    claimed = mb.claim_for("coder", owner="a")
    assert claimed is not None and claimed["id"] == mid
    assert claimed["status"] == "running"

    # another process (or the background job) must not start a second turn
    assert Mailbox(other).claim_for("coder", owner="b") is None
    mb.post("operator", "browser", "autre")
    assert Mailbox(other).claim_for("browser", owner="b") is None

    db.close()
    other.close()


def test_stale_running_is_recovered(config):
    """A message left running by a crash is claimable again."""
    db, mb = _mailbox(config)
    mid = mb.post("operator", "coder", "travail")
    db.claim_next_message("coder", owner="crashed")
    db.mark_message(mid, "running")  # simulate: claimed_at lost on crash
    again = db.claim_next_message("coder", owner="retry")
    assert again is not None and again["id"] == mid
    db.close()


def test_archive_pending_messages(config):
    db, mb = _mailbox(config)
    db.post_message("browser", "operator", "rapport de mission")
    assert db.archive_pending_messages("operator", "operator channel disabled") == 1
    assert mb.next_for("operator") is None
    assert mb.history()[-1]["status"] == "archived"
    db.close()
