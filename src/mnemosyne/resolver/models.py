"""Pydantic contract for the resolver golden dataset.

The JSONL schema is documented in `docs/RESOLVER-ADVERSARIAL.md` and
`schemas/golden_sentence.schema.json`. Extra keys are preserved so an
annotation tool can add fields without breaking the importer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

GoldenStatus = Literal["match", "partial", "no_match", "ambiguous"]


def _http_url(value: str) -> str:
    value = value.strip()
    if not value.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")
    return value


class GoldenVideo(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    title: str = ""
    channel: str = ""
    published_at: str | None = None

    @field_validator("url")
    @classmethod
    def _url_is_http(cls, value: str) -> str:
        return _http_url(value)


class GoldenSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)
    text: str = Field(min_length=1)


class GoldenClaim(BaseModel):
    model_config = ConfigDict(extra="allow")

    when: str | None = None
    where: str | None = None
    who: list[str] = Field(default_factory=list)
    event: str | None = None
    visual_intent: str | None = None


class GoldenImage(BaseModel):
    model_config = ConfigDict(extra="allow")

    url: str = Field(min_length=1)
    why: str = Field(min_length=1)
    source_id: str | None = None
    source_asset_id: str | None = None

    @field_validator("url")
    @classmethod
    def _url_is_http(cls, value: str) -> str:
        return _http_url(value)


class HardNegative(BaseModel):
    model_config = ConfigDict(extra="allow")

    url: str = Field(min_length=1)
    why_wrong: str = Field(min_length=1)
    source_id: str | None = None
    source_asset_id: str | None = None

    @field_validator("url")
    @classmethod
    def _url_is_http(cls, value: str) -> str:
        return _http_url(value)


class GoldenGold(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: GoldenStatus
    images: list[GoldenImage] = Field(default_factory=list)
    hard_negatives: list[HardNegative] = Field(default_factory=list)


class GoldenSentence(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    video: GoldenVideo
    segment: GoldenSegment
    claim: GoldenClaim | None = None
    gold: GoldenGold
    notes: str = ""
    annotator: str = ""
