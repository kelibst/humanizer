"""Tests for research.readability (CONTRACT v1.3 §1.3)."""
from __future__ import annotations

from sis_caro_humanizer.profile.schema import Profile, ProfileTargets
from sis_caro_humanizer.research.readability import compute


def _profile_with_targets(**kw) -> Profile:
    targets = ProfileTargets(**kw)
    return Profile(profile_name="t", targets=targets)


def test_flesch_kincaid_baseline_simple_text():
    text = "The cat sat on the mat. The dog ran fast. Birds fly high."
    metrics, _ = compute(text)
    assert metrics.word_count > 0
    assert metrics.sentence_count == 3
    # Trivially short sentences should produce a very low FK grade.
    assert metrics.flesch_kincaid_grade < 8.0


def test_flesch_kincaid_higher_for_complex_text():
    text = (
        "The methodological underpinnings of contemporary epidemiological "
        "investigations require sophisticated multivariable regression "
        "techniques to disentangle confounding variables. Such approaches "
        "necessitate considerable statistical literacy."
    )
    metrics, _ = compute(text)
    # Complex prose should clearly exceed grade 10.
    assert metrics.flesch_kincaid_grade > 10.0


def test_sentence_cv_reflects_burstiness():
    bursty = "Short. Then a much longer sentence that runs on for many words. Another short. " * 3
    metrics_b, _ = compute(bursty)
    flat = "This is a sentence of seven words. " * 5
    metrics_f, _ = compute(flat)
    assert metrics_b.sentence_cv > metrics_f.sentence_cv


def test_target_check_ok_when_actual_under_fk_max():
    text = "The cat sat. The dog ran. Birds fly."
    profile = _profile_with_targets(fk_grade_max=12.0)
    _, targets = compute(text, profile)
    assert targets.fk_grade_max.target == 12.0
    assert targets.fk_grade_max.ok is True


def test_target_check_not_ok_when_cv_below_min():
    flat = "This is a sentence of seven words. " * 5
    profile = _profile_with_targets(sentence_cv_min=0.45)
    _, targets = compute(flat, profile)
    assert targets.sentence_cv_min.target == 0.45
    assert targets.sentence_cv_min.ok is False


def test_target_none_when_profile_field_unset():
    text = "A sentence here. Another there."
    profile = _profile_with_targets()  # all None
    _, targets = compute(text, profile)
    assert targets.fk_grade_max.target is None
    assert targets.fk_grade_max.actual is None
    assert targets.fk_grade_max.ok is None


def test_empty_text_returns_zeroed_metrics():
    metrics, targets = compute("")
    assert metrics.word_count == 0
    assert metrics.sentence_count == 0
    assert metrics.flesch_kincaid_grade == 0.0
    assert targets.fk_grade_max.target is None
