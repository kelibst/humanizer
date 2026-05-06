"""v1.3 request body models — LintBody, ChecklistBody, ReadabilityBody, CitationsBody, RefBody."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...serve.lint import LINT_CODES

MAX_TEXT_LINT = 100_000
MAX_TEXT_CHECKLIST = 100_000
MAX_TEXT_READABILITY = 100_000
MAX_TEXT_CITATIONS = 100_000


class LintBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., max_length=MAX_TEXT_LINT)
    profile: str | None = None
    include: list[str] | None = None

    @field_validator("include")
    @classmethod
    def _check_include(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        for code in v:
            if code not in LINT_CODES:
                raise ValueError(f"unknown lint code {code!r}")
        return v


class ChecklistBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., max_length=MAX_TEXT_CHECKLIST)
    profile: str | None = None


class ReadabilityBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., max_length=MAX_TEXT_READABILITY)
    profile: str | None = None


class CitationsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., max_length=MAX_TEXT_CITATIONS)
    workspace_root: str = Field(..., min_length=1)
    profile: str | None = None


class RefBody(BaseModel):
    """``POST /v1/refs`` body. Accepts a partial Reference (id may be omitted).

    The shape mirrors :class:`Reference` but with a permissive ``id``: blank
    or absent is fine, the server fills it in.
    """

    model_config = ConfigDict(extra="forbid")
    workspace_root: str = Field(..., min_length=1)
    document_path: str | None = None
    id: str | None = None
    authors: list[str] = Field(min_length=1)
    year: int = Field(ge=1500, le=2100)
    title: str = Field(min_length=1)
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    type: str = Field(default="journal")
    raw_apa: str | None = None

    @field_validator("type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in ("journal", "book", "chapter", "web"):
            raise ValueError("type must be journal|book|chapter|web")
        return v
