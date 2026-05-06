"""v1.4 request body models — RenderPromptBody, InspectBody, ReviewerBody, LlmRunBody, BenchmarkBody."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...backends import BACKEND_NAMES
from ...scoring.external import KNOWN_DETECTORS

MAX_TEXT_PROMPT = 50_000
MAX_TEXT_INSPECT = 100_000
MAX_TEXT_REVIEWER = 200_000
MAX_TEXT_LLM_RUN = 200_000
MAX_TEXT_BENCHMARK = 100_000


class RenderPromptBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_id: str = Field(..., min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)


class InspectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section_text: str = Field(..., max_length=MAX_TEXT_INSPECT)
    section_type: str = Field(..., min_length=1)


class ReviewerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_text: str = Field(..., max_length=MAX_TEXT_REVIEWER)
    persona: str = Field(...)

    @field_validator("persona")
    @classmethod
    def _check_persona(cls, v: str) -> str:
        if v not in ("r1", "r2"):
            raise ValueError("persona must be 'r1' or 'r2'")
        return v


class LlmRunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(..., max_length=MAX_TEXT_LLM_RUN)
    backend: str = Field(...)
    model: str | None = None

    @field_validator("backend")
    @classmethod
    def _check_backend(cls, v: str) -> str:
        if v not in BACKEND_NAMES:
            raise ValueError(f"unknown backend {v!r}")
        return v


class BenchmarkBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., max_length=MAX_TEXT_BENCHMARK)
    detectors: list[str] = Field(default_factory=list)
    profile: str | None = None

    @field_validator("detectors")
    @classmethod
    def _check_detectors(cls, v: list[str]) -> list[str]:
        for d in v:
            if d not in KNOWN_DETECTORS:
                raise ValueError(f"unknown detector {d!r}")
        return v
