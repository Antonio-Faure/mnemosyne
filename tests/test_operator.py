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


def test_random_message_without_reply_is_ignored(config):
    """A plain message is NOT an answer: it must not enter any task context."""
    db = Database(config.db_file())
    db.enqueue_task("coder", "mission")
    db.create_ask("a3", 1, "coder", "question ?", [{"label": "Oui"}])
    db.set_ask_telegram("a3", "42", 100)

    update = {
        "message": {
            "text": "bonjour, je passais par là",
            "chat": {"id": 42},
        }
    }
    order = telegram.handle_update(db, "coder", update)

    assert order is None
    assert db.get_ask("a3")["status"] == "pending"
    assert db.pending_task_messages(1, OPERATOR) == []
    assert db.pending_task_messages(1, "coder") == []
    db.close()


def test_reply_to_a_non_question_message_is_ignored(config):
    db = Database(config.db_file())
    db.enqueue_task("coder", "mission")
    db.create_ask("a4", 1, "coder", "question ?", [{"label": "Oui"}])
    db.set_ask_telegram("a4", "42", 100)

    update = {
        "message": {
            "text": "réponse à un vieux message",
            "chat": {"id": 42},
            "reply_to_message": {"message_id": 999},
        }
    }
    assert telegram.handle_update(db, "coder", update) is None
    assert db.get_ask("a4")["status"] == "pending"
    db.close()


def test_reply_to_an_answered_question_is_ignored(config):
    db = Database(config.db_file())
    db.enqueue_task("coder", "mission")
    db.create_ask("a5", 1, "coder", "question ?", [{"label": "Oui"}])
    db.set_ask_telegram("a5", "42", 100)
    db.answer_ask("a5", "Oui")

    update = {
        "message": {
            "text": "trop tard",
            "chat": {"id": 42},
            "reply_to_message": {"message_id": 100},
        }
    }
    assert telegram.handle_update(db, "coder", update) is None
    assert db.get_ask("a5")["status"] == "answered"
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


def test_resolver_question_is_stored_for_resolver_mailbox(config):
    db = Database(config.db_file())
    db.enqueue_task("resolver", "illustrate a sentence")
    try:
        ask_id = asyncio.run(
            telegram.ask_operator(
                config,
                db,
                None,
                agent="resolver",
                task_id=1,
                question="Valide ce candidat ?",
                options=[{"label": "Valide"}, {"label": "Refuse"}],
            )
        )
        assert db.get_ask(ask_id)["agent"] == "resolver"
        asked = db.pending_task_messages(1, "operator")
        assert len(asked) == 1
        assert asked[0]["sender"] == "resolver"
        assert "Valide ce candidat" in asked[0]["body"]
    finally:
        db.close()


def test_questions_are_delivered_one_at_a_time(config):
    """The Telegram drip: a sent-but-unanswered question blocks the queue."""
    db = Database(config.db_file())
    try:
        db.enqueue_task("coder", "mission 1")
        db.enqueue_task("browser", "mission 2")
        db.create_ask("a1", 1, "coder", "q1", [{"label": "Oui"}])
        db.create_ask("a2", 2, "browser", "q2", [{"label": "Oui"}])

        assert telegram.next_ask_to_send(db)["id"] == "a1"
        db.set_ask_telegram("a1", "42", 100)
        assert telegram.next_ask_to_send(db) is None, "one question at a time"

        db.answer_ask("a1", "Oui")
        assert telegram.next_ask_to_send(db)["id"] == "a2"
    finally:
        db.close()


def test_ask_operator_does_not_send_immediately(config, monkeypatch):
    """The agent only registers; the telegram job owns delivery order."""
    sent: list[str] = []

    async def fake_send(cfg, agent, ask, vault_get):
        sent.append(ask["id"])
        return None

    monkeypatch.setattr(telegram, "send_ask", fake_send)
    db = Database(config.db_file())
    try:
        db.enqueue_task("resolver", "mission")
        ask_id = asyncio.run(
            telegram.ask_operator(
                config,
                db,
                None,
                agent="resolver",
                task_id=1,
                question="Valide ?",
                options=[{"label": "Oui"}, {"label": "Non"}],
            )
        )
        assert sent == []
        assert db.get_ask(ask_id)["tg_message_id"] is None
    finally:
        db.close()


def test_resolver_has_its_own_bot(config):
    assert config.operator.resolver.bot_token_env == "MNEMOSYNE_RESOLVER_BOT_TOKEN"
    assert config.operator.resolver is not config.operator.browser


def test_reply_is_matched_within_the_right_bot(config):
    """Two bots can use the same message id: the reply must not cross them."""
    db = Database(config.db_file())
    try:
        db.enqueue_task("coder", "mission 1")
        db.enqueue_task("browser", "mission 2")
        db.create_ask("a1", 1, "coder", "coder question", [{"label": "Oui"}])
        db.create_ask("a2", 2, "browser", "browser question", [{"label": "Oui"}])
        db.set_ask_telegram("a1", "42", 100)
        db.set_ask_telegram("a2", "42", 100)

        update = {
            "message": {
                "text": "réponse au coder",
                "chat": {"id": 42},
                "reply_to_message": {"message_id": 100},
            }
        }
        order = telegram.handle_update(db, "coder", update)
        assert order["kind"] == "answered"
        assert db.get_ask("a1")["status"] == "answered"
        assert db.get_ask("a2")["status"] == "pending"
    finally:
        db.close()


def test_questions_from_before_the_channel_was_enabled_are_skipped(config):
    """Enabling Telegram must not dump the backlog accumulated while it was off."""
    db = Database(config.db_file())
    try:
        db.enqueue_task("coder", "old mission")
        db.create_ask("old", 1, "coder", "old question", [{"label": "Oui"}])
        db._conn.execute(
            "UPDATE operator_asks SET created_at = '2000-01-01T00:00:00+00:00' WHERE id = 'old'"
        )
        db._conn.commit()
        db.enqueue_task("coder", "new mission")
        db.create_ask("new", 2, "coder", "new question", [{"label": "Oui"}])

        assert telegram.next_ask_to_send(db, since="2020-01-01T00:00:00+00:00")["id"] == "new"
    finally:
        db.close()
