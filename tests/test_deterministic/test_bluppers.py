"""Blupper-transform tests."""
from __future__ import annotations

import random

from sis_caro_humanizer.pipeline.stage3_deterministic import bluppers
from sis_caro_humanizer.pipeline.stage3_deterministic.protected import (
    build_protected_spans,
)
from sis_caro_humanizer.profile.schema import BlupperProbabilities, Profile


def _profile(**overrides) -> Profile:
    bp = BlupperProbabilities(**overrides) if overrides else BlupperProbabilities()
    return Profile(profile_name="t", blupper_probabilities=bp)


def _run(text: str, profile: Profile, seed: int = 0):
    rng = random.Random(seed)
    spans = build_protected_spans(text)
    return bluppers.apply(text, profile, rng, spans)


def test_data_singular_verb_with_high_probability() -> None:
    text = "The data show that bystander CPR is rare. The data are conclusive."
    p = _profile(
        data_singular_verb=1.0,
        less_for_fewer=0.0,
        which_for_that=0.0,
        comma_splice_rate=0.0,
        start_with_and_but=0.0,
        oxford_comma_rate=0.55,
    )
    out, logs = _run(text, p)
    assert "data shows" in out
    assert "data is" in out
    assert any(l.transform == "blupper.data_singular_verb" for l in logs)


def test_less_for_fewer_with_high_probability() -> None:
    text = "Fewer patients arrived alive. Fewer cases were resuscitated."
    p = _profile(
        data_singular_verb=0.0,
        less_for_fewer=1.0,
        which_for_that=0.0,
        comma_splice_rate=0.0,
        start_with_and_but=0.0,
        oxford_comma_rate=0.55,
    )
    out, logs = _run(text, p)
    assert "Less patients" in out
    assert "Less cases" in out
    assert any(l.transform == "blupper.less_for_fewer" for l in logs)


def test_comma_splice_joins_short_clauses() -> None:
    text = "The results were striking. This aligns with prior work."
    p = _profile(
        data_singular_verb=0.0,
        less_for_fewer=0.0,
        which_for_that=0.0,
        comma_splice_rate=1.0,
        start_with_and_but=0.0,
        oxford_comma_rate=0.55,
    )
    out, logs = _run(text, p)
    assert "striking, this aligns" in out
    assert any(l.transform == "blupper.comma_splice" for l in logs)


def test_zero_probabilities_yield_no_change() -> None:
    text = "The data show that fewer patients arrived; this is a finding that surprises us."
    p = _profile(
        data_singular_verb=0.0,
        less_for_fewer=0.0,
        which_for_that=0.0,
        comma_splice_rate=0.0,
        start_with_and_but=0.0,
        oxford_comma_rate=0.5,  # any flip would need a 3-item list
    )
    out, _ = _run(text, p)
    assert out == text


def test_deterministic_with_same_seed() -> None:
    text = (
        "The data show that fewer cases arrive alive. The data are convincing. "
        "This finding that the system fails is unsurprising."
    )
    p = _profile()
    out_a, logs_a = _run(text, p, seed=123)
    out_b, logs_b = _run(text, p, seed=123)
    assert out_a == out_b
    assert [l.transform for l in logs_a] == [l.transform for l in logs_b]


def test_protected_text_not_modified() -> None:
    text = '"Fewer patients arrived." said the nurse, but fewer cases survived.'
    p = _profile(less_for_fewer=1.0)
    out, _ = _run(text, p)
    # Inside-quote "Fewer patients" must remain.
    assert '"Fewer patients arrived."' in out
    # Outside-quote occurrence flips.
    assert "less cases" in out


def test_which_for_that_skips_complementizer_after_noting() -> None:
    """``It is worth noting that the X...`` must NOT flip ``that`` to ``which``.

    Here ``that`` is a clause-introducing complementizer, not a relative
    pronoun, so the flip produces ungrammatical output like
    ``noting which the comprehensive...``.
    """
    text = (
        "It is worth noting that the comprehensive analysis reveals key "
        "patterns in the data."
    )
    p = _profile(
        data_singular_verb=0.0,
        less_for_fewer=0.0,
        which_for_that=1.0,
        comma_splice_rate=0.0,
        start_with_and_but=0.0,
        oxford_comma_rate=0.55,
    )
    out, logs = _run(text, p)
    assert "noting which" not in out
    assert "noting that" in out
    assert not any(l.transform == "blupper.which_for_that" for l in logs)


def test_which_for_that_skips_other_complementizers() -> None:
    """Verbs of saying/thinking/believing/etc. must not get ``that`` flipped."""
    cases = [
        "We are thinking that the system fails.",
        "He said that the pipeline works.",
        "They believe that the chain breaks early.",
        "We assume that the data are noisy.",
        "She argued that the evidence is weak.",
        "It is a fact that the records are incomplete.",
    ]
    p = _profile(
        data_singular_verb=0.0,
        less_for_fewer=0.0,
        which_for_that=1.0,
        comma_splice_rate=0.0,
        start_with_and_but=0.0,
        oxford_comma_rate=0.55,
    )
    for text in cases:
        out, logs = _run(text, p)
        # The ``that`` after the licensing token must be preserved.
        assert " that " in out, f"failed on: {text!r} -> {out!r}"
        assert not any(
            l.transform == "blupper.which_for_that" for l in logs
        ), f"unexpected which-for-that flip on: {text!r}"
