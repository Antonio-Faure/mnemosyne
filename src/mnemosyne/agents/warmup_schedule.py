"""Pure warmup scheduling + goals (no stirrup/browser import — unit-testable)."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

#: Each automatic session commits to ONE goal (target + intent), like a person
#: who opens their laptop with something in mind.
WARMUP_GOALS: list[dict] = [
    {
        "name": "gmail",
        "sites": ["https://mail.google.com/mail/u/0/#inbox"],
        "instruction": (
            "Check your Gmail inbox: read the subjects/snippets of a few messages, "
            "open one or two, then leave. Nothing to send."
        ),
    },
    {
        "name": "wikipedia",
        "sites": [
            "https://fr.wikipedia.org/wiki/Histoire_de_l%27industrie",
            "https://fr.wikipedia.org/wiki/P%C3%A9trole",
        ],
        "instruction": (
            "Research a history topic on Wikipedia: read an article, scroll, follow "
            "one or two links, and stop when you've learned enough."
        ),
    },
    {
        "name": "gallica",
        "sites": ["https://gallica.bnf.fr/"],
        "instruction": "Browse Gallica: search historical photographs and open a few results.",
    },
    {
        "name": "ina",
        "sites": ["https://www.ina.fr/"],
        "instruction": "Explore INA: read an archive page or two about history.",
    },
    {
        "name": "commons",
        "sites": ["https://commons.wikimedia.org/wiki/Main_Page"],
        "instruction": "Look at Wikimedia Commons images of industry/history.",
    },
    {
        "name": "europeana",
        "sites": ["https://www.europeana.eu/"],
        "instruction": "Search Europeana for historical images and open one.",
    },
    {
        "name": "archive_org",
        "sites": ["https://archive.org/"],
        "instruction": "Browse the Internet Archive for old books or photographs.",
    },
]


def pick_goal(rng: random.Random | None = None) -> dict:
    return (rng or random).choice(WARMUP_GOALS)


def daily_session_target(day: str, lo: int, hi: int) -> int:
    """Deterministic per-day target (1 or 2 sessions) so all ticks agree."""
    return random.Random(day).randint(lo, max(lo, hi))


def seconds_until_next_window(now: datetime, start_hour: int) -> int:
    """Seconds until a random time inside the next daily window."""
    target = now.replace(
        hour=start_hour,
        minute=random.randint(0, 59),
        second=random.randint(0, 59),
        microsecond=0,
    )
    if target <= now:
        target += timedelta(days=1)
    return max(60, int((target - now).total_seconds()))
