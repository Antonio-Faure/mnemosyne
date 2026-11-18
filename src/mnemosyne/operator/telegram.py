"""Telegram rendering and routing for operator questions.

Design (see docs/OPERATEUR-TELEGRAM.md):

* each agent has its own bot and its own chat with the operator
  (coder, browser, resolver — never shared);
* a question is stored (`operator_asks`), posted in the task's mailbox
  (`agent → operator`) and sent with inline keyboard buttons;
* questions are delivered ONE AT A TIME: the next one is only sent after the
  previous answer, so no two agents can ask at the same time;
* a tap (or a free-text reply) is routed back into the mailbox
  (`operator → agent`) and the bridge wakes the task immediately;
* one process (the container) is the only update reader for the three bots,
  through a persistent long poll (not a periodic job).
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from typing import Any

import httpx

from mnemosyne.agents.mailbox import OPERATOR, Mailbox
from mnemosyne.config import Config, OperatorBotConfig
from mnemosyne.db import Database
from mnemosyne.logger import get_logger
from mnemosyne.util import utcnow_iso

log = get_logger("operator")

_API = "https://api.telegram.org"
#: a free-text answer is capped like any mailbox body
_MAX_ANSWER = 500
#: buttons we render ourselves; anything else is ignored
_CALLBACK_PREFIX = "q"


def resolve_bot(config: Config, agent: str, vault_get) -> tuple[str, str] | None:
    """(token, chat_id) for one agent's bot; token from env, then the vault."""
    bot: OperatorBotConfig | None = getattr(config.operator, agent, None)
    if bot is None:
        return None
    chat_id = bot.chat_id or (
        os.environ.get(bot.chat_id_env, "") if bot.chat_id_env else ""
    )
    if not chat_id:
        return None
    token = os.environ.get(bot.bot_token_env) or ""
    if not token and vault_get is not None:
        token = str(vault_get(bot.bot_token_env.lower()) or "")
    if not token:
        return None
    return token, chat_id


def question_text(ask: dict) -> str:
    """The question as the operator sees it (options numbered for the log)."""
    options = json.loads(ask["options"])
    lines = [f"❓ {ask['agent']} (tâche #{ask['task_id']}) — {ask['question']}"]
    for i, option in enumerate(options, start=1):
        detail = f" — {option['description']}" if option.get("description") else ""
        lines.append(f"{i}. {option['label']}{detail}")
    return "\n".join(lines)


def build_question_payload(ask: dict, chat_id: str) -> dict:
    """sendMessage payload: the question + one button per option + free text."""
    options = json.loads(ask["options"])
    rows: list[list[dict]] = [
        [{"text": option["label"], "callback_data": f"{_CALLBACK_PREFIX}:{ask['id']}:{i}"}]
        for i, option in enumerate(options)
    ]
    rows.append(
        [{"text": "✏️ Autre réponse", "callback_data": f"{_CALLBACK_PREFIX}:{ask['id']}:custom"}]
    )
    return {
        "chat_id": chat_id,
        "text": question_text(ask),
        "reply_markup": {"inline_keyboard": rows},
    }


async def _api_post(
    token: str, method: str, payload: dict, *, timeout: float = 15.0, quiet: bool = False
) -> dict | None:
    """Best-effort Telegram call; a failure must never break the pipeline."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{_API}/bot{token}/{method}", json=payload)
        if resp.status_code >= 400:
            if not quiet:
                log.warning(
                    "telegram %s failed: HTTP %s — %s",
                    method,
                    resp.status_code,
                    _telegram_error(resp),
                )
            return None
        return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        if not quiet:
            log.warning(
                "telegram %s failed: %s", method, str(exc) or type(exc).__name__
            )
        return None


def _telegram_error(resp: httpx.Response) -> str:
    """The human-readable part of a Telegram error response (never the token)."""
    try:
        return str(resp.json().get("description") or resp.text)[:300]
    except ValueError:
        return (resp.text or "")[:300]


#: Telegram refuses answerCallbackQuery once the tap is older than its window.
_STALE_QUERY_MARKERS = (
    "query is too old",
    "query id is invalid",
    "response timeout expired",
)


def _is_stale_query(description: str) -> bool:
    """True when Telegram refused an answer because the callback query expired."""
    text = description.lower()
    return any(marker in text for marker in _STALE_QUERY_MARKERS)


async def _answer_callback(token: str, callback_id: str, text: str | None = None) -> bool:
    """Ack a button tap; an expired query is routine, not an error.

    Telegram keeps a button card forever but its callback query expires after a
    few minutes. A user can therefore tap a valid question long after it was
    sent; the answer must still be routed, and the UI feedback must still be the
    edit — the toast is optional.
    """
    payload: dict[str, Any] = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text[:200]
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{_API}/bot{token}/answerCallbackQuery", json=payload)
    except httpx.HTTPError as exc:
        log.warning("telegram answerCallbackQuery failed: %s", str(exc) or type(exc).__name__)
        return False
    if resp.status_code < 400:
        return True
    description = _telegram_error(resp)
    if _is_stale_query(description):
        log.debug("telegram answerCallbackQuery ignoré (requête expirée)")
        return False
    log.warning(
        "telegram answerCallbackQuery failed: HTTP %s — %s", resp.status_code, description
    )
    return False


async def _edit_message(token: str, chat_id: str, message_id: int, text: str) -> bool:
    """Edit the question card; retry once because a timeout can be transient."""
    for attempt in range(2):
        data = await _api_post(
            token,
            "editMessageText",
            {"chat_id": chat_id, "message_id": message_id, "text": text},
            timeout=20.0,
            quiet=attempt == 0,
        )
        if data is not None:
            return True
        if attempt == 0:
            await asyncio.sleep(0.5)
    return False


async def send_ask(config: Config, agent: str, ask: dict, vault_get) -> tuple[str, int] | None:
    """Send one question to the right bot. Returns (chat_id, message_id)."""
    bot = resolve_bot(config, agent, vault_get)
    if bot is None:
        return None
    token, chat_id = bot
    data = await _api_post(token, "sendMessage", build_question_payload(ask, chat_id))
    if not data:
        return None
    try:
        return chat_id, int(data["result"]["message_id"])
    except (KeyError, TypeError, ValueError):
        return None


async def ask_operator(
    config: Config,
    db: Database,
    vault_get,
    *,
    agent: str,
    task_id: int,
    question: str,
    options: list[dict[str, Any]],
) -> str:
    """Register the question and post it in the task mailbox.

    Delivery is deliberately NOT immediate: the telegram job sends questions one
    at a time (`send_next_ask`), and only after the previous answer. Telegram
    being unavailable is not fatal: the question is in the mailbox and the
    operator can answer with `mnemosyne answer`.
    """
    ask_id = secrets.token_hex(5)
    mailbox = Mailbox(db)
    body = question_text(
        {"agent": agent, "task_id": task_id, "question": question, "options": json.dumps(options)}
    )
    message_id = mailbox.post(agent, OPERATOR, body, task_id)
    db.create_ask(ask_id, task_id, agent, question, options, message_id=message_id)
    return ask_id


def _awaiting_answer(ask: dict) -> bool:
    """True when this question is already on the operator's screen."""
    return bool(ask.get("tg_message_id") or ask.get("tg_prompt_id"))


def next_ask_to_send(db: Database, *, since: str | None = None) -> dict | None:
    """The next question to send, or None when one is already awaiting an answer.

    This is the whole one-at-a-time mechanic: as long as a sent question has no
    answer, nothing else is delivered — whatever the agent or the task. `since`
    (ISO timestamp) skips a backlog created before the channel was enabled.
    """
    pending = db.list_asks(status="pending")
    if since:
        pending = [ask for ask in pending if str(ask.get("created_at") or "") >= since]
    if any(_awaiting_answer(ask) for ask in pending):
        return None
    for ask in pending:
        if not _awaiting_answer(ask):
            return ask
    return None


async def send_next_ask(
    config: Config, db: Database, vault_get, *, since: str | None = None
) -> dict | None:
    """Deliver the next pending question (if the channel is idle)."""
    ask = next_ask_to_send(db, since=since)
    if ask is None:
        return None
    sent = await send_ask(config, ask["agent"], ask, vault_get)
    if not sent:
        return None
    db.set_ask_telegram(ask["id"], sent[0], sent[1])
    log.info(
        "operator: question %s envoyée (agent %s, tâche #%s)",
        ask["id"],
        ask["agent"],
        ask["task_id"],
    )
    return ask


def _deliver(db: Database, ask: dict, answer: str) -> None:
    """Deliver the operator's answer into the task mailbox and close the ask."""
    mailbox = Mailbox(db)
    mailbox.post(OPERATOR, ask["agent"], answer, ask["task_id"])
    if ask.get("message_id"):
        mailbox.mark(ask["message_id"], "handled", note="répondu par l'opérateur")
    db.answer_ask(ask["id"], answer)


def handle_update(db: Database, agent: str, update: dict) -> dict | None:
    """Route ONE Telegram update. Pure routing (no network): testable.

    Returns a rendering order for the poller, or None when the update is not
    ours (unknown chat is filtered by the caller, this filters unknown shapes).
    """
    query = update.get("callback_query")
    if query:
        parts = str(query.get("data") or "").split(":")
        if len(parts) != 3 or parts[0] != _CALLBACK_PREFIX:
            return None
        ask = db.get_ask(parts[1])
        if ask is None or ask["status"] != "pending":
            return {"kind": "stale", "callback_id": query.get("id")}
        if parts[2] == "custom":
            return {"kind": "custom", "ask": ask, "callback_id": query.get("id")}
        options = json.loads(ask["options"])
        if not parts[2].isdigit() or int(parts[2]) >= len(options):
            return None
        answer = options[int(parts[2])]["label"]
        _deliver(db, ask, answer)
        return {"kind": "answered", "ask": ask, "answer": answer, "callback_id": query.get("id")}

    message = update.get("message")
    if message:
        reply = message.get("reply_to_message") or {}
        text = str(message.get("text") or "").strip()
        chat_id = str((message.get("chat") or {}).get("id", ""))
        if not reply or not text:
            return None
        replied_to = reply.get("message_id")
        for ask in db.list_asks(status="pending"):
            # Message ids are per bot: a reply in the coder bot must never match
            # a browser/resolver question that happens to share the same id.
            if ask.get("agent") != agent:
                continue
            if str(ask.get("tg_chat_id") or "") != chat_id:
                continue
            if replied_to in (ask.get("tg_message_id"), ask.get("tg_prompt_id")):
                answer = text[:_MAX_ANSWER]
                _deliver(db, ask, answer)
                return {"kind": "answered", "ask": ask, "answer": answer, "custom": True}
    return None


async def _render(token: str, chat_id: str, order: dict) -> None:
    """Apply the visual feedback for a routed update (best-effort).

    The card edit is the durable feedback; `answerCallbackQuery` is only the
    transient toast, and Telegram refuses it once the card is older than its
    window. Both run concurrently so a stale or slow toast never blocks the
    edit that actually tells the operator the answer was recorded.
    """
    kind = order["kind"]
    ack = None
    if order.get("callback_id"):
        ack_text = "Question expirée." if kind == "stale" else None
        ack = asyncio.create_task(
            _answer_callback(token, order["callback_id"], ack_text)
        )

    try:
        if kind == "stale":
            return

        ask = order["ask"]
        if kind == "custom":
            # a free-text answer arrives as a REPLY to a ForceReply prompt
            data = await _api_post(
                token,
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": f"✏️ Réponds à CE message avec ta réponse.\n\n{question_text(ask)}",
                    "reply_markup": {"force_reply": True, "selective": True},
                },
            )
            try:
                prompt_id = int(data["result"]["message_id"]) if data else None
            except (KeyError, TypeError, ValueError):
                prompt_id = None
            if prompt_id:
                # the prompt id is how the reply is matched; the caller owns the db
                order["prompt_id"] = prompt_id
            if ask.get("tg_message_id"):
                await _edit_message(
                    token,
                    chat_id,
                    ask["tg_message_id"],
                    f"{question_text(ask)}\n\n✏️ en attente de ta réponse personnalisée…",
                )
            return

        if kind == "answered" and ask.get("tg_message_id"):
            edited = await _edit_message(
                token,
                chat_id,
                ask["tg_message_id"],
                f"{question_text(ask)}\n\n✅ {order['answer']}",
            )
            if not edited:
                # the card may be gone or uneditable; the answer is still recorded
                await _api_post(
                    token,
                    "sendMessage",
                    {
                        "chat_id": chat_id,
                        "text": f"✅ Réponse enregistrée : {order['answer']}",
                    },
                )
    finally:
        if ack is not None:
            await ack

def _update_chat_id(update: dict) -> str:
    """The chat that produced this update (message or callback query)."""
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    if chat.get("id") is not None:
        return str(chat["id"])
    query = update.get("callback_query") or {}
    chat = ((query.get("message") or {}).get("chat") or {})
    return str(chat.get("id", ""))


def _poll_error(agent: str, exc: BaseException) -> None:
    """Log a polling failure without ever echoing the bot URL (it contains the token)."""
    if isinstance(exc, httpx.HTTPStatusError):
        log.warning(
            "telegram poll (%s) failed: HTTP %s — %s",
            agent,
            exc.response.status_code,
            _telegram_error(exc.response),
        )
    else:
        log.warning(
            "telegram poll (%s) failed: %s", agent, str(exc) or type(exc).__name__
        )


async def _route_update(
    db: Database,
    agent: str,
    token: str,
    chat_id: str,
    update: dict,
    wake=None,
) -> bool:
    """Route one update; return True when it produced a rendering order."""
    sender_chat = _update_chat_id(update)
    if sender_chat != chat_id:
        log.warning("telegram: update ignoré (chat non autorisé %s)", sender_chat)
        return False
    order = handle_update(db, agent, update)
    if order is None:
        return False
    # Wake the task BEFORE the card edit: the answer is already in the mailbox,
    # and a slow/failing edit must not delay the agent by another heartbeat tick.
    if wake is not None and order.get("kind") == "answered":
        try:
            wake(order)
        except Exception as exc:  # noqa: BLE001 - a wake failure must not lose the answer
            log.warning("operator wake failed: %s", str(exc) or type(exc).__name__)
    await _render(token, chat_id, order)
    if order.get("prompt_id") and order.get("ask"):
        db.set_ask_prompt(order["ask"]["id"], order["prompt_id"])
    log.info(
        "operator (%s): %s (tâche #%s)",
        agent,
        order["kind"],
        order["ask"]["task_id"] if order.get("ask") else "?",
    )
    return True


async def poll_once(config: Config, db: Database, vault_get) -> int:
    """Legacy one-shot poll (tests, manual checks).

    The live bridge uses :func:`listen_forever`; this function remains for
    compatibility and for the CLI/manual path.
    """
    handled = 0
    for agent in ("coder", "browser", "resolver"):
        bot = resolve_bot(config, agent, vault_get)
        if bot is None:
            continue
        token, chat_id = bot
        offset_key = f"telegram_offset:{agent}"
        offset = int(db.get_kv(offset_key, 0) or 0)
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    f"{_API}/bot{token}/getUpdates",
                    params={
                        "offset": offset,
                        "timeout": 0,
                        "allowed_updates": '["message","callback_query"]',
                    },
                )
                resp.raise_for_status()
                updates = resp.json().get("result", [])
        except (httpx.HTTPError, ValueError) as exc:
            _poll_error(agent, exc)
            continue

        for update in updates:
            try:
                if await _route_update(db, agent, token, chat_id, update):
                    handled += 1
            except Exception as exc:  # noqa: BLE001 - one poison update must not block the channel
                log.error("telegram update %s failed: %s", update.get("update_id"), exc)
            finally:
                # advance only AFTER the update was handled: a crash mid-batch
                # must not consume updates that were never routed
                db.set_kv(offset_key, int(update["update_id"]) + 1)
    # The answer (if any) just freed the channel: send the next question.
    since = db.get_kv("telegram_since") or None
    await send_next_ask(config, db, vault_get, since=since)
    return handled


async def _poll_bot(
    config: Config,
    db: Database,
    vault_get,
    agent: str,
    *,
    wake=None,
) -> None:
    """Long-poll ONE bot forever. Telegram holds the request until an update."""
    poll_timeout = max(5, int(config.operator.poll_timeout_s))
    while True:
        bot = resolve_bot(config, agent, vault_get)
        if bot is None:
            # Tokens can be added to .env without a reload; retry quietly.
            await asyncio.sleep(30)
            continue
        token, chat_id = bot
        offset_key = f"telegram_offset:{agent}"
        offset = int(db.get_kv(offset_key, 0) or 0)
        try:
            async with httpx.AsyncClient(timeout=poll_timeout + 10) as client:
                resp = await client.get(
                    f"{_API}/bot{token}/getUpdates",
                    params={
                        "offset": offset,
                        "timeout": poll_timeout,
                        "allowed_updates": '["message","callback_query"]',
                    },
                )
                resp.raise_for_status()
                updates = resp.json().get("result", [])
        except asyncio.CancelledError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            _poll_error(agent, exc)
            await asyncio.sleep(2)
            continue

        for update in updates:
            try:
                await _route_update(db, agent, token, chat_id, update, wake=wake)
            except Exception as exc:  # noqa: BLE001 - one poison update must not block the channel
                log.error("telegram update %s failed: %s", update.get("update_id"), exc)
            finally:
                db.set_kv(offset_key, int(update["update_id"]) + 1)


async def _sender_loop(config: Config, db: Database, vault_get) -> None:
    """Send the next queued question as soon as the channel is free."""
    interval = max(0.5, float(config.operator.send_interval_s))
    while True:
        try:
            since = db.get_kv("telegram_since") or None
            await send_next_ask(config, db, vault_get, since=since)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - the sender must never die
            log.warning(
                "telegram sender failed: %s", str(exc) or type(exc).__name__
            )
        await asyncio.sleep(interval)


async def listen_forever(config: Config, db: Database, vault_get, *, wake=None) -> None:
    """The live operator bridge: long-poll the three bots, route immediately.

    This mirrors the Hermes gateway architecture: a persistent long-poll loop
    instead of a periodic heartbeat job. Answers are acknowledged and routed as
    soon as Telegram delivers them; ``wake`` lets the heartbeat resume the task
    without waiting for the next agency tick.
    """
    if not db.get_kv("telegram_since"):
        # First enabled run: never dump a backlog accumulated while the bridge
        # was off. Only questions created from now on are delivered.
        db.set_kv("telegram_since", utcnow_iso())
    log.info("telegram bridge listening (long poll, 3 bots)")
    tasks = [asyncio.create_task(_sender_loop(config, db, vault_get), name="telegram-sender")]
    for agent in ("coder", "browser", "resolver"):
        tasks.append(
            asyncio.create_task(
                _poll_bot(config, db, vault_get, agent, wake=wake),
                name=f"telegram-poll:{agent}",
            )
        )
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
