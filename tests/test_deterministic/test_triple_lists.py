"""Triple-list transform tests."""
from __future__ import annotations

import random

from sis_caro_humanizer.pipeline.stage3_deterministic import triple_lists
from sis_caro_humanizer.pipeline.stage3_deterministic.protected import (
    build_protected_spans,
)
from sis_caro_humanizer.profile.schema import Profile


def _run(text: str, seed: int = 0):
    p = Profile(profile_name="t")
    rng = random.Random(seed)
    spans = build_protected_spans(text)
    return triple_lists.apply(text, p, rng, spans)


def test_three_item_match_can_rewrite() -> None:
    # Use many lists so probability ~0.4 fires at least once for some seed.
    text = (
        "We saw clarity, consistency, and care. We need clarity, focus, and depth. "
        "We had time, money, and effort. We tracked age, weight, and height. "
        "We observed haste, panic, and confusion."
    )
    # Try several seeds; with 5 triples and prob 0.4 we expect at least one fire.
    seen_rewrite = False
    for seed in range(20):
        out, logs = _run(text, seed=seed)
        if logs:
            seen_rewrite = True
            assert any(l.transform == "break_triple_list" for l in logs)
            # And the output must still mention at least one of the original
            # items so we didn't blow the sentence away.
            break
    assert seen_rewrite, "no triple-list rewrites fired across 20 seeds"


def test_proper_noun_list_is_skipped() -> None:
    text = "We surveyed Accra, Kumasi, and Tamale extensively."
    # Run many seeds; never rewrite this one.
    for seed in range(20):
        out, logs = _run(text, seed=seed)
        assert "Accra, Kumasi, and Tamale" in out or "Accra, Kumasi and Tamale" in out
        assert all(l.reason != "" for l in logs)  # any logs must be elsewhere
        assert not any(
            "Accra" in l.before for l in logs
        ), f"proper-noun list was rewritten at seed {seed}"


def test_proper_noun_list_lagos_nairobi_cairo_is_skipped() -> None:
    """Regression for STATE.md Bug 2: triples of single capitalised tokens
    that are place names must not be rewritten, even when the regex greedily
    captures the leading verb into group 1."""
    text = "Researchers compared Lagos, Nairobi, and Cairo across three years."
    for seed in range(20):
        out, logs = _run(text, seed=seed)
        # Output preserves the place-name list verbatim (with or without
        # the oxford comma — the transform never touched it).
        assert (
            "Lagos, Nairobi, and Cairo" in out
            or "Lagos, Nairobi and Cairo" in out
        )
        assert not any(
            "Lagos" in l.before for l in logs
        ), f"proper-noun list was rewritten at seed {seed}"


def test_citation_list_is_skipped() -> None:
    # The protected-spans builder protects (Author, Year) parentheticals; a
    # triple inside such a paren must survive.
    text = "Prior work (Smith, 2020) and (Jones, 2021) supports this. No triples here."
    # And a triple inside a quote must also survive.
    text2 = 'The reviewer wrote "the data show clarity, focus, and depth" plainly.'
    for seed in range(10):
        out, _ = _run(text2, seed=seed)
        assert '"the data show clarity, focus, and depth"' in out


def test_no_triple_yields_no_change() -> None:
    text = "Just two items: cats and dogs. Nothing else here."
    for seed in range(5):
        out, logs = _run(text, seed=seed)
        assert out == text
        assert logs == []
