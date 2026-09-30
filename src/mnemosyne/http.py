"""Async HTTP client with polite retries, backoff and governor pacing."""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Any

import httpx

from mnemosyne.logger import get_logger

if TYPE_CHECKING:
    from mnemosyne.reputation.governor import Governor

log = get_logger("http")

RETRY_STATUS = {429, 500, 502, 503, 504}


def default_contact() -> str:
    return os.environ.get("MNEMOSYNE_CONTACT", "mnemosyne-agent (https://github.com/Antonio-Faure/mnemosyne)")


def domain_of(url: str) -> str:
    try:
        return httpx.URL(url).host or ""
    except Exception:
        return ""


class HttpClient:
    def __init__(
        self,
        contact: str | None = None,
        governor: Governor | None = None,
        timeout: float = 30.0,
        retries: int = 3,
    ):
        self.contact = contact or default_contact()
        self.governor = governor
        self.retries = retries
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": self.contact, "Accept-Language": "fr,en;q=0.8"},
        )

    async def __aenter__(self) -> HttpClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        accept: str = "application/json",
    ) -> httpx.Response:
        merged = {"Accept": accept}
        if headers:
            merged.update(headers)
        domain = domain_of(url)
        last_exc: Exception | None = None

        for attempt in range(self.retries + 1):
            if self.governor is not None:
                await self.governor.acquire(domain)
            try:
                resp = await self._client.get(url, params=params, headers=merged)
            except httpx.HTTPError as exc:  # network error
                last_exc = exc
                await self._backoff(attempt)
                continue

            if resp.status_code in RETRY_STATUS:
                if self.governor is not None and resp.status_code in (403, 429):
                    await self.governor.report_block(domain)
                retry_after = _retry_after(resp)
                log.debug("HTTP %s on %s (attempt %d)", resp.status_code, domain, attempt + 1)
                await self._backoff(attempt, retry_after)
                last_exc = httpx.HTTPStatusError(
                    f"status {resp.status_code}", request=resp.request, response=resp
                )
                continue

            resp.raise_for_status()
            return resp

        raise last_exc or RuntimeError(f"GET failed: {url}")

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        resp = await self.get(url, accept="application/json", **kwargs)
        return resp.json()

    async def get_text(self, url: str, **kwargs: Any) -> str:
        resp = await self.get(url, accept="text/plain, text/html;q=0.9, */*;q=0.8", **kwargs)
        return resp.text

    async def get_bytes(self, url: str, **kwargs: Any) -> bytes:
        resp = await self.get(url, accept="image/*, */*;q=0.5", **kwargs)
        return resp.content

    async def _backoff(self, attempt: int, retry_after: float | None = None) -> None:
        if attempt >= self.retries:
            return
        delay = retry_after if retry_after is not None else min(2.0 * (attempt + 1), 15.0)
        await asyncio.sleep(min(delay, 30.0))


def _retry_after(resp: httpx.Response) -> float | None:
    value = resp.headers.get("Retry-After")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None
