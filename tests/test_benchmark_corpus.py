"""Benchmark corpus tests for the humanizer scorer (CONTRACT v1.5 §7).

Tests are marked @pytest.mark.slow and only run when --slow flag is passed
or HUMANIZER_SLOW_TESTS=1 is set in the environment.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from sis_caro_humanizer.profile.loader import resolve_profile
from sis_caro_humanizer.scoring.risk import ai_risk_score

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "benchmark"


def _load_paragraphs(filename: str) -> list[str]:
    path = FIXTURES_DIR / filename
    text = path.read_text(encoding="utf-8")
    # Paragraphs are separated by \n\n---\n\n
    paragraphs = text.split("\n\n---\n\n")
    return [p.strip() for p in paragraphs if p.strip()]


@pytest.mark.slow
def test_human_corpus_mostly_low_or_medium():
    """At least 80% of 25 human paragraphs score LOW or MEDIUM."""
    profile = resolve_profile("default_ghanaian")
    paragraphs = _load_paragraphs("human_25.md")
    assert len(paragraphs) == 25, f"Expected 25 paragraphs, got {len(paragraphs)}"

    low_or_medium = 0
    for para in paragraphs:
        report = ai_risk_score(para, profile)
        if report.band in ("low", "medium"):
            low_or_medium += 1

    pct = low_or_medium / len(paragraphs)
    assert pct >= 0.80, (
        f"Only {low_or_medium}/{len(paragraphs)} human paragraphs scored LOW/MEDIUM "
        f"({pct:.0%}); expected ≥ 80%"
    )


@pytest.mark.slow
def test_ai_corpus_mostly_medium_or_high():
    """At least 80% of 25 AI paragraphs score MEDIUM or HIGH."""
    profile = resolve_profile("default_ghanaian")
    paragraphs = _load_paragraphs("ai_25.md")
    assert len(paragraphs) == 25, f"Expected 25 paragraphs, got {len(paragraphs)}"

    medium_or_high = 0
    for para in paragraphs:
        report = ai_risk_score(para, profile)
        if report.band in ("medium", "high"):
            medium_or_high += 1

    pct = medium_or_high / len(paragraphs)
    assert pct >= 0.80, (
        f"Only {medium_or_high}/{len(paragraphs)} AI paragraphs scored MEDIUM/HIGH "
        f"({pct:.0%}); expected ≥ 80%"
    )


@pytest.mark.slow
def test_deterministic_reduces_score_on_ai_corpus():
    """Deterministic stage reduces score on ≥ 80% of AI paragraphs."""
    profile = resolve_profile("default_ghanaian")
    paragraphs = _load_paragraphs("ai_25.md")

    try:
        from sis_caro_humanizer.pipeline.stage3_deterministic.runner import run_deterministic
    except ImportError:
        pytest.skip("stage3_deterministic not available")

    reduced_count = 0
    for para in paragraphs:
        pre = ai_risk_score(para, profile).score
        rewritten, _ = run_deterministic(para, profile, seed=42)
        post = ai_risk_score(rewritten, profile).score
        if post < pre:
            reduced_count += 1

    pct = reduced_count / len(paragraphs)
    assert pct >= 0.80, (
        f"Deterministic stage only reduced score on {reduced_count}/{len(paragraphs)} "
        f"AI paragraphs ({pct:.0%}); expected ≥ 80%"
    )
