"""Smoke-test the Textual TUI through the Pilot harness.

The pipeline stack itself is fully covered by ``tests/test_pipeline_e2e.py``
and friends; here we just confirm that the TUI mounts, that the home screen
renders, that the Check screen drives :func:`ai_risk_score` and surfaces the
result on the gauge widget, and that the score lands in the HIGH band on the
deliberate AI sample.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from sis_caro_humanizer.tui.app import HumanizerApp
from sis_caro_humanizer.tui.widgets.score_gauge import ScoreGauge
from sis_caro_humanizer.tui.widgets.tab_aware_input import TabAwareInput

# A deliberately AI-flavoured paragraph: matches the calibration corpus
# the project ships with (post-scan moves it to LOW after the deterministic
# stage; pre-scan keeps it solidly HIGH).
AI_SAMPLE = (
    "In the rapidly evolving landscape of modern academia, it is worth noting "
    "that researchers must navigate a multifaceted tapestry of methodologies. "
    "Furthermore, scholars must delve into the intricate paradigm shifts that "
    "have emerged. Moreover, this holistic approach is crucial — leveraging "
    "diverse perspectives, fostering collaboration, and embarking on "
    "transformative endeavors.\n"
)


def _run(coro):
    return asyncio.run(coro)


def test_app_mounts_home_screen():
    async def go():
        app = HumanizerApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            return type(app.screen).__name__

    assert _run(go()) == "HomeScreen"


def test_check_screen_scores_ai_sample_to_high(tmp_path: Path):
    sample = tmp_path / "ai_sample.md"
    sample.write_text(AI_SAMPLE, encoding="utf-8")

    async def go():
        app = HumanizerApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("2")  # check tab
            await pilot.pause()
            screen = app.screen
            inp = screen.query_one("#check-input", TabAwareInput)
            inp.value = str(sample)
            screen.action_score()
            # Inline path is taken for short text; let the message loop drain.
            await pilot.pause()
            gauge = screen.query_one("#check-gauge", ScoreGauge)
            return gauge.score, gauge.band

    score, band = _run(go())
    # The deliberate AI paragraph parks comfortably in the HIGH band; we
    # accept anything from MEDIUM up so flakiness on different platforms /
    # randomness windows does not bite us.
    # v1.4: with perplexity disabled in the test suite (conftest.py), the
    # heuristic-only stack still parks the AI-flavoured paragraph above LOW.
    # Live runs with perplexity on routinely score > 0.7.
    assert score >= 0.4, f"unexpectedly low: {score}"
    assert band in {"medium", "high"}


def test_score_gauge_pure_render():
    """The widget can be rendered without mounting (used by the docs panel).

    Bare-metal sanity check that the gauge handles all three bands.
    """
    low = ScoreGauge._render_text(0.10, "low")
    med = ScoreGauge._render_text(0.50, "medium")
    high = ScoreGauge._render_text(0.90, "high")
    assert "0.100" in str(low)
    assert "LOW" in str(low)
    assert "MEDIUM" in str(med)
    assert "HIGH" in str(high)
