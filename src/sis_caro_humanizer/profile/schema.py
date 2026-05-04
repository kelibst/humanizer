from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PunctTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: float = Field(ge=0)
    hard_cap: float | None = Field(default=None, ge=0)


class SentenceShape(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mean_words: float = 19.0
    std_words: float = 10.0
    pct_short_lt10: float = Field(default=0.18, ge=0, le=1)
    pct_long_gt35: float = Field(default=0.08, ge=0, le=1)
    max_consecutive_similar: int = 2


class Vocabulary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    must_use: list[str] = Field(default_factory=list)
    never_use: list[str] = Field(default_factory=list)
    preferred_swaps: dict[str, list[str]] = Field(default_factory=dict)
    repetition_tolerance: Literal["low", "medium", "high"] = "high"


class BlupperProbabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comma_splice_rate: float = Field(default=0.15, ge=0, le=1)
    data_singular_verb: float = Field(default=0.50, ge=0, le=1)
    less_for_fewer: float = Field(default=0.20, ge=0, le=1)
    which_for_that: float = Field(default=0.30, ge=0, le=1)
    oxford_comma_rate: float = Field(default=0.55, ge=0, le=1)
    start_with_and_but: float = Field(default=0.08, ge=0, le=1)
    article_drop_ghanaian: float = Field(default=0.0, ge=0, le=1)
    tense_shift_past_present: float = Field(default=0.10, ge=0, le=1)


class HedgeMix(BaseModel):
    model_config = ConfigDict(extra="forbid")
    formal_share: float = Field(default=0.55, ge=0, le=1)
    informal_share: float = Field(default=0.45, ge=0, le=1)
    formal_pool: list[str] = Field(
        default_factory=lambda: ["may", "might", "could", "suggests", "appears to"]
    )
    informal_pool: list[str] = Field(
        default_factory=lambda: [
            "seems like",
            "looks like",
            "hard to say with certainty",
            "one would think",
        ]
    )


class ParagraphShape(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic_sentence_perfection_max: float = Field(default=0.40, ge=0, le=1)
    thinking_marker_rate: float = Field(default=0.15, ge=0, le=1)
    thinking_markers: list[str] = Field(
        default_factory=lambda: [
            "Interestingly,",
            "What stands out here is that",
            "This raises an important question:",
            "Looking at the data above,",
            "From the table, it is clear that",
            "Of course, this does not mean that",
        ]
    )
    length_cv_min: float = Field(default=0.45, ge=0)


Dialect = Literal["ghanaian", "british", "american", "neutral"]
Register = Literal["academic", "technical", "casual"]


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = 1
    profile_name: str
    extracted_from: list[str] = Field(default_factory=list)
    extracted_at: date | None = None
    word_count_basis: int = 0

    domain_register: Register = "academic"
    dialect: Dialect = "neutral"
    seed: int = 1337

    # v1.2 — backend selection. ``backend_config`` is intentionally loose-shape
    # (see plan/BACKEND_CONTRACT.md §5) so users can drop in
    # ``{"model": "claude-haiku-4-5"}`` or ``{"host": "..."}`` without a schema
    # migration. Per-backend keys are documented in the contract.
    backend: Literal["ollama", "anthropic", "openai", "gemini"] = "ollama"
    backend_config: dict[str, Any] = Field(default_factory=dict)

    sentence_shape: SentenceShape = Field(default_factory=SentenceShape)
    punctuation_per_1000w: dict[str, PunctTarget] = Field(
        default_factory=lambda: {
            "em_dash": PunctTarget(target=0.0, hard_cap=0.0),
            "semicolon": PunctTarget(target=0.5, hard_cap=2.0),
            "colon": PunctTarget(target=4.0),
            "parenthesis": PunctTarget(target=5.0),
            "comma": PunctTarget(target=55.0),
        }
    )
    vocabulary: Vocabulary = Field(default_factory=Vocabulary)
    connectors_per_1000w: dict[str, float] = Field(default_factory=dict)
    blupper_probabilities: BlupperProbabilities = Field(default_factory=BlupperProbabilities)
    hedge_mix: HedgeMix = Field(default_factory=HedgeMix)
    paragraph_shape: ParagraphShape = Field(default_factory=ParagraphShape)
    forbidden_openers: list[str] = Field(
        default_factory=lambda: [
            "In conclusion",
            "To summarize",
            "It is worth noting",
            "Furthermore,",
            "Additionally,",
            "Moreover,",
        ]
    )
    risk_target: float = Field(default=0.35, ge=0, le=1)

    @field_validator("profile_name")
    @classmethod
    def _name_safe(cls, v: str) -> str:
        if not v or not all(c.isalnum() or c in "-_." for c in v):
            raise ValueError("profile_name must be non-empty and alphanumeric/.-_")
        return v


def load_profile(path: str | Path) -> Profile:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Profile.model_validate(data)


def save_profile(profile: Profile, path: str | Path) -> None:
    payload = profile.model_dump(mode="json", exclude_none=True)
    Path(path).write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
