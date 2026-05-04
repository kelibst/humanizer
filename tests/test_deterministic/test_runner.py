"""End-to-end deterministic runner tests."""
from __future__ import annotations

from sis_caro_humanizer.pipeline.stage3_deterministic import (
    DETERMINISTIC_PIPELINE,
    run_deterministic,
)
from sis_caro_humanizer.profile.schema import Profile


def _ghanaian_profile() -> Profile:
    return Profile(profile_name="t_gh", dialect="ghanaian")


def test_simple_input_does_not_crash() -> None:
    text = "Hello world. This is a test."
    out, logs = run_deterministic(text, Profile(profile_name="t"), seed=1)
    assert isinstance(out, str)
    assert out  # non-empty
    assert isinstance(logs, list)


def test_pipeline_has_eight_transforms() -> None:
    assert len(DETERMINISTIC_PIPELINE) == 8


def test_inline_code_survives_pipeline() -> None:
    text = (
        "We must `delve into multifaceted things` per spec. "
        "The data show that fewer patients arrived; this matters. "
        "The system was complex, intricate, and demanding."
    )
    out, _ = run_deterministic(text, _ghanaian_profile(), seed=42)
    # Inline code body must survive verbatim.
    assert "`delve into multifaceted things`" in out


def test_em_dash_is_removed_in_pipeline() -> None:
    text = "Bystander CPR was rare — most families froze in panic."
    out, _ = run_deterministic(text, _ghanaian_profile(), seed=42)
    assert "—" not in out


def test_deterministic_with_explicit_seed() -> None:
    text = (
        "The data show that bystander CPR rates are low. "
        "Fewer patients survived; the chain of survival breaks early. "
        "We need clarity, training, and time."
    )
    p = _ghanaian_profile()
    out_a, logs_a = run_deterministic(text, p, seed=99)
    out_b, logs_b = run_deterministic(text, p, seed=99)
    assert out_a == out_b
    assert [(l.transform, l.reason) for l in logs_a] == [
        (l.transform, l.reason) for l in logs_b
    ]


def test_logs_have_required_fields() -> None:
    text = "The data show that fewer cases arrive alive — this is the reality."
    _out, logs = run_deterministic(text, _ghanaian_profile(), seed=7)
    assert logs, "expected at least one transform to fire on this text"
    for l in logs:
        assert l.transform
        assert isinstance(l.site, tuple) and len(l.site) == 2
        assert l.reason
