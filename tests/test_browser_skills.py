"""The browser agent receives the harness interaction skills and email writing."""

from pathlib import Path

from mnemosyne.agents.browser_agent import _load_skills


def test_email_writing_skill_is_injected():
    skills = _load_skills(Path(__file__).resolve().parents[1])
    assert "### email-writing" in skills
    assert "institution" in skills
    assert "Après l'envoi" in skills
