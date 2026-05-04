"""Em-dash transform tests."""
from __future__ import annotations

import random

from sis_caro_humanizer.pipeline.stage3_deterministic import em_dashes
from sis_caro_humanizer.pipeline.stage3_deterministic.protected import (
    build_protected_spans,
)
from sis_caro_humanizer.profile.schema import Profile


def _run(text: str):
    p = Profile(profile_name="t")
    rng = random.Random(0)
    spans = build_protected_spans(text)
    return em_dashes.apply(text, p, rng, spans)


def test_default_dash_becomes_comma() -> None:
    text = "Bystander CPR is rare — most families freeze."
    out, logs = _run(text)
    assert "—" not in out
    assert "rare, most families" in out
    assert any(l.transform == "strip_em_dashes" for l in logs)


def test_explanation_dash_becomes_colon() -> None:
    text = "There is one rule — namely, do not delay."
    out, _ = _run(text)
    # The "namely" trigger should produce a colon.
    assert "—" not in out
    assert ": " in out


def test_numeric_range_becomes_hyphen() -> None:
    text = "The trial ran 10—15 minutes per case."
    out, logs = _run(text)
    assert "10-15" in out
    assert any("range" in l.reason for l in logs)


def test_protected_quote_is_untouched() -> None:
    text = 'The reviewer wrote "this is a — bad — sentence" and moved on.'
    out, logs = _run(text)
    # The em-dashes inside the double-quoted span must survive.
    assert '"this is a — bad — sentence"' in out
    # No log lines should have been emitted inside the quote.
    for l in logs:
        assert "this is a" not in l.before


def test_paired_dashes_become_parentheses() -> None:
    text = "The result — surprising as it was — was conclusive."
    out, _ = _run(text)
    assert "—" not in out
    # The aside should be wrapped in parentheses.
    assert "(surprising as it was)" in out


def test_no_dashes_yields_no_change() -> None:
    text = "This sentence has no em dashes whatsoever."
    out, logs = _run(text)
    assert out == text
    assert logs == []
