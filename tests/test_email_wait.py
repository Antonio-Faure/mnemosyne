"""Email waits: IMAP matching, mailbox wake-up, parking and timeout."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from email.message import EmailMessage
from email.policy import default

import pytest

from mnemosyne.agents.mailbox import Mailbox
from mnemosyne.db import Database
from mnemosyne.mailwatch import (
    _deliver,
    _timeout,
    body_text,
    matches,
    poll_once,
    register_email_wait,
)
from mnemosyne.operator.models import WaitForEmailParams


def _db(config) -> Database:
    return Database(config.db_file())


def _ready_config(config, monkeypatch):
    config.email.enabled = True
    config.email.imap_host = "imap.example.org"
    config.identity.agent_email = "agent@example.org"
    monkeypatch.setenv("MNEMOSYNE_EMAIL_USER", "agent@example.org")
    monkeypatch.setenv("MNEMOSYNE_EMAIL_PASSWORD", "app-password")
    return config


def _message(
    *,
    sender: str = "Person <person@example.org>",
    subject: str = "Re: Asking for permission",
    body: str = "Yes, you may use the images.\n\nBest,",
    in_reply_to: str | None = "<outgoing@example.org>",
    auto: bool = False,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = "agent@example.org"
    msg["Subject"] = subject
    msg["Date"] = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S +0000")
    msg["Message-ID"] = "<reply@example.org>"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    if auto:
        msg["Auto-Submitted"] = "auto-replied"
    msg.set_content(body)
    return msg


def _wait(config, *, timeout_s: int = 0) -> dict:
    db = _db(config)
    task_id = db.enqueue_task("browser", "wait for an email")
    db.set_task_status(task_id, "running", agent="browser")
    marker = db.post_message("browser", "email", "marker", task_id)
    wait_id = db.create_email_wait(
        task_id,
        "browser",
        from_address="person@example.org",
        subject_contains="permission",
        in_reply_to="outgoing@example.org",
        timeout_s=timeout_s,
        marker_message_id=marker,
    )
    wait = db.task_email_wait(task_id)
    db.close()
    assert wait is not None and wait["id"] == wait_id
    return wait


def test_matches_sender_subject_and_thread(config):
    config.identity.agent_email = "agent@example.org"
    wait = _wait(config)
    assert matches(wait, _message(), config) is True
    assert matches(wait, _message(sender="Other <other@example.org>"), config) is False
    assert matches(wait, _message(subject="Hello"), config) is False
    assert matches(wait, _message(in_reply_to="<other@example.org>"), config) is False


def test_matches_rejects_own_address_and_automatic_replies(config):
    config.identity.agent_email = "agent@example.org"
    wait = _wait(config)
    assert matches(wait, _message(sender="Agent <agent@example.org>"), config) is False
    assert matches(wait, _message(auto=True), config) is False


def test_matches_rejects_old_messages(config):
    config.identity.agent_email = "agent@example.org"
    wait = _wait(config)
    old = _message()
    old.replace_header("Date", "Mon, 01 Jan 2001 00:00:00 +0000")
    assert matches(wait, old, config) is False


def test_body_text_plain_and_html():
    plain = EmailMessage()
    plain.set_content("line one\n\nline two")
    assert "line one" in body_text(plain, 100)

    html = EmailMessage()
    html.set_content("<p>Hello <b>world</b></p>", subtype="html")
    text = body_text(html, 100)
    assert "Hello" in text and "world" in text and "<p>" not in text


def test_register_email_wait_parks_task(config, monkeypatch):
    _ready_config(config, monkeypatch)
    db = _db(config)
    task_id = db.enqueue_task("browser", "email mission")
    db.set_task_status(task_id, "running", agent="browser")
    mailbox = Mailbox(db)
    try:
        wait_id = register_email_wait(
            config,
            db,
            mailbox,
            agent="browser",
            task_id=task_id,
            params=WaitForEmailParams(from_address="person@example.org"),
            vault_get=None,
        )
        assert db.task_waiting_on_email(task_id) is True
        assert db.next_task() is None  # parked
        marker = db.pending_task_messages(task_id, "email")
        assert marker and marker[0]["sender"] == "browser"
        assert marker[0]["body"].startswith("[EMAIL WAIT]")
        assert db.task_email_wait(task_id)["id"] == wait_id
    finally:
        db.close()


def test_register_requires_credentials(config):
    config.email.enabled = True
    config.email.imap_host = "imap.example.org"
    db = _db(config)
    task_id = db.enqueue_task("browser", "email mission")
    mailbox = Mailbox(db)
    try:
        with pytest.raises(ValueError, match="veille email"):
            register_email_wait(
                config,
                db,
                mailbox,
                agent="browser",
                task_id=task_id,
                params=WaitForEmailParams(from_address="person@example.org"),
                vault_get=None,
            )
    finally:
        db.close()


def test_deliver_wakes_task_and_marks_marker(config):
    wait = _wait(config)
    db = Database(config.db_file())
    msg = _message()
    try:
        _deliver(config, db, wait, b"42", msg)
        assert db.task_waiting_on_email(wait["task_id"]) is False
        messages = db.pending_task_messages(wait["task_id"], "browser")
        assert len(messages) == 1
        assert messages[0]["sender"] == "email"
        assert "Yes, you may use the images." in messages[0]["body"]
        assert "Subject: Re: Asking for permission" in messages[0]["body"]
        marker = db.pending_task_messages(wait["task_id"], "email")
        assert marker == []  # marker handled
        task = db.next_task()
        assert task is not None and task["id"] == wait["task_id"]
    finally:
        db.close()


def test_timeout_wakes_task_with_system_message(config):
    wait = _wait(config, timeout_s=1)
    db = Database(config.db_file())
    try:
        _timeout(db, wait)
        messages = db.pending_task_messages(wait["task_id"], "browser")
        assert len(messages) == 1
        assert messages[0]["sender"] == "system"
        assert "TIMEOUT" in messages[0]["body"]
        assert db.task_email_wait(wait["task_id"]) is None
    finally:
        db.close()


class _FakeIMAP:
    payload = b""

    def __init__(self, host: str, port: int, timeout: float | None = None):
        self.host = host
        self.port = port

    def login(self, user: str, password: str):
        return "OK", [b""]

    def select(self, folder: str, readonly: bool = False):
        return "OK", [b"1"]

    def uid(self, command: str, *args):
        if command == "search":
            return "OK", [b"1"]
        if command == "fetch":
            return "OK", [(b"1", self.payload)]
        return "NO", []

    def logout(self):
        return "BYE", [b""]


def test_poll_once_delivers_matching_email(config, monkeypatch):
    _ready_config(config, monkeypatch)
    _FakeIMAP.payload = _message().as_bytes(policy=default)
    monkeypatch.setattr("mnemosyne.mailwatch.imaplib.IMAP4_SSL", _FakeIMAP)

    db = _db(config)
    task_id = db.enqueue_task("browser", "email mission")
    db.set_task_status(task_id, "running", agent="browser")
    mailbox = Mailbox(db)
    try:
        register_email_wait(
            config,
            db,
            mailbox,
            agent="browser",
            task_id=task_id,
            params=WaitForEmailParams(from_address="person@example.org"),
            vault_get=None,
        )
        handled = asyncio.run(poll_once(config, db, None))
        assert handled == 1
        assert db.task_waiting_on_email(task_id) is False
        messages = db.pending_task_messages(task_id, "browser")
        assert len(messages) == 1
        assert messages[0]["sender"] == "email"
        assert "EMAIL RECEIVED" in messages[0]["body"]
        assert db.next_task()["id"] == task_id
    finally:
        db.close()


def test_cancel_cleanup_removes_email_wait(config):
    wait = _wait(config)
    db = Database(config.db_file())
    try:
        db.delete_task_email_waits(wait["task_id"])
        assert db.task_waiting_on_email(wait["task_id"]) is False
    finally:
        db.close()
