from mnemosyne.config import IdentityConfig
from mnemosyne.identity import disclosure, email_body, form_message


def _identity() -> IdentityConfig:
    return IdentityConfig(
        name="mnemosyne",
        purpose="an open archive aggregator",
        repo_url="https://example.org/repo",
        language="fr",
    )


def test_disclosure_states_identity_and_repo():
    text = disclosure(_identity())
    assert "mnemosyne" in text
    assert "an open archive aggregator" in text
    assert "https://example.org/repo" in text


def test_email_body_contains_ask_and_disclosure():
    body = email_body(_identity(), "Pourriez-vous m'indiquer un accès ?")
    assert "Pourriez-vous m'indiquer un accès ?" in body
    assert "https://example.org/repo" in body


def test_form_message_contains_disclosure():
    message = form_message(_identity(), "Question")
    assert message.startswith("Question")
    assert "https://example.org/repo" in message


def test_english_variant():
    identity = IdentityConfig(language="en", repo_url="https://example.org/repo")
    assert disclosure(identity).startswith("I am")
