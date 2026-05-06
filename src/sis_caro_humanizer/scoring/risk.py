"""AI-risk aggregator: sigmoid over weighted feature contributions.

See CONTRACTS.md § 3 and plan/V1_4_CONTRACT.md §3.5. As of v1.4, seven
features sum to 1.0:

    llm_vocab_density          0.16
    burstiness_deficit         0.14
    punct_signature            0.10
    triple_list_rate           0.08
    topic_sentence_perfection  0.08
    hedge_formality_skew       0.08
    perplexity                 0.36
    -------------------------------
    total                      1.00

The sigmoid sharpens the mid-range so that scores near 0.5 spread out into
clear `low / medium / high` bands.
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
    """Compute the aggregated AI-risk score over all seven features.

    The ``profile`` is forwarded to :func:`scoring.features.all_features` so
    the perplexity feature (v1.4) can honour ``profile.perplexity_model``.
    """
    # Lazy import to avoid circular dependency: features.py imports
    # FeatureContribution from this module.
    from .features import all_features

    components = all_features(text, profile)
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
