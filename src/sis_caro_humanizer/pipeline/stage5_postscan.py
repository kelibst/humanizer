"""Stage 5: post-scan. Identical to stage 1; lives separately for symmetry."""
from __future__ import annotations

from ..profile.schema import Profile
from ..scoring.risk import ScoreReport, ai_risk_score


def postscan(text: str, profile: Profile | None = None) -> ScoreReport:
    return ai_risk_score(text, profile)


__all__ = ["postscan"]
