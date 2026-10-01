"""Pure warmup scheduling + goals (no stirrup/browser import — unit-testable)."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

#: Each automatic session commits to ONE goal (target + intent). `weight` skews
#: the draw so the distribution is human: general/aggregator sites are common,
#: deep archives rare.
#:
#: IMPORTANT: this is an LLM driving a browser — it can only *read text and look
#: at still images*. Only list text/image sites it can actually process. Never
#: add video/streaming sites (YouTube, Twitch…): "watching" is meaningless for
#: the agent and just parks a tab. The warmup's purpose is a *credible browsing
#: history* for the account, not pretending to be human.
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
            "https://fr.wikipedia.org/wiki/Industrialisation",
            "https://fr.wikipedia.org/wiki/P%C3%A9trole",
            "https://fr.wikipedia.org/wiki/Affiche",
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
        "name": "news",
        "weight": 8,
        "sites": [
            "https://www.francetvinfo.fr/",
            "https://www.lemonde.fr/",
            "https://www.lemonde.fr/archives/",
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


def seconds_until_next_slot(
    now: datetime,
    start_hour: int,
    end_hour: int,
    min_gap_min: int = 45,
    max_gap_min: int = 180,
) -> int:
    """Random delay for the next session, kept *inside* the daily window.

    Falls back to the next day's window when there is no room left today.
    """
    end = now.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    room = int((end - now).total_seconds()) - 600  # 10 min margin
    lo = min_gap_min * 60
    if room < lo:
        return seconds_until_next_window(now, start_hour)
    hi = max(lo, min(max_gap_min * 60, room))
    return random.randint(lo, hi)
