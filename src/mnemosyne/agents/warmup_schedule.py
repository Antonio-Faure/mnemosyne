"""Pure warmup scheduling + goals (no stirrup/browser import — unit-testable)."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

#: Each automatic session commits to ONE goal (target + intent), like a person
#: who opens their laptop with something in mind. `weight` skews the draw so the
#: distribution is human: general/aggregator sites are common, deep archives rare.
WARMUP_GOALS: list[dict] = [
    {
        "name": "google",
        "weight": 20,
        "sites": ["https://www.google.com/"],
        "instruction": (
            "Run a few ordinary searches (history, old photos, local news, a "
            "person/place) and open one or two results. Just curious browsing."
        ),
    },
    {
        "name": "wikipedia",
        "weight": 16,
        "sites": [
            "https://fr.wikipedia.org/wiki/Histoire_de_l%27industrie",
            "https://fr.wikipedia.org/wiki/P%C3%A9trole",
            "https://fr.wikipedia.org/wiki/R%C3%A9volution_industrielle",
            "https://fr.wikipedia.org/wiki/Special:Random",
        ],
        "instruction": (
            "Research on Wikipedia: read an article, scroll, follow one or two "
            "links, stop when you've learned enough."
        ),
    },
    {
        "name": "gmail",
        "weight": 12,
        "sites": ["https://mail.google.com/mail/u/0/#inbox"],
        "instruction": (
            "Check your Gmail inbox: read the subjects/snippets of a few messages, "
            "open one or two, then leave. Nothing to send."
        ),
    },
    {
        "name": "youtube",
        "weight": 10,
        "sites": ["https://www.youtube.com/"],
        "instruction": (
            "Look for a short history/industry documentary and watch part of it, "
            "like anyone killing a few minutes."
        ),
    },
    {
        "name": "news",
        "weight": 8,
        "sites": [
            "https://www.francetvinfo.fr/",
            "https://www.lemonde.fr/",
            "https://www.ouest-france.fr/",
        ],
        "instruction": "Read the headlines and open one or two articles.",
    },
    {
        "name": "gallica",
        "weight": 6,
        "sites": ["https://gallica.bnf.fr/"],
        "instruction": "Browse Gallica: search historical photographs and open a few results.",
    },
    {
        "name": "ina",
        "weight": 5,
        "sites": ["https://www.ina.fr/"],
        "instruction": "Explore INA: read an archive page or two about history.",
    },
    {
        "name": "commons",
        "weight": 5,
        "sites": ["https://commons.wikimedia.org/wiki/Main_Page"],
        "instruction": "Look at Wikimedia Commons images of industry/history.",
    },
    {
        "name": "archive_org",
        "weight": 4,
        "sites": ["https://archive.org/"],
        "instruction": "Browse the Internet Archive for old books or photographs.",
    },
    {
        "name": "europeana",
        "weight": 3,
        "sites": ["https://www.europeana.eu/"],
        "instruction": "Search Europeana for historical images and open one.",
    },
    {
        "name": "wikidata",
        "weight": 2,
        "sites": ["https://www.wikidata.org/"],
        "instruction": "Explore a Wikidata item related to industry/history.",
    },
    {
        "name": "retronews",
        "weight": 2,
        "sites": ["https://www.retronews.fr/"],
        "instruction": "Skim old French press on RetroNews and open one article.",
    },
    {
        "name": "flickr_commons",
        "weight": 2,
        "sites": ["https://www.flickr.com/commons"],
        "instruction": "Browse the Flickr Commons for historical photographs.",
    },
    {
        "name": "loc",
        "weight": 2,
        "sites": ["https://www.loc.gov/"],
        "instruction": "Explore the Library of Congress digital collections.",
    },
    {
        "name": "openlibrary",
        "weight": 1,
        "sites": ["https://openlibrary.org/"],
        "instruction": "Browse Open Library for an old book on industry/history.",
    },
    {
        "name": "david_rumsey",
        "weight": 1,
        "sites": ["https://www.davidrumsey.com/"],
        "instruction": "Look at historical maps on the David Rumsey collection.",
    },
    {
        "name": "persee",
        "weight": 1,
        "sites": ["https://www.persee.fr/"],
        "instruction": "Skim a scholarly article on Persée about industrial history.",
    },
]


def pick_goal(rng: random.Random | None = None) -> dict:
    """Weighted draw: common sites more often, deep archives rarely."""
    rng = rng or random
    weights = [max(1, int(g.get("weight", 1))) for g in WARMUP_GOALS]
    return rng.choices(WARMUP_GOALS, weights=weights, k=1)[0]


def goal_weights() -> dict[str, int]:
    return {g["name"]: int(g.get("weight", 1)) for g in WARMUP_GOALS}


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
