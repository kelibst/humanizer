"""Stage 1: pre-scan. Thin wrapper around `ai_risk_score`."""
from __future__ import annotations

from ..profile.schema import Profile
from ..scoring.risk import ScoreReport, ai_risk_score


def prescan(text: str, profile: Profile | None = None) -> ScoreReport:
    return ai_risk_score(text, profile)


__all__ = ["prescan"]
