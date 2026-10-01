"""Deterministic Stirrup tools backing the browser agents.

Instead of exposing dozens of low-level DOM tools (expensive and fragile), the
agent gets a small set of business-level, deterministic tools. Extraction,
persistence and wall detection are done by code.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from urllib.parse import quote

from pydantic import BaseModel, Field
from stirrup.core.models import EmptyParams, Tool, ToolProvider, ToolResult, ToolUseCountMetadata

from mnemosyne.browser.session import new_browser_session
from mnemosyne.journal import Journal
from mnemosyne.logger import get_logger
from mnemosyne.notify import Notifier
from mnemosyne.vault import Vault

log = get_logger("tools")

# JS helpers (return JSON strings so the result survives the CDP boundary).
_TEXT_JS = "(...args) => (document.body ? document.body.innerText : '').slice(0, 5000)"
_LINKS_JS = """
(...args) => JSON.stringify(
  [...document.querySelectorAll('a')]
    .map(a => a.href)
    .filter(h => h && h.startsWith('http'))
    .slice(0, 120)
)
"""
_BLOCKED_JS = """
(...args) => {
  const t = (document.body ? document.body.innerText : '').toLowerCase();
  const markers = ['captcha','vérifiez','verify you','unusual traffic',
    'se connecter','log in to','connecte-toi','too many requests','trop de demandes',
    'are you human','je ne suis pas un robot'];
  for (const m of markers) { if (t.includes(m)) return m; }
  return '';
}
"""


def _qs_js(selector: str, body: str) -> str:
    """Build a JS snippet that looks up `selector` and runs `body` with `el` bound."""
    return (
        "(...args) => { const el = document.querySelector("
        + json.dumps(selector)
        + "); if (!el) return 'no'; "
        + body
        + " }"
    )


class GotoParams(BaseModel):
    url: str = Field(description="Absolute URL to open")


class LinkParams(BaseModel):
    substring: str = Field(default="", description="Only keep links containing this substring")


class FillParams(BaseModel):
    selector: str = Field(description="CSS selector of the field")
    value: str = Field(description="Value to type")


class ClickParams(BaseModel):
    selector: str = Field(description="CSS selector of the element to click")


class UploadParams(BaseModel):
    selector: str = Field(description="CSS selector of the file input (input[type=file])")
    path: str = Field(description="Path inside the browser, under /outbox/")


class TypeParams(BaseModel):
    selector: str = Field(description="CSS selector of the field")
    text: str = Field(description="Text to type with real keyboard events")
    submit: bool = Field(default=False, description="Press Enter after typing")


class ClickTextParams(BaseModel):
    text: str = Field(description="Visible text of the button/link to click")


class TabUrlParams(BaseModel):
    url: str = Field(description="URL to open in a new tab")


class TabIndexParams(BaseModel):
    index: int = Field(description="Tab index from list_tabs()")


class WaitParams(BaseModel):
    seconds: float = Field(default=3.0, description="Seconds to wait for the page")


class RememberParams(BaseModel):
    key: str = Field(description="Credential key, e.g. 'api_key' or 'login:acme'")
    value: str = Field(description="Secret value to store in the encrypted vault")


class HumanParams(BaseModel):
    reason: str = Field(description="Why a human is needed (captcha, phone check, refusal…)")


class DoneParams(BaseModel):
    summary: str = Field(description="Short factual summary of what was achieved")

    contact_email: str | None = Field(default=None)
    contact_form_url: str | None = Field(default=None)

    api_key: str | None = Field(default=None)


class EmailParams(BaseModel):
    to: str = Field(description="Recipient email address")
    subject: str = Field(description="Email subject")
    body: str = Field(description="Email body (must include the disclosure line)")


class FormParams(BaseModel):
    url: str = Field(description="Contact form URL")
    message: str = Field(description="Message to submit (must include the disclosure)")


class InboxParams(BaseModel):
    substring: str = Field(default="", description="Only show messages matching this text")


def _ok(content: str) -> ToolResult[ToolUseCountMetadata]:
    return ToolResult(content=content, metadata=ToolUseCountMetadata())


def _fail(content: str) -> ToolResult[ToolUseCountMetadata]:
    return ToolResult(content=content, success=False, metadata=ToolUseCountMetadata())


class BrowserToolProvider(ToolProvider):
    """Deterministic browser tools shared by the onboarding and outreach agents."""

    def __init__(
        self,
        *,
        vault_path: str | Path,
        notifier: Notifier,
        journal: Journal | None = None,
        service_id: str | None = None,
        service_title: str | None = None,
    ):
        self._vault_path = Path(vault_path)
        self._notifier = notifier
        self._journal = journal
        self._service_id = service_id
        self._service_title = service_title
        self._session = None
        self._page = None
        self.finish: str | None = None
        self.outcome: dict = {}

    # ── lifecycle ────────────────────────────────────────────────────────
    async def __aenter__(self):
        self._session = new_browser_session()
        await asyncio.wait_for(self._session.start(), timeout=45)
        self._page = await asyncio.wait_for(self._session.must_get_current_page(), timeout=30)
        return self._tools()

    async def __aexit__(self, *exc):
        if self._session is not None:
            try:
                await asyncio.wait_for(self._session.stop(), timeout=30)
            except Exception:  # noqa: BLE001
                pass
            self._session = None

    # ── page helpers ─────────────────────────────────────────────────────
    async def _eval(self, js: str, timeout: float = 25.0):
        return await asyncio.wait_for(self._page.evaluate(js), timeout=timeout)

    async def _goto(self, url: str) -> None:
        try:
            await asyncio.wait_for(self._page.goto(url), timeout=40)
            await asyncio.sleep(2.0)
        except Exception as exc:  # noqa: BLE001
            log.warning("goto %s failed: %s", url[:80], exc)

    async def _text(self) -> str:
        try:
            return await self._eval(_TEXT_JS) or ""
        except Exception:  # noqa: BLE001
            return ""

    async def _blocked(self) -> str | None:
        try:
            reason = await self._eval(_BLOCKED_JS)
            return reason or None
        except Exception:  # noqa: BLE001
            return None

    async def _request_human(self, reason: str) -> str:
        message = f"human needed: {reason}"
        # Ask the operator on Telegram; their reply is read by the heartbeat.
        await self._notifier.ask(
            f"Intervention requise sur le navigateur de l'agent.\n{reason}"
        )
        if self._journal is not None:
            self._journal.append(f"escalade humaine : {reason}", level="warn", source="agent")
            if self._service_id:
                self._journal.append_service(
                    self._service_id,
                    f"escalade humaine : {reason}",
                    title=self._service_title,
                    level="warn",
                    source="agent",
                )
        return message

    # ── tool builders ────────────────────────────────────────────────────
    def _common_tools(self) -> list[Tool]:
        async def goto_exec(p: GotoParams):
            await self._goto(p.url)
            reason = await self._blocked()
            if reason:
                return _fail(f"page bloque, mur detecte ({reason}). Utilise request_human.")
            return _ok(f"opened {p.url}\n\n{(await self._text())[:2000]}")

        async def read_exec(_: EmptyParams):
            reason = await self._blocked()
            if reason:
                return _fail(f"mur detecte ({reason}).")
            try:
                url = await self._page.get_url()
            except Exception:  # noqa: BLE001
                url = "?"
            return _ok(f"[url] {url}\n\n" + ((await self._text())[:4000] or "(page vide)"))

        async def links_exec(p: LinkParams):
            try:
                links = json.loads(await self._eval(_LINKS_JS) or "[]")
            except Exception:  # noqa: BLE001
                links = []
            if p.substring:
                links = [lnk for lnk in links if p.substring.lower() in lnk.lower()]
            return _ok("\n".join(links[:60]) or "(aucun lien)")

        async def fill_exec(p: FillParams):
            js = _qs_js(
                p.selector,
                "el.focus(); el.value = " + json.dumps(p.value) + ";"
                " el.dispatchEvent(new Event('input', {bubbles:true}));"
                " el.dispatchEvent(new Event('change', {bubbles:true})); return 'ok';",
            )
            try:
                res = await self._eval(js)
            except Exception as exc:  # noqa: BLE001
                return _fail(f"fill failed: {exc}")
            return _ok(f"fill {p.selector}: {res}")

        async def click_exec(p: ClickParams):
            # prefer a real CDP mouse click (works with React/disabled logic)
            try:
                elements = await self._page.get_elements_by_css_selector(p.selector)
            except Exception:  # noqa: BLE001
                elements = []
            if elements:
                try:
                    await elements[0].click()
                    await asyncio.sleep(1.5)
                    return _ok(f"clicked {p.selector} (mouse)")
                except Exception as exc:  # noqa: BLE001
                    log.debug("mouse click failed, JS fallback: %s", exc)
            js = _qs_js(p.selector, "el.click(); return 'ok';")
            try:
                res = await self._eval(js)
                await asyncio.sleep(1.5)
            except Exception as exc:  # noqa: BLE001
                return _fail(f"click failed: {exc}")
            return _ok(f"click {p.selector}: {res}")

        async def enter_exec(p: ClickParams):
            js = _qs_js(
                p.selector,
                "el.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter',bubbles:true}));"
                " el.form && el.form.requestSubmit && el.form.requestSubmit(); return 'ok';",
            )
            try:
                res = await self._eval(js)
            except Exception as exc:  # noqa: BLE001
                return _fail(f"enter failed: {exc}")
            return _ok(f"enter {p.selector}: {res}")

        async def upload_exec(p: UploadParams):
            if not p.path.startswith("/outbox/"):
                return _fail("upload path must be under /outbox/ (browser-side)")
            try:
                elements = await self._page.get_elements_by_css_selector(p.selector)
            except Exception as exc:  # noqa: BLE001
                return _fail(f"selector failed: {exc}")
            if not elements:
                return _fail(f"no element matches {p.selector}")
            el = elements[0]
            try:
                await el._client.send_raw(
                    "DOM.setFileInputFiles",
                    {"files": [p.path], "backendNodeId": el._backend_node_id},
                    session_id=el._session_id,
                )
            except Exception as exc:  # noqa: BLE001
                return _fail(f"upload failed: {exc}")
            await asyncio.sleep(2.0)
            return _ok(f"uploaded {p.path} to {p.selector}")

        async def type_exec(p: TypeParams):
            try:
                elements = await self._page.get_elements_by_css_selector(p.selector)
            except Exception as exc:  # noqa: BLE001
                return _fail(f"selector failed: {exc}")
            if not elements:
                return _fail(f"no element matches {p.selector}")
            el = elements[0]
            try:
                await el.focus()
                await el.fill(p.text)  # browser-use uses real CDP key events
                if p.submit:
                    for ev in ("keyDown", "keyUp"):
                        await el._client.send_raw(
                            "Input.dispatchKeyEvent",
                            {"type": ev, "windowsVirtualKeyCode": 13, "key": "Enter",
                             "nativeVirtualKeyCode": 13},
                            session_id=el._session_id,
                        )
            except Exception as exc:  # noqa: BLE001
                return _fail(f"type failed: {exc}")
            await asyncio.sleep(1.5)
            return _ok(f"typed into {p.selector}: {p.text!r}")

        async def click_text_exec(p: ClickTextParams):
            js = (
                "(...args) => { const t = " + json.dumps(p.text.lower()) + ";"
                " const sel = 'button,a,[role=button],input[type=submit],div';"
                " const els = [...document.querySelectorAll(sel)];"
                " const el = els.find(e => (e.innerText||e.value||'')"
                ".trim().toLowerCase().includes(t));"
                " if (!el) return 'no';"
                " (el.closest('button,a,[role=button],input[type=submit]') || el).click();"
                " return 'ok'; }"
            )
            try:
                res = await self._eval(js)
            except Exception as exc:  # noqa: BLE001
                return _fail(f"click_text failed: {exc}")
            await asyncio.sleep(2.0)
            return _ok(f"click_text {p.text!r}: {res}")

        async def new_tab_exec(p: TabUrlParams):
            res = self._session.new_page(p.url)
            page = await res if inspect.isawaitable(res) else res
            self._page = page
            await asyncio.sleep(2.0)
            return _ok(f"new tab opened: {p.url}")

        async def list_tabs_exec(_: EmptyParams):
            pages = await self._session.get_pages()
            lines = []
            for i, pg in enumerate(pages):
                try:
                    url = await pg.get_url()
                except Exception:  # noqa: BLE001
                    url = "?"
                mark = " <-current" if pg is self._page else ""
                lines.append(f"{i}. {url}{mark}")
            return _ok("\n".join(lines) or "(no tab)")

        async def switch_tab_exec(p: TabIndexParams):
            pages = await self._session.get_pages()
            if p.index < 0 or p.index >= len(pages):
                return _fail(f"bad tab index {p.index} (have {len(pages)})")
            self._page = pages[p.index]
            await asyncio.sleep(0.5)
            return _ok(f"switched to tab {p.index}")

        async def close_tab_exec(_: EmptyParams):
            try:
                await self._session.close_page(self._page)
            except Exception as exc:  # noqa: BLE001
                return _fail(f"close tab failed: {exc}")
            pages = await self._session.get_pages()
            if pages:
                self._page = pages[0]
            return _ok("tab closed")

        async def wait_exec(p: WaitParams):
            await asyncio.sleep(min(max(p.seconds, 0.5), 60.0))
            return _ok(f"waited {p.seconds:.0f}s")

        async def blocked_exec(_: EmptyParams):
            reason = await self._blocked()
            return _ok(reason or "no wall detected")

        async def remember_exec(p: RememberParams):
            try:
                Vault(self._vault_path).set(p.key, p.value)
            except Exception as exc:  # noqa: BLE001
                return _fail(f"vault write failed: {exc}")
            return _ok(f"stored '{p.key}' in the vault")

        async def human_exec(p: HumanParams):
            msg = await self._request_human(p.reason)
            return _ok(msg)

        async def done_exec(p: DoneParams):
            self.finish = p.summary
            self.outcome = {
                "summary": p.summary,
                "api_key": p.api_key,
                "contact_email": p.contact_email,
                "contact_form_url": p.contact_form_url,
            }
            if p.api_key:
                try:
                    Vault(self._vault_path).set("api_key", p.api_key)
                except Exception:  # noqa: BLE001
                    pass
            return _ok("task marked done")

        return [
            Tool(name="goto", description="Open a URL.", parameters=GotoParams, executor=goto_exec),
            Tool(name="read_page", description="Read the current page text.",
                 parameters=EmptyParams, executor=read_exec),
            Tool(name="list_links", description="List links on the page.",
                 parameters=LinkParams, executor=links_exec),
            Tool(name="fill", description="Set a field value by CSS selector.",
                 parameters=FillParams, executor=fill_exec),
            Tool(name="click", description="Click an element by CSS selector.",
                 parameters=ClickParams, executor=click_exec),
            Tool(name="press_enter", description="Press Enter on a field.",
                 parameters=ClickParams, executor=enter_exec),
            Tool(name="upload_file",
                 description="Set a file on an input[type=file] (path under /outbox/).",
                 parameters=UploadParams, executor=upload_exec),
            Tool(name="type_text",
                 description="Type text with real keyboard events (React/combobox fields).",
                 parameters=TypeParams, executor=type_exec),
            Tool(name="click_text",
                 description="Click a button/link by its visible text.",
                 parameters=ClickTextParams, executor=click_text_exec),
            Tool(name="new_tab", description="Open a URL in a new tab and switch to it.",
                 parameters=TabUrlParams, executor=new_tab_exec),
            Tool(name="list_tabs", description="List open tabs (index + url).",
                 parameters=EmptyParams, executor=list_tabs_exec),
            Tool(name="switch_tab", description="Switch to a tab by index.",
                 parameters=TabIndexParams, executor=switch_tab_exec),
            Tool(name="close_tab", description="Close the current tab.",
                 parameters=EmptyParams, executor=close_tab_exec),
            Tool(name="wait", description="Wait a few seconds for the page to settle.",
                 parameters=WaitParams, executor=wait_exec),
            Tool(name="blocked_status", description="Report any captcha/login/rate wall.",
                 parameters=EmptyParams, executor=blocked_exec),
            Tool(name="remember", description="Store a credential in the encrypted vault.",
                 parameters=RememberParams, executor=remember_exec),
            Tool(name="request_human", description="Escalate to the operator.",
                 parameters=HumanParams, executor=human_exec),
            Tool(name="task_done", description="Finish and summarise the outcome.",
                 parameters=DoneParams, executor=done_exec),
        ]

    def _tools(self) -> list[Tool]:
        return self._common_tools()


class OutreachToolProvider(BrowserToolProvider):
    """Adds Gmail (via the browser) and web contact-form tools."""

    def _tools(self) -> list[Tool]:
        async def email_exec(p: EmailParams):
            reason = await self._blocked()
            if reason:
                return _fail(f"mur detecte ({reason}); utilise request_human.")
            url = (
                "https://mail.google.com/mail/?view=cm&fs=1"
                f"&to={quote(p.to)}&su={quote(p.subject)}&body={quote(p.body)}"
            )
            await self._goto(url)
            # Gmail auto-opens the composer; click Send by its aria-label.
            js = """
            (...args) => {
              const btns = [...document.querySelectorAll('[role="button"],div[aria-label]')];
              const label = (b) => (b.getAttribute('aria-label') || b.innerText || '').trim();
              const send = btns.find(b => /^(send|envoyer)$/i.test(label(b)));
              if (send) { send.click(); return 'sent'; }
              return 'no-send-button';
            }
            """
            try:
                res = await self._eval(js)
            except Exception as exc:  # noqa: BLE001
                return _fail(f"send failed: {exc}")
            if res == "sent":
                return _ok(f"email sent to {p.to}")
            return _fail(f"composer opened but send button not found ({res})")

        async def form_exec(p: FormParams):
            await self._goto(p.url)
            reason = await self._blocked()
            if reason:
                return _fail(f"mur detecte ({reason}); utilise request_human.")
            js = (
                "(...args) => {\n"
                "  const msg = " + json.dumps(p.message) + ";\n"
                "  const sel = 'textarea, input[type=text], input[name*=message i], ' +\n"
                "              'input[name*=msg i]';\n"
                "  const fields = [...document.querySelectorAll(sel)];\n"
                "  if (!fields.length) return 'no-field';\n"
                "  const el = fields[0];\n"
                "  el.focus(); el.value = msg;\n"
                "  el.dispatchEvent(new Event('input', {bubbles:true}));\n"
                "  el.dispatchEvent(new Event('change', {bubbles:true}));\n"
                "  const sel2 = 'button[type=submit], input[type=submit]';\n"
                "  const submit = document.querySelector(sel2);\n"
                "  if (submit) { submit.click(); return 'submitted'; }\n"
                "  return 'filled-no-submit';\n"
                "}"
            )
            try:
                res = await self._eval(js)
            except Exception as exc:  # noqa: BLE001
                return _fail(f"form failed: {exc}")
            return _ok(f"contact form: {res}")

        async def inbox_exec(p: InboxParams):
            await self._goto("https://mail.google.com/mail/u/0/#inbox")
            text = await self._text()
            if p.substring:
                lines = [ln for ln in text.splitlines() if p.substring.lower() in ln.lower()]
                text = "\n".join(lines[:40]) or "(aucun message correspondant)"
            return _ok(text[:3000])

        return [
            *self._common_tools(),
            Tool(name="send_email", description="Send an email from the agent's Gmail.",
                 parameters=EmailParams, executor=email_exec),
            Tool(name="submit_contact_form", description="Submit a web contact form.",
                 parameters=FormParams, executor=form_exec),
            Tool(name="read_inbox", description="Read the agent's Gmail inbox.",
                 parameters=InboxParams, executor=inbox_exec),
        ]
