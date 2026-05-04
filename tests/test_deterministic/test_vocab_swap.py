"""Vocab-swap transform tests.

Regression coverage for the phrasal-verb stranded-preposition bug
(see STATE.md "Bug 1 - vocab_swap strands trailing prepositions"): when
the source word is part of a phrasal verb in the user text, the trailing
preposition is *always* consumed so we do not produce ungrammatical
sequences like "look at into" (duplicate stranding) or "examine into"
(transitive verb that does not take a preposition).
"""
from __future__ import annotations

import random

from sis_caro_humanizer.pipeline.stage3_deterministic import vocab_swap
from sis_caro_humanizer.pipeline.stage3_deterministic.protected import (
    build_protected_spans,
)
from sis_caro_humanizer.profile.schema import Profile, Vocabulary


def _profile_with_swaps(swaps: dict[str, list[str]]) -> Profile:
    return Profile(
        profile_name="t",
        vocabulary=Vocabulary(preferred_swaps=swaps),
    )


def _run(text: str, profile: Profile, seed: int = 0):
    rng = random.Random(seed)
    spans = build_protected_spans(text)
    return vocab_swap.apply(text, profile, rng, spans)


def test_delve_into_does_not_strand_preposition() -> None:
    """``delve into`` must never produce ``look at into`` or similar."""
    profile = _profile_with_swaps({"delve": ["look at", "go into", "examine"]})
    text = "We need to delve into the records carefully."
    for seed in range(20):
        out, _ = _run(text, profile, seed=seed)
        # No stranded prepositions in any branch.
        assert "look at into" not in out
        assert "go into into" not in out
        assert "examine into" not in out
        # Some swap must have happened.
        assert "delve" not in out.lower(), f"swap missing at seed {seed}"


def test_delve_into_examine_replacement_drops_into() -> None:
    """``examine`` is transitive: ``delve into X`` -> ``examine X``."""
    profile = _profile_with_swaps({"delve": ["examine"]})
    text = "We need to delve into the records carefully."
    out, logs = _run(text, profile, seed=0)
    assert "examine the records" in out
    assert "examine into" not in out
    assert "delve" not in out.lower()
    assert len(logs) == 1
    assert logs[0].before == "delve into"
    assert logs[0].after == "examine"


def test_delve_into_look_at_replacement_drops_into() -> None:
    """``look at`` already carries its preposition: drop trailing ``into``."""
    profile = _profile_with_swaps({"delve": ["look at"]})
    text = "We need to delve into the records carefully."
    out, logs = _run(text, profile, seed=0)
    assert "look at the records" in out
    assert "look at into" not in out
    assert len(logs) == 1
    assert logs[0].before == "delve into"
    assert logs[0].after == "look at"


def test_delve_into_go_into_replacement_drops_into() -> None:
    """``go into`` already carries ``into``: do not duplicate."""
    profile = _profile_with_swaps({"delve": ["go into"]})
    text = "We need to delve into the records carefully."
    out, logs = _run(text, profile, seed=0)
    assert "go into the records" in out
    assert "go into into" not in out
    assert len(logs) == 1
    assert logs[0].before == "delve into"
    assert logs[0].after == "go into"


def test_navigate_through_consumes_trailing_preposition() -> None:
    profile = _profile_with_swaps({"navigate": ["work through", "deal with"]})
    text = "We must navigate through the maze."
    for seed in range(20):
        out, _ = _run(text, profile, seed=seed)
        assert "work through through" not in out
        assert "deal with through" not in out
        # The trailing "through" from the source must always be consumed.
        assert "the maze" in out


def test_embark_on_consumes_trailing_preposition() -> None:
    profile = _profile_with_swaps({"embark": ["set out on", "begin"]})
    text = "They embark on a new project."
    for seed in range(20):
        out, _ = _run(text, profile, seed=seed)
        assert "set out on on" not in out
        assert "begin on" not in out
        assert "a new project" in out


def test_non_phrasal_swap_unchanged() -> None:
    """A plain single-word swap with no following preposition is unaffected."""
    profile = _profile_with_swaps({"leverage": ["use", "draw on"]})
    text = "We leverage the data."
    out, logs = _run(text, profile, seed=0)
    assert "leverage" not in out
    assert len(logs) == 1
    # No preposition to strand here - output is well-formed regardless of pick.
    assert "the data" in out
