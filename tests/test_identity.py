from mnemosyne.config import IdentityConfig
from mnemosyne.identity import disclosure


def _identity() -> IdentityConfig:
    return IdentityConfig(
        name="mnemosyne",
        agent_name="Archivist",
        purpose="le moteur de recherche d'images d'archives",
        purpose_en="the archive image search engine",
        repo_url="https://example.org/repo",
        language="fr",
    )


def test_disclosure_states_identity_and_repo():
    text = disclosure(_identity())
    assert "Archivist" in text
    assert "Mnemosyne" in text
    assert "moteur de recherche d'images d'archives" in text
    assert "https://example.org/repo" in text


def test_english_variant():
    identity = IdentityConfig(language="en", repo_url="https://example.org/repo")
    text = disclosure(identity)
    assert text.startswith("I am Archivist")
    assert "Mnemosyne" in text
    assert "archive image search engine" in text
