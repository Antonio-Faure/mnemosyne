"""Telegram alerts + operator dialogue for human-in-the-loop.

Two-way: the agent sends alerts/questions, and the heartbeat polls the operator's
replies (any message to the bot) so the operator can answer or steer the agent.
"""

from __future__ import annotations

import os

import httpx

from mnemosyne.config import TelegramConfig
from mnemosyne.logger import get_logger

log = get_logger("notify")

_BASE = "https://api.telegram.org"


class Notifier:
    def __init__(self, config: TelegramConfig):
        self.config = config
        self.token = os.environ.get(config.bot_token_env, "")
        self.chat_id = os.environ.get(config.chat_id_env, "")

    @property
    def enabled(self) -> bool:
        return self.config.enabled and bool(self.token) and bool(self.chat_id)

    async def send(self, text: str, level: str = "info") -> bool:
        prefix = {"info": "ℹ️", "warn": "⚠️", "error": "🛑", "blocked": "🚧", "ask": "❓"}.get(
            level, "•"
        )
        message = f"{prefix} mnemosyne — {text}"
        if not self.enabled:
            log.warning("notify (telegram disabled): %s", message)
            return False
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{_BASE}/bot{self.token}/sendMessage",
                    json={"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"},
                )
                resp.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            log.error("telegram send failed: %s", exc)
            return False

    async def get_me(self) -> dict | None:
        if not self.token:
            return None
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{_BASE}/bot{self.token}/getMe")
                data = resp.json()
            return data.get("result") if data.get("ok") else None
        except httpx.HTTPError:
            return None

    async def get_updates(self, offset: int | None = None, timeout: int = 0) -> list[dict]:
        if not self.token:
            return []
        params: dict[str, object] = {"timeout": timeout, "allowed_updates": '["message"]'}
        if offset is not None:
            params["offset"] = offset
        try:
            async with httpx.AsyncClient(timeout=timeout + 10) as client:
                resp = await client.get(f"{_BASE}/bot{self.token}/getUpdates", params=params)
                data = resp.json()
            return data.get("result", []) if data.get("ok") else []
        except httpx.HTTPError as exc:
            log.warning("telegram getUpdates failed: %s", exc)
            return []

    async def poll(self, offset: int | None = None) -> tuple[list[str], int | None]:
        """Return (operator messages, next offset). Only the configured chat."""
        updates = await self.get_updates(offset=offset)
        if not updates:
            return [], offset
        next_offset = offset
        messages: list[str] = []
        for update in updates:
            next_offset = max(int(update.get("update_id", 0)) + 1, next_offset or 0)
            msg = update.get("message") or {}
            chat = msg.get("chat") or {}
            text = (msg.get("text") or "").strip()
            # Ignore Telegram bot commands (/start, /help…) — keep real messages.
            if text and not text.startswith("/") and str(chat.get("id")) == str(self.chat_id):
                messages.append(text)
        return messages, next_offset
