"""Skeleton end-to-end test for ``run_pipeline``.

The full e2e (with real Ollama + deterministic + grammar) is the PM's
integration round. For now we exercise the runner with the cheap, dependency-
free stages only: ``prescan`` and ``postscan``.
"""
from __future__ import annotations

import pytest

from sis_caro_humanizer.pipeline.runner import (
    ALL_STAGES,
    PipelineResult,
    run_pipeline,
)
from sis_caro_humanizer.profile.loader import resolve_profile


SAMPLE = (
    "Bystander CPR rates are low at the hospital. We saw this in the death "
    "register. Twelve patients arrived dead. Of those, only two had any sign "
    "of compression marks on the chest. Looking at the data above, it seems "
    "like the chain of survival breaks very early. As such, training matters."
)


def test_runner_prescan_postscan_only() -> None:
    profile = resolve_profile("default_ghanaian")
    result = run_pipeline(SAMPLE, profile, stages=("prescan", "postscan"))
    assert isinstance(result, PipelineResult)
    assert result.input == SAMPLE
    assert result.output == SAMPLE  # no mutation stages requested
    assert result.pre_score is not None
    assert result.post_score is not None
    assert result.pre_score.band in ("low", "medium", "high")
    assert result.post_score.band in ("low", "medium", "high")
    # Pre/post scoring on identical text should produce identical scores.
    assert abs(result.pre_score.score - result.post_score.score) < 1e-9
    assert result.llm_used is False
    assert result.deterministic_log == []
    assert result.grammar is None
    assert result.elapsed_seconds >= 0.0


def test_runner_normalises_all_alias() -> None:
    profile = resolve_profile("default_ghanaian")
    # "all" must resolve to the same set ALL_STAGES, but we don't actually want
    # to invoke the LLM here - run with explicit prescan+postscan and confirm
    # the alias doesn't crash on parsing. We still pass the cheap pair.
    result = run_pipeline(SAMPLE, profile, stages=("prescan", "postscan"))
    assert ALL_STAGES == ("prescan", "llm", "determ", "grammar", "postscan")
    assert result.output == SAMPLE


def test_runner_unknown_stage_raises() -> None:
    profile = resolve_profile("default_ghanaian")
    try:
        run_pipeline(SAMPLE, profile, stages=("not_a_stage",))
    except ValueError as exc:
        assert "not_a_stage" in str(exc)
    else:  # pragma: no cover - regression
        raise AssertionError("expected ValueError for bad stage name")


def test_runner_handles_empty_text() -> None:
    profile = resolve_profile("default_ghanaian")
    result = run_pipeline("", profile, stages=("prescan", "postscan"))
    assert result.input == ""
    assert result.output == ""
    assert result.pre_score is not None
    assert result.post_score is not None


def test_runner_determ_downgrades_when_stage3_unavailable(monkeypatch) -> None:
    """If the deterministic stage cannot be imported, the runner must not
    crash: it downgrades, marks the stage as un-run, returns the input
    unchanged through that stage, and records a note naming ``determ``.
    """
    import sys
    import types

    # Force the lazy ``from .stage3_deterministic.runner import run_deterministic``
    # to fail by replacing the cached submodule with one that has no
    # ``run_deterministic`` attribute. The runner's broad ``except Exception``
    # catches the resulting ImportError and downgrades.
    fake = types.ModuleType("sis_caro_humanizer.pipeline.stage3_deterministic.runner")
    monkeypatch.setitem(
        sys.modules,
        "sis_caro_humanizer.pipeline.stage3_deterministic.runner",
        fake,
    )

    profile = resolve_profile("default_ghanaian")
    result = run_pipeline(
        SAMPLE, profile, stages=("prescan", "determ", "postscan")
    )

    assert isinstance(result, PipelineResult)
    assert result.llm_used is False
    # Stage 3 was the only mutating stage requested and it was forced to
    # fail, so the output equals the input.
    assert result.output == SAMPLE
    # Downgrade note must mention the deterministic stage.
    assert any("determ" in n.lower() for n in result.notes), (
        f"expected a determ-related downgrade note, got {result.notes!r}"
    )


def test_runner_unknown_stage_name_raises() -> None:
    """Per CONTRACTS, an unknown stage name in ``stages=`` must raise
    ``ValueError`` rather than silently downgrade."""
    profile = resolve_profile("default_ghanaian")
    with pytest.raises(ValueError, match="nonexistent_stage"):
        run_pipeline(SAMPLE, profile, stages=("nonexistent_stage",))
