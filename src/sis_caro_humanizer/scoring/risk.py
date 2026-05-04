"""AI-risk aggregator: sigmoid over weighted feature contributions.

See CONTRACTS.md § 3. Six features, weights summing to 0.85; the remaining
0.15 is reserved for v2. The sigmoid sharpens the mid-range so that scores
near 0.5 spread out into clear `low / medium / high` bands.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from ..profile.schema import Profile


@dataclass
class FeatureContribution:
    name: str
    value: float
    weight: float
    detail: str
    examples: list[str] = field(default_factory=list)


@dataclass
class ScoreReport:
    score: float
    raw_weighted_sum: float
    components: list[FeatureContribution]
    band: Literal["low", "medium", "high"]


def _sigmoid(x: float) -> float:
    # Numerically stable.
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _band_for(score: float) -> Literal["low", "medium", "high"]:
    if score < 0.34:
        return "low"
    if score < 0.67:
        return "medium"
    return "high"


def ai_risk_score(text: str, profile: Profile | None = None) -> ScoreReport:
    """Compute the aggregated AI-risk score over all six features.

    `profile` is currently unused but kept in the signature so callers can
    eventually pass profile-specific weights or feature toggles.
    """
    # Lazy import to avoid circular dependency: features.py imports
    # FeatureContribution from this module.
    from .features import all_features

    components = all_features(text)
    weighted_sum = sum(c.value * c.weight for c in components)
    # Sigmoid centred on 0.5; gain of 6 widens the spread around the midpoint.
    score = _sigmoid(6.0 * (weighted_sum - 0.5))
    return ScoreReport(
        score=score,
        raw_weighted_sum=weighted_sum,
        components=components,
        band=_band_for(score),
    )


__all__ = ["FeatureContribution", "ScoreReport", "ai_risk_score"]
