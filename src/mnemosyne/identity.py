"""Transparent disclosure.

The agent must always state who it is, what it is doing, and where the source
code lives. `disclosure()` builds that footer from `config.identity`.
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
