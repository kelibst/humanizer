"""Stage 1: pre-scan. Thin wrapper around `ai_risk_score`.

v1.6: also returns a list of warning notes. Currently the only possible note
is ``perplexity_unavailable`` which fires when neither Ollama logprobs nor the
DistilGPT2 fallback are accessible. The pipeline runner appends these notes to
``PipelineResult.notes`` so the CLI and TUI can surface them without crashing.
"""
from __future__ import annotations

from ..profile.schema import Profile
from ..scoring.risk import ScoreReport, ai_risk_score

_PERPLEXITY_WARN = (
    "perplexity unavailable: internal score may be under-estimated "
    "(Ollama not running / DistilGPT2 not installed). "
    "Run `humanize doctor` for details, or use `humanize check --external` "
    "to cross-validate against GPTZero/Sapling/ZeroGPT."
)


def prescan(text: str, profile: Profile | None = None) -> tuple[ScoreReport, list[str]]:
    """Run the AI-risk scorer and return ``(ScoreReport, notes)``.

    ``notes`` is a list of human-readable warning strings. It is empty when
    all features computed successfully. The caller should extend
    ``PipelineResult.notes`` with these strings.
    """
    report = ai_risk_score(text, profile)
    notes: list[str] = []
    for c in report.components:
        if c.name == "perplexity" and "perplexity_unavailable" in c.examples:
            notes.append(_PERPLEXITY_WARN)
            break
    return report, notes


__all__ = ["prescan", "_PERPLEXITY_WARN"]
