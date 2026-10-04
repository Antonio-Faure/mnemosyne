"""The per-task temporary mailbox.

A message exists only INSIDE a task: it is written by one agent to the other,
and the mailbox dies with the task. There is no global inbox to intervene in —
the operator posts TASKS to the queue, never messages.
"""

from __future__ import annotations

import pytest

from mnemosyne.agents.mailbox import AGENTS, Mailbox
from mnemosyne.db import Database


@pytest.fixture
def mailbox(config):
    db = Database(config.db_file())
    task_id = db.enqueue_task("browser", "objectif de test")
    try:
        yield db, Mailbox(db), task_id
    finally:
        db.close()


def test_a_message_lives_inside_its_task(mailbox):
    db, mb, task_id = mailbox
    mid = mb.post("browser", "coder", "travaille", task_id)
    pending = mb.pending_for(task_id, "coder")
    assert [m["id"] for m in pending] == [mid]
    assert pending[0]["task_id"] == task_id
    # the same message is invisible to another task
    other_task = db.enqueue_task("coder", "autre objectif")
    assert mb.pending_for(other_task, "coder") == []


def test_a_taskless_message_does_not_exist(mailbox):
    _db, mb, task_id = mailbox
    with pytest.raises(ValueError):
        mb.post("browser", "coder", "orphelin", None)


def test_agents_and_operator_exchange(mailbox):
    _db, mb, task_id = mailbox
    # the operator is the third correspondent: agents ask, the operator answers
    assert mb.post("browser", "operator", "ping", task_id) > 0
    assert mb.post("operator", "coder", "bonjour coder", task_id) > 0
    with pytest.raises(ValueError):
        mb.post("browser", "stranger", "ping", task_id)


def test_cannot_message_yourself(mailbox):
    _db, mb, task_id = mailbox
    with pytest.raises(ValueError):
        mb.post("browser", "browser", "moi", task_id)


def test_mark_is_the_memory_of_what_was_done(mailbox):
    db, mb, task_id = mailbox
    mid = mb.post("browser", "coder", "mission", task_id)
    mb.mark(mid, "handled", "fait : lien wetransfer https://…")
    assert mb.pending_for(task_id, "coder") == [], "un message marqué n'est plus à consommer"
    stored = mb.history()[-1]
    assert stored["status"] == "handled"
    assert "wetransfer" in stored["note"]


def test_recipients_are_the_agents_with_work_to_do(mailbox):
    db, mb, task_id = mailbox
    assert mb.recipients(task_id) == []
    mb.post("browser", "coder", "aller", task_id)
    assert mb.recipients(task_id) == ["coder"]
    mb.post("coder", "browser", "aller-retour", task_id)
    assert mb.recipients(task_id) == ["browser", "coder"]
    for message in mb.pending_for(task_id, "coder"):
        mb.mark(message["id"], "handled")
    assert mb.recipients(task_id) == ["browser"]


def test_the_mailbox_dies_with_the_task(mailbox):
    db, mb, task_id = mailbox
    mb.post("browser", "coder", "aller", task_id)
    mb.post("coder", "browser", "retour", task_id)
    assert mb.pending_count(task_id) == 2
    assert db.delete_task_messages(task_id) == 2
    assert mb.pending_count(task_id) == 0


def test_agents_constant_is_the_bi_agent_pair():
    assert AGENTS == ("coder", "browser")
