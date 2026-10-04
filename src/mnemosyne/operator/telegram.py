"""Telegram rendering and routing for operator questions.

Design (see docs/OPERATEUR-TELEGRAM.md):

* each agent has its own bot and its own chat with the operator;
* a question is stored (`operator_asks`), posted in the task's mailbox
  (`agent → operator`) and sent with inline keyboard buttons;
* a tap (or a free-text reply) is routed back into the mailbox
  (`operator → agent`) and the task resumes at the next heartbeat tick;
* one process (the container) is the only update reader for both bots.
"""

from __future__ import annotations

import json
import os
import secrets
from typing import Any

import httpx

from mnemosyne.agents.mailbox import OPERATOR, Mailbox
from mnemosyne.config import Config, OperatorBotConfig
from mnemosyne.db import Database
from mnemosyne.logger import get_logger

log = get_logger("operator")

_API = "https://api.telegram.org"
#: a free-text answer is capped like any mailbox body
_MAX_ANSWER = 500
#: buttons we render ourselves; anything else is ignored
_CALLBACK_PREFIX = "q"


def resolve_bot(config: Config, agent: str, vault_get) -> tuple[str, str] | None:
    """(token, chat_id) for one agent's bot; token from env, then the vault."""
    bot: OperatorBotConfig | None = getattr(config.operator, agent, None)
    if bot is None or not bot.chat_id:
        return None
    token = os.environ.get(bot.bot_token_env) or ""
    if not token and vault_get is not None:
        token = str(vault_get(bot.bot_token_env.lower()) or "")
    if not token:
        return None
    return token, bot.chat_id


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


async def _api_post(token: str, method: str, payload: dict) -> dict | None:
    """Best-effort Telegram call; a failure must never break the pipeline."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{_API}/bot{token}/{method}", json=payload)
            resp.raise_for_status()
            return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("telegram %s failed: %s", method, exc)
        return None


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
    """Register the question, post it in the task mailbox, send it to Telegram.

    Returns the ask id. Telegram being unavailable is not fatal: the question
    is still in the mailbox and the operator can answer with `mnemosyne answer`.
    """
    ask_id = secrets.token_hex(5)
    mailbox = Mailbox(db)
    body = question_text(
        {"agent": agent, "task_id": task_id, "question": question, "options": json.dumps(options)}
    )
    message_id = mailbox.post(agent, OPERATOR, body, task_id)
    db.create_ask(ask_id, task_id, agent, question, options, message_id=message_id)
    sent = await send_ask(config, agent, db.get_ask(ask_id), vault_get)
    if sent:
        db.set_ask_telegram(ask_id, sent[0], sent[1])
    return ask_id


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
            if str(ask.get("tg_chat_id") or "") != chat_id:
                continue
            if replied_to in (ask.get("tg_message_id"), ask.get("tg_prompt_id")):
                answer = text[:_MAX_ANSWER]
                _deliver(db, ask, answer)
                return {"kind": "answered", "ask": ask, "answer": answer, "custom": True}
    return None


async def _render(token: str, chat_id: str, order: dict) -> None:
    """Apply the visual feedback for a routed update (best-effort)."""
    kind = order["kind"]
    if kind == "stale":
        if order.get("callback_id"):
            await _api_post(
                token,
                "answerCallbackQuery",
                {"callback_query_id": order["callback_id"], "text": "Question expirée."},
            )
        return

    ask = order["ask"]
    if order.get("callback_id"):
        await _api_post(
            token, "answerCallbackQuery", {"callback_query_id": order["callback_id"]}
        )

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
            await _api_post(
                token,
                "editMessageText",
                {
                    "chat_id": chat_id,
                    "message_id": ask["tg_message_id"],
                    "text": f"{question_text(ask)}\n\n✏️ en attente de ta réponse personnalisée…",
                },
            )
        return

    if kind == "answered" and ask.get("tg_message_id"):
        await _api_post(
            token,
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": ask["tg_message_id"],
                "text": f"{question_text(ask)}\n\n✅ {order['answer']}",
            },
        )


async def poll_once(config: Config, db: Database, vault_get) -> int:
    """Read updates from both bots and route the operator's answers.

    Only the configured chat is heard. Returns the number of handled updates.
    """
    handled = 0
    for agent in ("coder", "browser"):
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
            log.warning("telegram poll (%s) failed: %s", agent, exc)
            continue

        for update in updates:
            db.set_kv(offset_key, int(update["update_id"]) + 1)
            sender_chat = str(
                ((update.get("message") or {}).get("chat") or {}).get("id", "")
                or (
                    ((update.get("callback_query") or {}).get("message") or {}).get("chat")
                    or {}
                ).get("id", "")
            )
            if sender_chat != chat_id:
                log.warning("telegram: update ignoré (chat non autorisé %s)", sender_chat)
                continue
            order = handle_update(db, agent, update)
            if order is None:
                continue
            handled += 1
            await _render(token, chat_id, order)
            if order.get("prompt_id") and order.get("ask"):
                db.set_ask_prompt(order["ask"]["id"], order["prompt_id"])
            log.info(
                "operator (%s): %s (tâche #%s)",
                agent,
                order["kind"],
                order["ask"]["task_id"] if order.get("ask") else "?",
            )
    return handled
