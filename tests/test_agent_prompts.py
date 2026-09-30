from mnemosyne.agents.prompts import (
    onboarding_system,
    onboarding_task,
    outreach_system,
    outreach_task,
)
from mnemosyne.config import IdentityConfig
from mnemosyne.models import Protocol, SourceDescriptor


def _descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        id="acme_archives",
        name="Acme Archives",
        institution="Acme Corp",
        protocol=Protocol.EMAIL,
        base_url="https://archives.acme.example",
        notes="Ask the documentation department.",
    )


def _identity() -> IdentityConfig:
    return IdentityConfig(
        name="mnemosyne",
        purpose="an open historical image index",
        repo_url="https://example.org/mnemosyne",
        language="fr",
    )


def test_onboarding_system_has_identity_and_portal():
    system = onboarding_system(_descriptor(), _identity())
    assert "Acme Archives" in system
    assert "https://archives.acme.example" in system
    assert "https://example.org/mnemosyne" in system


def test_onboarding_task_mentions_disclosure():
    task = onboarding_task(_descriptor(), _identity())
    assert "mnemosyne" in task
    assert "https://example.org/mnemosyne" in task


def test_outreach_system_discloses_identity():
    system = outreach_system(_identity())
    assert "https://example.org/mnemosyne" in system
    assert "MUST include this disclosure" in system


def test_outreach_task_contains_ask_and_disclosure():
    task = outreach_task(
        _descriptor(),
        "Puis-je indexer vos images ?",
        _identity(),
        contact_email="doc@acme.example",
        contact_form_url="https://archives.acme.example/contact",
    )
    assert "Puis-je indexer vos images ?" in task
    assert "doc@acme.example" in task
    assert "https://archives.acme.example/contact" in task
    assert "https://example.org/mnemosyne" in task
