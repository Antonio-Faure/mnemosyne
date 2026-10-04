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
