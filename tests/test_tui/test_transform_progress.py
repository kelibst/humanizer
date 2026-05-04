"""Verify the transform progress widget reflects ``StageEvent`` callbacks.

Two angles:

1. The widget itself — feed a synthetic event sequence directly into
   :meth:`StagePipeline.apply_event` and confirm the per-stage state ends in
   the expected terminal value (no Textual app required).
2. End-to-end through the runner_bridge — wire the worker into a real
   ``HumanizerApp``, point the screen at a small text input, and let the
   actual ``run_pipeline`` execute. The post-score gauge ends up below the
   pre-score (deterministic stage drops AI-flavoured text into LOW band).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from sis_caro_humanizer.tui.app import HumanizerApp
from sis_caro_humanizer.tui.screens.transform import DEFAULT_STAGES, TransformScreen
from sis_caro_humanizer.tui.widgets.score_gauge import ScoreGauge
from sis_caro_humanizer.tui.widgets.stage_pipeline import STAGE_ORDER, StagePipeline
from sis_caro_humanizer.tui.widgets.tab_aware_input import TabAwareInput


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


# ---------------------------------------------------------------------------
# 1. Widget unit test — drive ``apply_event`` through a mounted Textual app.
#    The widget cannot be modified outside an ``App`` context because the
#    reactive ``states`` dict needs the active-app lookup.
# ---------------------------------------------------------------------------


def test_stage_pipeline_apply_event_state_machine():
    async def go():
        app = HumanizerApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("3")  # transform tab — owns the StagePipeline
            await pilot.pause()
            sp = app.screen.query_one("#t-pipeline", StagePipeline)

            # Mimic the four state transitions a single stage can go through.
            sp.apply_event(("stage_start", "prescan"))
            assert sp.state("prescan") == "running"
            sp.apply_event(("stage_done", "prescan", 0.01))
            assert sp.state("prescan") == "done"

            sp.apply_event(("stage_start", "llm"))
            assert sp.state("llm") == "running"
            sp.apply_event(("stage_skipped", "llm", "ollama unreachable"))
            assert sp.state("llm") == "skipped"

            # determ_step events do NOT touch the strip's per-stage state.
            sp.apply_event(("determ_step", "vocab_swap", 4))
            assert sp.state("determ") == "pending"

            # Unknown event kinds are tolerated.
            sp.apply_event(("mystery", "x"))
            assert sp.state("prescan") == "done"

    _run(go())


def test_stage_pipeline_reset():
    async def go():
        app = HumanizerApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("3")
            await pilot.pause()
            sp = app.screen.query_one("#t-pipeline", StagePipeline)
            for stage in STAGE_ORDER:
                sp.apply_event(("stage_done", stage, 0.0))
            assert all(sp.state(s) == "done" for s in STAGE_ORDER)
            sp.reset()
            assert all(sp.state(s) == "pending" for s in STAGE_ORDER)

    _run(go())


# ---------------------------------------------------------------------------
# 2. End-to-end through the worker
# ---------------------------------------------------------------------------


def test_transform_screen_runs_pipeline_through_worker(tmp_path: Path):
    sample = tmp_path / "ai_sample.md"
    sample.write_text(AI_SAMPLE, encoding="utf-8")

    async def go():
        app = HumanizerApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("3")  # transform
            await pilot.pause()
            screen: TransformScreen = app.screen  # type: ignore[assignment]
            inp = screen.query_one("#t-input", TabAwareInput)
            inp.value = str(sample)
            # Default stages (prescan, determ, postscan) are the fast path.
            screen.action_run()
            # Drain the worker queue.
            await app.workers.wait_for_complete()
            # Let final messages drain to the screen.
            for _ in range(5):
                await pilot.pause()
            sp = screen.query_one("#t-pipeline", StagePipeline)
            gauge = screen.query_one("#t-postscore-gauge", ScoreGauge)
            return (
                {s: sp.state(s) for s in STAGE_ORDER},
                gauge.score,
                gauge.band,
                screen._last_result,  # type: ignore[attr-defined]
            )

    states, post_score, band, result = _run(go())

    # All requested stages finished; un-requested stages stayed pending.
    assert states["prescan"] == "done"
    assert states["determ"] == "done"
    assert states["postscan"] == "done"
    assert states["llm"] == "pending"
    assert states["grammar"] == "pending"

    # Post-score gauge reflects the final score and lands in LOW or MEDIUM
    # (the deterministic stage routinely drops the AI sample to ~0.31).
    assert result is not None, "PipelineResult never reached the screen"
    assert post_score == result.post_score.score
    assert band in {"low", "medium"}, f"unexpected post-score band: {band}"
    assert result.pre_score.score > result.post_score.score, (
        f"pre {result.pre_score.score} not strictly > post {result.post_score.score}"
    )
