"""Transparent disclosure.

The agent must always state who it is, what it is doing, and where the source
code lives. `disclosure()` builds that footer from `config.identity`.

The wording is explicit: **Archivist** is the autonomous system that adds
archive image sources to **Mnemosyne**, the archive image search engine. The
project is public; the engine does not own or copy the images.
"""

from __future__ import annotations

from mnemosyne.config import IdentityConfig


def disclosure(identity: IdentityConfig, language: str | None = None) -> str:
    lang = (language or identity.language).lower()
    if lang.startswith("en"):
        return (
            f"I am {identity.agent_name}, the autonomous system that adds archive "
            f"image sources to {identity.name.capitalize()}, {identity.purpose_en}. "
            f"Open source, and transparent about the project: {identity.repo_url}"
        )
    return (
        f"Je suis {identity.agent_name}, le système autonome qui ajoute les sources "
        f"d'images d'archives à {identity.name.capitalize()}, {identity.purpose}. "
        f"Open source, transparent sur le projet : {identity.repo_url}"
    )
