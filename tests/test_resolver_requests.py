"""Resolver source-request dependencies: parking, filtering and wake-up."""

from __future__ import annotations

from mnemosyne.agents.mailbox import Mailbox
from mnemosyne.agents.supervisor import _complete_resolver_dependencies
from mnemosyne.db import Database


def _db(config) -> Database:
    return Database(config.db_file())


def test_next_task_filters_agent_family(config):
    db = _db(config)
    try:
        coder = db.enqueue_task("coder", "add a source")
        resolver = db.enqueue_task("resolver", "illustrate a sentence")
        assert db.next_task(agents=("coder", "browser"))["id"] == coder
        assert db.next_task(agents=("resolver",))["id"] == resolver
        assert db.next_task(agents=("browser",)) is None
    finally:
        db.close()


def test_resolver_parks_while_sources_pending(config):
    db = _db(config)
    try:
        resolver = db.enqueue_task("resolver", "illustrate a sentence")
        db.set_task_status(resolver, "running", agent="resolver")
        coder = db.enqueue_task("coder", "add source X")
        request = db.create_resolver_request(
            resolver,
            sentence_id="yt_1",
            source_id="source_x",
            source_name="Source X",
            biagent_task_id=coder,
        )
        assert request > 0
        assert db.task_waiting_on_sources(resolver) is True
        assert db.next_task(agents=("resolver",)) is None

        db.complete_resolver_requests_for_biagent(coder, status="done", note="added")
        assert db.task_waiting_on_sources(resolver) is False
        # A wake message is what makes it runnable again.
        Mailbox(db).post("system", "resolver", "[SOURCES READY]", resolver)
        task = db.next_task(agents=("resolver",))
        assert task is not None and task["id"] == resolver
    finally:
        db.close()


def test_multiple_requests_wake_only_when_all_terminal(config):
    db = _db(config)
    try:
        resolver = db.enqueue_task("resolver", "illustrate a sentence")
        db.set_task_status(resolver, "running", agent="resolver")
        first = db.enqueue_task("coder", "add source A")
        second = db.enqueue_task("coder", "add source B")
        db.create_resolver_request(
            resolver, source_id="a", source_name="A", biagent_task_id=first
        )
        db.create_resolver_request(
            resolver, source_id="b", source_name="B", biagent_task_id=second
        )

        assert db.complete_resolver_requests_for_biagent(first, status="done") == [resolver]
        assert db.task_waiting_on_sources(resolver) is True
        assert db.next_task(agents=("resolver",)) is None

        assert db.complete_resolver_requests_for_biagent(second, status="failed") == [resolver]
        assert db.task_waiting_on_sources(resolver) is False
    finally:
        db.close()


def test_supervisor_helper_posts_one_wake_message(config):
    db = _db(config)
    try:
        resolver = db.enqueue_task("resolver", "illustrate a sentence")
        db.set_task_status(resolver, "running", agent="resolver")
        biagent = db.enqueue_task("coder", "add source A")
        db.create_resolver_request(
            resolver, source_id="a", source_name="A", biagent_task_id=biagent
        )
        _complete_resolver_dependencies(
            db, Mailbox(db), biagent, "done", "source added"
        )
        pending = db.pending_task_messages(resolver, "resolver")
        assert len(pending) == 1
        assert pending[0]["sender"] == "system"
        assert "SOURCES READY" in pending[0]["body"]
        assert "A: done" in pending[0]["body"]
        # Completing again must not post a duplicate.
        _complete_resolver_dependencies(
            db, Mailbox(db), biagent, "done", "source added"
        )
        assert len(db.pending_task_messages(resolver, "resolver")) == 1
    finally:
        db.close()


def test_cancel_cleanup_removes_resolver_requests(config):
    db = _db(config)
    try:
        resolver = db.enqueue_task("resolver", "illustrate a sentence")
        db.create_resolver_request(resolver, source_id="a")
        assert db.resolver_requests(resolver)
        db.delete_task_resolver_requests(resolver)
        assert db.resolver_requests(resolver) == []
    finally:
        db.close()
