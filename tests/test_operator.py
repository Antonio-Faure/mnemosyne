"""Operator channel: a question parks a task, an answer wakes it back.

The question lives in the task's mailbox (agent → operator), never in the
queue; the answer (operator → agent) resumes the task at the next tick, before
newer pending tasks.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from mnemosyne.agents import supervisor
from mnemosyne.agents.mailbox import OPERATOR, Mailbox
from mnemosyne.db import Database
from mnemosyne.operator import telegram


def test_mailbox_allows_operator_both_ways(config):
    db = Database(config.db_file())
    db.enqueue_task("coder", "mission")
    mailbox = Mailbox(db)
    question_id = mailbox.post("coder", OPERATOR, "question ?", 1)
    answer_id = mailbox.post(OPERATOR, "coder", "réponse", 1)
    assert answer_id > question_id
    db.close()


def test_callback_answer_delivers_and_marks(config):
    db = Database(config.db_file())
    db.enqueue_task("coder", "mission")
    mailbox = Mailbox(db)
    question_id = mailbox.post("coder", OPERATOR, "question ?", 1)
    db.create_ask(
        "a1", 1, "coder", "question ?",
        [{"label": "Oui"}, {"label": "Non"}], message_id=question_id,
    )

    update = {"callback_query": {"id": "cb1", "data": "q:a1:0", "message": {"chat": {"id": 42}}}}
    order = telegram.handle_update(db, "coder", update)

    assert order["kind"] == "answered" and order["answer"] == "Oui"
    assert db.get_ask("a1")["status"] == "answered"
    pending = db.pending_task_messages(1, "coder")
    assert len(pending) == 1 and pending[0]["sender"] == OPERATOR
    assert pending[0]["body"] == "Oui"
    db.close()


def test_free_text_reply_routes_custom_answer(config):
    db = Database(config.db_file())
    db.enqueue_task("coder", "mission")
    db.create_ask("a2", 1, "coder", "question ?", [{"label": "Oui"}])
    db.set_ask_telegram("a2", "42", 100)

    update = {
        "message": {
            "text": "plutôt non finalement",
            "chat": {"id": 42},
            "reply_to_message": {"message_id": 100},
        }
    }
    order = telegram.handle_update(db, "coder", update)

    assert order["kind"] == "answered"
    assert order["answer"] == "plutôt non finalement"
    assert db.get_ask("a2")["status"] == "answered"
    db.close()


def test_unknown_callback_is_stale(config):
    db = Database(config.db_file())
    update = {"callback_query": {"id": "cb", "data": "q:nope:0", "message": {"chat": {"id": 1}}}}
    order = telegram.handle_update(db, "coder", update)
    assert order["kind"] == "stale"
    db.close()


def test_question_payload_has_buttons(config):
    db = Database(config.db_file())
    db.create_ask(
        "a1", 1, "coder", "On active la source ?",
        [{"label": "Oui", "description": "CC0"}, {"label": "Non"}],
    )
    payload = telegram.build_question_payload(db.get_ask("a1"), "42")
    rows = payload["reply_markup"]["inline_keyboard"]
    assert rows[0][0]["callback_data"] == "q:a1:0"
    assert rows[-1][0]["callback_data"] == "q:a1:custom"
    assert "On active la source ?" in payload["text"]
    db.close()


@dataclass
class _Outcome:
    finish: str
    branch: str | None = None


def test_parked_task_does_not_block_the_queue(config, monkeypatch):
    """A task waiting on the operator is skipped: the next task runs."""
    ran: list[int] = []

    async def fake_coder(cfg, task, mailbox, journal, vault_get, task_id=None, max_turns=None):
        ran.append(task_id)
        return _Outcome(finish="ok")

    monkeypatch.setitem(supervisor._RUNNERS, "coder", fake_coder)

    db = Database(config.db_file())
    db.enqueue_task("coder", "tâche 1")
    db.enqueue_task("coder", "tâche 2")
    db.set_task_status(1, "running")
    Mailbox(db).post("coder", OPERATOR, "question ?", 1)  # task 1 parks
    db.close()

    from mnemosyne.agents.supervisor import drain_queue

    asyncio.run(drain_queue(config))

    db = Database(config.db_file())
    assert db.get_task(1)["status"] == "running"  # still parked
    assert db.get_task(2)["status"] == "done"
    assert ran == [2]
    db.close()


def test_answer_wakes_the_parked_task_before_pending(config, monkeypatch):
    """The answered task resumes before newer pending tasks."""
    ran: list[int] = []

    async def fake_coder(cfg, task, mailbox, journal, vault_get, task_id=None, max_turns=None):
        ran.append(task_id)
        return _Outcome(finish="ok")

    monkeypatch.setitem(supervisor._RUNNERS, "coder", fake_coder)

    db = Database(config.db_file())
    db.enqueue_task("coder", "tâche 1")
    db.set_task_status(1, "running")
    mailbox = Mailbox(db)
    question_id = mailbox.post("coder", OPERATOR, "question ?", 1)
    db.create_ask("a9", 1, "coder", "question ?", [{"label": "Oui"}], message_id=question_id)
    db.enqueue_task("coder", "tâche 3")
    # the operator taps the answer button (routes + marks the question handled)
    telegram.handle_update(
        db,
        "coder",
        {"callback_query": {"id": "cb", "data": "q:a9:0", "message": {"chat": {"id": 1}}}},
    )
    db.close()

    from mnemosyne.agents.supervisor import drain_queue

    asyncio.run(drain_queue(config))

    assert ran[0] == 1
    db = Database(config.db_file())
    assert db.get_task(1)["status"] == "done"
    db.close()
