"""Phase 4: voice-diff and idle suggestions routes."""
from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException

from ..models.v156 import VoiceDiffBody


def make_router(auth_dep: Any) -> APIRouter:
    router = APIRouter()

    # ------------------------------------------------------------------
    # POST /v1/research/voice-diff
    # ------------------------------------------------------------------

    @router.post("/v1/research/voice-diff")
    async def voice_diff(body: VoiceDiffBody, _: None = auth_dep) -> dict[str, Any]:
        """Detect sections whose writing style deviates from the document average.

        Returns a list of ``{title, word_count, is_outlier, mean_abs_z,
        outlier_features}`` dicts, one per section.  Sections with fewer
        than 30 words are skipped.  When fewer than 2 substantial sections
        are present the response is always empty.
        """
        from ...research.voice_diff import analyse_voice
        from ..helpers import _safe_resolve_profile

        prof = _safe_resolve_profile(body.profile)
        results = analyse_voice(body.text)

        def _row(r) -> dict[str, Any]:
            return {
                "title": r.title,
                "word_count": r.word_count,
                "is_outlier": r.is_outlier,
                "mean_abs_z": r.mean_abs_z,
                "outlier_features": r.outlier_features,
                "features": r.features,
            }

        return {"sections": [_row(r) for r in results]}

    return router
