"""v1.2 request body models — ScoreBody, TransformBody, SuggestBody."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...backends import BACKEND_NAMES
from ...pipeline.runner import ALL_STAGES

MAX_TEXT_SCORE = 100_000
MAX_TEXT_TRANSFORM = 100_000
MAX_TEXT_SUGGEST = 30_000

VALID_STAGES = set(ALL_STAGES) | {"all"}


class ScoreBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., max_length=MAX_TEXT_SCORE)
    profile: str | None = None


class TransformBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., max_length=MAX_TEXT_TRANSFORM)
    profile: str | None = None
    stages: list[str] | None = None
    backend: str | None = None
    model: str | None = None
    seed: int | None = None

    @field_validator("stages")
    @classmethod
    def _check_stages(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        for s in v:
            if s not in VALID_STAGES:
                raise ValueError(f"unknown stage {s!r}")
        return v

    @field_validator("backend")
    @classmethod
    def _check_backend(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in BACKEND_NAMES:
            raise ValueError(f"unknown backend {v!r}")
        return v


class SuggestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., max_length=MAX_TEXT_SUGGEST)
    profile: str | None = None
    n: int = Field(default=3, ge=1, le=3)
    backend: str | None = None
    model: str | None = None

    @field_validator("backend")
    @classmethod
    def _check_backend(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in BACKEND_NAMES:
            raise ValueError(f"unknown backend {v!r}")
        return v
