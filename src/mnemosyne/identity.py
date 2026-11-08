"""Transparent disclosure.

The agent must always state who it is, what it is doing, and where the source
code lives. `disclosure()` builds that footer from `config.identity`.

The wording never leads with "autonomous agent": a non-technical archivist
reads "AI" as a risk. It leads with the project and what it does, and presents
the software as the project's assistant.
"""

from __future__ import annotations

from mnemosyne.config import IdentityConfig


def disclosure(identity: IdentityConfig, language: str | None = None) -> str:
    lang = (language or identity.language).lower()
    if lang.startswith("en"):
        return (
            f"I am the software assistant of {identity.name}, {identity.purpose}. "
            f"Open source, and transparent about the project: {identity.repo_url}"
        )
    return (
        f"Je suis l'assistant logiciel du projet {identity.name}, "
        f"{identity.purpose}. Open source, transparent sur le projet : {identity.repo_url}"
    )
