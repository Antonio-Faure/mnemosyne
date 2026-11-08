"""Telegram alerts (send-only).

Agent questionnaires are a separate channel: `mnemosyne.operator.telegram`
uses one bot per agent and only routes a reply to a pending question (button or
reply to the question/ForceReply prompt). Random messages to the alert bot are
never consumed and never enter a session context.
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
