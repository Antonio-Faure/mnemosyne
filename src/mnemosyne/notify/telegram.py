"""Telegram alerts for human-in-the-loop escalation (captcha, refusal, block)."""

from __future__ import annotations

import os

import httpx

from mnemosyne.config import TelegramConfig
from mnemosyne.logger import get_logger

log = get_logger("notify")


class Notifier:
    def __init__(self, config: TelegramConfig):
        self.config = config
        self.token = os.environ.get(config.bot_token_env, "")
        self.chat_id = os.environ.get(config.chat_id_env, "")

    @property
    def enabled(self) -> bool:
        return self.config.enabled and bool(self.token) and bool(self.chat_id)

    async def send(self, text: str, level: str = "info") -> bool:
        prefix = {"info": "ℹ️", "warn": "⚠️", "error": "🛑", "blocked": "🚧"}.get(level, "•")
        message = f"{prefix} mnemosyne — {text}"
        if not self.enabled:
            log.warning("notify (telegram disabled): %s", message)
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    url, json={"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}
                )
                resp.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            log.error("telegram send failed: %s", exc)
            return False
