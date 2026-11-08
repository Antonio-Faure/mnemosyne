"""IMAP email wait: park a task until a matching message arrives.

The browser agent cannot poll a mailbox forever without burning tokens. It
calls `wait_for_email` with criteria (expected sender and/or the Message-ID of
the email it sent); the wait is stored, a marker message is posted in the task
mailbox (so the task is not closed), and `next_task()` parks the task. The
heartbeat's `email_watch` job polls the configured IMAP mailbox; on a match it
posts the email into the task mailbox (sender ``email``), marks the marker
handled, and the task is picked up again by the next agency tick.
"""

from __future__ import annotations

import asyncio
import email
import html
import imaplib
import os
import re
from datetime import UTC, datetime, timedelta
from email.header import decode_header, make_header
from email.message import Message
from email.policy import default
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any

from mnemosyne.agents.mailbox import EMAIL, SYSTEM, Mailbox
from mnemosyne.config import Config
from mnemosyne.db import Database
from mnemosyne.logger import get_logger
from mnemosyne.observatory import events, task_session_id

log = get_logger("mailwatch")

#: Do not scan an unbounded inbox on every poll.
_MAX_UIDS_PER_POLL = 500

#: How much clock skew we tolerate between the wait creation and the email Date.
_DATE_SKEW = timedelta(hours=1)


def _env_or_vault(config: Config, env_name: str, vault_get) -> str | None:
    value = os.environ.get(env_name)
    if not value and vault_get is not None:
        value = vault_get(env_name.lower())
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def resolve_credentials(config: Config, vault_get) -> tuple[str, str] | None:
    """(username, password) from env first, then the vault (lowercased env name)."""
    cfg = config.email
    username = _env_or_vault(config, cfg.username_env, vault_get)
    password = _env_or_vault(config, cfg.password_env, vault_get)
    if not username or not password:
        return None
    return username, password


def watcher_ready(config: Config, vault_get) -> bool:
    """True when the feature is enabled and the IMAP endpoint is usable."""
    cfg = config.email
    if not cfg.enabled or not cfg.imap_host.strip():
        return False
    return resolve_credentials(config, vault_get) is not None


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _header(msg: Message, name: str) -> str:
    raw = msg.get(name)
    if raw is None:
        return ""
    try:
        return str(make_header(decode_header(str(raw)))).strip()
    except (LookupError, UnicodeError):
        return str(raw).strip()


def _from_addresses(msg: Message) -> list[str]:
    return [
        addr.strip().lower()
        for _name, addr in getaddresses([_header(msg, "From")])
        if addr and addr.strip()
    ]


def _normalize_message_id(value: str | None) -> str:
    return (value or "").strip().strip("<>").strip().lower()


def _message_date(msg: Message) -> datetime | None:
    raw = msg.get("Date")
    if raw is None:
        return None
    try:
        parsed = parsedate_to_datetime(str(raw))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def matches(wait: dict, msg: Message, config: Config) -> bool:
    """Pure predicate used by the watcher and by the offline tests."""
    from_address = (wait.get("from_address") or "").strip().lower()
    subject_needle = (wait.get("subject_contains") or "").strip().lower()
    in_reply_to = _normalize_message_id(wait.get("in_reply_to"))

    if not from_address and not in_reply_to:
        return False

    addresses = _from_addresses(msg)
    own = (config.identity.agent_email or "").strip().lower()
    if own and own in addresses:
        return False

    # Never wake on vacation/automatic replies.
    auto = _header(msg, "Auto-Submitted").lower()
    if auto and auto != "no":
        return False
    if _header(msg, "X-Autoreply") or _header(msg, "X-Autorespond"):
        return False

    if from_address:
        if from_address.startswith("@"):
            if not any(addr.endswith(from_address) for addr in addresses):
                return False
        elif "@" in from_address:
            if from_address not in addresses:
                return False
        elif from_address not in _header(msg, "From").lower():
            return False

    if subject_needle and subject_needle not in _header(msg, "Subject").lower():
        return False

    if in_reply_to:
        refs = (
            _header(msg, "In-Reply-To").lower()
            + " "
            + _header(msg, "References").lower()
        )
        refs = refs.replace("<", " ").replace(">", " ").replace("\n", " ")
        if in_reply_to not in refs:
            return False

    created = _parse_iso(wait.get("created_at"))
    sent = _message_date(msg)
    if created is not None and sent is not None and sent < created - _DATE_SKEW:
        # An old message cannot be the answer to this wait.
        return False
    return True


def body_text(msg: Message, limit: int) -> str:
    """Plain-text body (HTML converted), bounded to ``limit`` characters."""
    part = None
    try:
        part = msg.get_body(preferencelist=("plain",))
        if part is None:
            part = msg.get_body(preferencelist=("html",))
    except (AttributeError, ValueError):
        part = None

    if part is not None:
        try:
            content = part.get_content()
        except (LookupError, UnicodeError, ValueError):
            payload = part.get_payload(decode=True) or b""
            content = payload.decode(part.get_content_charset() or "utf-8", "replace")
        if isinstance(content, bytes):
            content = content.decode(part.get_content_charset() or "utf-8", "replace")
        if part.get_content_subtype() == "html":
            content = re.sub(r"<[^>]+>", " ", content)
            content = html.unescape(content)
    else:
        # Fallback for malformed multipart messages.
        chunks: list[str] = []
        for sub in msg.walk():
            if sub.get_content_maintype() != "text":
                continue
            try:
                chunk = sub.get_content()
            except (LookupError, UnicodeError, ValueError):
                continue
            if isinstance(chunk, bytes):
                chunk = chunk.decode(sub.get_content_charset() or "utf-8", "replace")
            chunks.append(chunk)
        content = "\n".join(chunks)

    content = re.sub(r"[ \t]+\n", "\n", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()[:limit]


def _fetch_headers(conn: imaplib.IMAP4, uid: bytes) -> Message | None:
    try:
        status, data = conn.uid("fetch", uid.decode("ascii", "replace"), "(RFC822.HEADER)")
    except imaplib.IMAP4.error:
        return None
    if status != "OK":
        return None
    raw = b"".join(part[1] for part in data if isinstance(part, tuple))
    if not raw:
        return None
    return email.message_from_bytes(raw, policy=default)


def _fetch_full(conn: imaplib.IMAP4, uid: bytes) -> Message | None:
    try:
        status, data = conn.uid("fetch", uid.decode("ascii", "replace"), "(RFC822)")
    except imaplib.IMAP4.error:
        return None
    if status != "OK":
        return None
    raw = b"".join(part[1] for part in data if isinstance(part, tuple))
    if not raw:
        return None
    return email.message_from_bytes(raw, policy=default)


def _deliver(config: Config, db: Database, wait: dict, uid: bytes, msg: Message) -> None:
    mailbox = Mailbox(db)
    sender = _header(msg, "From")
    subject = _header(msg, "Subject")
    message_id = _header(msg, "Message-ID")
    body = (
        "[EMAIL RECEIVED]\n"
        f"From: {sender}\n"
        f"To: {_header(msg, 'To')}\n"
        f"Subject: {subject}\n"
        f"Date: {_header(msg, 'Date')}\n"
        f"Message-ID: {message_id}\n\n"
        f"{body_text(msg, config.email.max_body_chars)}"
    )
    mailbox.post(EMAIL, wait["agent"], body, wait["task_id"])
    if wait.get("marker_message_id"):
        mailbox.mark(int(wait["marker_message_id"]), "handled", note="email reçu")
    db.match_email_wait(
        int(wait["id"]),
        uid=uid.decode("ascii", "replace"),
        from_address=sender,
        subject=subject,
        message_id=message_id,
        note="email reçu",
    )
    db.add_event(
        task_session_id(int(wait["task_id"])),
        "email.received",
        actor=EMAIL,
        payload={
            "wait_id": wait["id"],
            "from": sender,
            "subject": subject,
            "message_id": message_id,
            "uid": uid.decode("ascii", "replace"),
        },
    )


def _timeout(db: Database, wait: dict) -> None:
    mailbox = Mailbox(db)
    timeout_s = int(wait.get("timeout_s") or 0)
    mailbox.post(
        SYSTEM,
        wait["agent"],
        (
            f"[EMAIL WAIT #{wait['id']} TIMEOUT]\n"
            f"Aucun email correspondant reçu après {timeout_s} s.\n"
            "La session est réactivée pour décider de la suite."
        ),
        wait["task_id"],
    )
    if wait.get("marker_message_id"):
        mailbox.mark(int(wait["marker_message_id"]), "handled", note="délai email expiré")
    db.timeout_email_wait(int(wait["id"]), note=f"aucun email après {timeout_s} s")
    db.add_event(
        task_session_id(int(wait["task_id"])),
        "email.timeout",
        actor=SYSTEM,
        payload={"wait_id": wait["id"], "timeout_s": timeout_s},
    )


def _poll_sync(
    config: Config,
    db: Database,
    credentials: tuple[str, str],
    waits: list[dict],
) -> int:
    cfg = config.email
    matched: set[int] = set()
    delivered = 0
    oldest = min(
        (_parse_iso(w.get("created_at")) or datetime.now(UTC)) for w in waits
    )
    since = (oldest - timedelta(days=1)).strftime("%d-%b-%Y")

    conn: imaplib.IMAP4 | None = None
    try:
        if cfg.imap_ssl:
            conn = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port, timeout=30)
        else:
            conn = imaplib.IMAP4(cfg.imap_host, cfg.imap_port, timeout=30)
        conn.login(*credentials)
        status, _ = conn.select(cfg.folder, readonly=True)
        if status != "OK":
            log.warning("email watch: cannot select folder %s", cfg.folder)
            return 0
        status, data = conn.uid("search", None, "SINCE", since)
        if status != "OK" or not data:
            return 0
        uids = data[0].split() if data and data[0] else []
        # Newest first: a reply is much more likely near the end.
        for uid in reversed(uids[-_MAX_UIDS_PER_POLL:]):
            if len(matched) >= len(waits):
                break
            header = _fetch_headers(conn, uid)
            if header is None:
                continue
            for wait in waits:
                if int(wait["id"]) in matched:
                    continue
                if not matches(wait, header, config):
                    continue
                full = _fetch_full(conn, uid) or header
                _deliver(config, db, wait, uid, full)
                matched.add(int(wait["id"]))
                delivered += 1
                log.info(
                    "email watch: wait #%s matched for task #%s",
                    wait["id"],
                    wait["task_id"],
                )
    except (imaplib.IMAP4.error, OSError, TimeoutError) as exc:
        log.warning("email watch: IMAP error: %s", exc)
    finally:
        if conn is not None:
            try:
                conn.logout()
            except (imaplib.IMAP4.error, OSError):
                pass

    # Timeouts must fire even when IMAP is temporarily unavailable.
    now = datetime.now(UTC)
    for wait in waits:
        if int(wait["id"]) in matched:
            continue
        timeout_s = int(wait.get("timeout_s") or 0)
        if timeout_s <= 0:
            continue
        created = _parse_iso(wait.get("created_at"))
        if created is not None and now - created >= timedelta(seconds=timeout_s):
            _timeout(db, wait)
            matched.add(int(wait["id"]))
            delivered += 1
    return delivered


async def poll_once(config: Config, db: Database, vault_get) -> int:
    """Heartbeat entry point: returns the number of waits matched/timed out."""
    if not config.email.enabled:
        return 0
    credentials = resolve_credentials(config, vault_get)
    if credentials is None:
        return 0
    waits = db.pending_email_waits()
    if not waits:
        return 0
    return await asyncio.to_thread(_poll_sync, config, db, credentials, waits)


def register_email_wait(
    config: Config,
    db: Database,
    mailbox: Mailbox,
    *,
    agent: str,
    task_id: int,
    params: Any,
    vault_get,
) -> int:
    """Validate, post the marker, and persist one wait. Returns its id."""
    if not watcher_ready(config, vault_get):
        raise ValueError(
            "veille email désactivée ou incomplète (config.email.enabled + "
            "identifiants IMAP requis)"
        )
    from_address = (getattr(params, "from_address", None) or "").strip()
    in_reply_to = (getattr(params, "in_reply_to", None) or "").strip()
    subject_contains = (getattr(params, "subject_contains", None) or "").strip()
    if not from_address and not in_reply_to:
        raise ValueError(
            "wait_for_email exige from_address ou in_reply_to (subject seul trop large)"
        )
    if db.task_email_wait(task_id) is not None:
        raise ValueError("une attente email est déjà en cours pour cette tâche")

    timeout_s = int(getattr(params, "timeout_s", 0) or 0)
    reason = (getattr(params, "reason", "") or "").strip()
    marker = (
        f"[EMAIL WAIT]\n"
        f"from: {from_address or '(any)'}\n"
        f"subject_contains: {subject_contains or '(any)'}\n"
        f"in_reply_to: {in_reply_to or '(any)'}\n"
        f"timeout_s: {timeout_s}\n"
        f"reason: {reason or '(not given)'}\n\n"
        "La tâche est parquée : elle sera réactivée quand un email correspondant "
        "arrivera. Ne surveille pas la boîte en boucle."
    )
    marker_id = mailbox.post(agent, EMAIL, marker, task_id)
    wait_id = db.create_email_wait(
        task_id,
        agent,
        from_address=from_address,
        subject_contains=subject_contains,
        in_reply_to=in_reply_to,
        timeout_s=timeout_s,
        reason=reason,
        marker_message_id=marker_id,
    )
    events.record(
        "email.wait",
        {
            "wait_id": wait_id,
            "from": from_address,
            "subject_contains": subject_contains,
            "in_reply_to": in_reply_to,
            "timeout_s": timeout_s,
            "reason": reason,
        },
    )
    return wait_id
