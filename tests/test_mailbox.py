import pytest

from mnemosyne.agents.mailbox import Mailbox
from mnemosyne.db import Database


def _mailbox(config) -> tuple[Database, Mailbox]:
    db = Database(config.db_file())
    return db, Mailbox(db)


def test_post_and_next(config):
    db, mb = _mailbox(config)
    mid = mb.post("operator", "coder", "connect europeana")
    msg = db.next_pending_message("coder")
    assert msg is not None and msg["id"] == mid and msg["status"] == "pending"
    assert db.next_pending_message("browser") is None
    db.close()


def test_mark_handled(config):
    db, mb = _mailbox(config)
    mid = mb.post("coder", "browser", "need the europeana api key")
    mb.mark(mid, "handled", "done")
    assert db.next_pending_message("browser") is None
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
    claimed = mb.claim_all_for("coder", owner="a", limit=1)
    assert claimed and claimed[0]["id"] == mid
    assert claimed[0]["status"] == "running"

    # another process (or the background job) must not start a second turn
    assert Mailbox(other).claim_all_for("coder", owner="b") == []
    mb.post("operator", "browser", "autre")
    assert Mailbox(other).claim_all_for("browser", owner="b") == []

    db.close()
    other.close()


def test_stale_running_is_recovered(config):
    """A message left running by a crash is claimable again."""
    db, mb = _mailbox(config)
    mid = mb.post("operator", "coder", "travail")
    db.claim_messages("coder", "crashed", limit=1)
    db.mark_message(mid, "running")  # simulate: claimed_at lost on crash
    again = db.claim_messages("coder", "retry", limit=1)
    assert again and again[0]["id"] == mid
    db.close()


def test_claim_all_batches_and_stays_exclusive(config):
    db, mb = _mailbox(config)
    mb.post("operator", "coder", "premier")
    mb.post("operator", "coder", "deuxieme")
    claimed = mb.claim_all_for("coder", owner="a")
    assert [m["body"] for m in claimed] == ["premier", "deuxieme"]
    assert all(m["status"] == "running" for m in claimed)
    # global turn-taking: nobody else can start a turn meanwhile
    assert mb.claim_all_for("coder", owner="b") == []
    db.close()


def test_claim_all_respects_the_batch_cap(config):
    db, mb = _mailbox(config)
    for i in range(7):
        mb.post("operator", "browser", f"message {i}")
    first = mb.claim_all_for("browser", owner="a")
    assert len(first) == 5
    # a second batch is impossible while a turn is running (turn-taking)
    assert mb.claim_all_for("browser", owner="a") == []
    for message in first:
        mb.mark(message["id"], "handled", "ok")
    # the overflow arrives on the next turn
    assert len(mb.claim_all_for("browser", owner="a")) == 2
    db.close()


