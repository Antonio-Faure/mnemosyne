from datetime import datetime

from mnemosyne.agents.warmup_schedule import (
    WARMUP_GOALS,
    daily_session_target,
    pick_goal,
    seconds_until_next_window,
)


def test_daily_target_is_deterministic_and_in_range():
    t = daily_session_target("2026-09-30", 1, 2)
    assert t in (1, 2)
    assert daily_session_target("2026-09-30", 1, 2) == t  # stable within the day
    assert daily_session_target("2026-09-30", 3, 3) == 3


def test_seconds_until_next_window_before_and_after():
    before = datetime(2026, 9, 30, 6, 0, 0)  # before 8h
    after = datetime(2026, 9, 30, 23, 30, 0)  # after the window
    wait_before = seconds_until_next_window(before, 8)
    wait_after = seconds_until_next_window(after, 8)
    assert 0 < wait_before <= 24 * 3600
    assert 0 < wait_after <= 24 * 3600
    # after the window, the next slot is tomorrow -> more than ~8h away
    assert wait_after > 8 * 3600


def test_goals_well_formed():
    assert WARMUP_GOALS
    for goal in WARMUP_GOALS:
        assert goal["name"]
        assert goal["instruction"]
        assert goal["sites"] and all(s.startswith("http") for s in goal["sites"])
    assert any(g["name"] == "gmail" for g in WARMUP_GOALS)
    assert pick_goal() in WARMUP_GOALS
