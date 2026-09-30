"""Transparent disclosure used in every outbound email / contact form.

The agent must always state who it is, what it is doing, and where the source
code lives. These helpers build that footer from `config.identity`.
"""

from __future__ import annotations

from mnemosyne.config import IdentityConfig


def disclosure(identity: IdentityConfig, language: str | None = None) -> str:
    lang = (language or identity.language).lower()
    if lang.startswith("en"):
        return (
            f"I am {identity.name}, an autonomous software agent building {identity.purpose}. "
            f"Open source and open about my goals: {identity.repo_url}"
        )
    return (
        f"Je suis {identity.name}, un agent logiciel autonome qui développe "
        f"{identity.purpose}. Open source, transparent sur mes objectifs : {identity.repo_url}"
    )


def greeting(identity: IdentityConfig, language: str | None = None) -> str:
    lang = (language or identity.language).lower()
    if lang.startswith("en"):
        return "Hello,"
    return "Bonjour,"


def email_body(
    identity: IdentityConfig,
    ask: str,
    *,
    language: str | None = None,
) -> str:
    """Full email body: greeting, the request, then the transparency footer."""
    return (
        f"{greeting(identity, language)}\n\n"
        f"{ask.strip()}\n\n"
        f"—\n{disclosure(identity, language)}\n"
    )


def form_message(
    identity: IdentityConfig,
    ask: str,
    *,
    language: str | None = None,
) -> str:
    """Shorter variant for web contact forms, disclosure included."""
    return f"{ask.strip()}\n\n{disclosure(identity, language)}"
