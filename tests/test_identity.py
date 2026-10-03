from mnemosyne.config import IdentityConfig
from mnemosyne.identity import disclosure


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


def test_english_variant():
    identity = IdentityConfig(language="en", repo_url="https://example.org/repo")
    assert disclosure(identity).startswith("I am")
