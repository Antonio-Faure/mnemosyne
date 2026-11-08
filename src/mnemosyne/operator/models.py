"""Shared parameter models for the operator question tool (both agents)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OperatorOption(BaseModel):
    label: str = Field(description="Short button label (2-40 chars)")
    description: str = Field(
        default="", description="One-line detail shown in the question text"
    )


class AskOperatorParams(BaseModel):
    question: str = Field(description="The question for the human operator")
    options: list[OperatorOption] = Field(
        min_length=2, max_length=6, description="2-6 answer choices"
    )


class WaitForEmailParams(BaseModel):
    """Criteria for parking the task until a matching email arrives.

    At least one of ``from_address`` / ``in_reply_to`` is required. The watcher
    reads the configured IMAP mailbox, matches new messages against these
    criteria, and injects the email into the task mailbox.
    """

    from_address: str | None = Field(
        default=None,
        description=(
            "Expected sender address (or substring of the From header), e.g. "
            "the person or institution you emailed."
        ),
    )
    subject_contains: str | None = Field(
        default=None, description="Optional substring that must appear in the subject"
    )
    in_reply_to: str | None = Field(
        default=None,
        description=(
            "Optional Message-ID of the email you sent (matched against "
            "In-Reply-To / References)"
        ),
    )
    timeout_s: int = Field(
        default=0,
        ge=0,
        le=30 * 86400,
        description="Wake the agent after this many seconds even without an email (0 = never)",
    )
    reason: str = Field(
        default="", description="Short human-readable reason, stored in the wait and events"
    )
