"""Tests for ``grammar.filters.apply_blupper_suppression``.

We don't run any external grammar tools here - the contract is that filters
operate on a list of ``GrammarIssue`` objects regardless of origin. We
hand-build issues that mimic what LanguageTool / Vale / proselint would emit.
"""
from __future__ import annotations

from sis_caro_humanizer.grammar.filters import apply_blupper_suppression
from sis_caro_humanizer.grammar.types import GrammarIssue
from sis_caro_humanizer.profile.schema import BlupperProbabilities, Profile


def _profile(**bp_overrides) -> Profile:
    bp = BlupperProbabilities(**bp_overrides) if bp_overrides else BlupperProbabilities()
    return Profile(profile_name="test", blupper_probabilities=bp)


def _issue(tool: str, rule_id: str, message: str, offset: int = 0) -> GrammarIssue:
    return GrammarIssue(
        tool=tool,  # type: ignore[arg-type]
        rule_id=rule_id,
        message=message,
        offset=offset,
        length=4,
    )


def test_data_singular_verb_suppressed_when_blupper_high() -> None:
    profile = _profile(data_singular_verb=0.6)
    issue = _issue(
        "languagetool",
        "DATA_VERB_AGREEMENT",
        "The word 'data' is plural; consider 'data are' instead of 'data is'.",
    )
    out = apply_blupper_suppression([issue], profile)
    assert out[0].suppressed is True
    assert "data_singular_verb" in (out[0].suppression_reason or "")


def test_data_singular_verb_not_suppressed_when_blupper_low() -> None:
    profile = _profile(data_singular_verb=0.1)
    issue = _issue(
        "languagetool",
        "DATA_VERB_AGREEMENT",
        "The word 'data' is plural; consider 'data are' instead of 'data is'.",
    )
    out = apply_blupper_suppression([issue], profile)
    assert out[0].suppressed is False
    assert out[0].suppression_reason is None


def test_less_for_fewer_suppressed() -> None:
    profile = _profile(less_for_fewer=0.3)
    issue = _issue(
        "languagetool",
        "LESS_COMP",
        "Use 'fewer' instead of 'less' before a countable noun.",
    )
    out = apply_blupper_suppression([issue], profile)
    assert out[0].suppressed is True


def test_which_that_suppressed_via_rule_id() -> None:
    profile = _profile(which_for_that=0.4)
    issue = _issue(
        "languagetool",
        "WHICH_THAT",
        "Consider 'that' for restrictive clauses.",
    )
    out = apply_blupper_suppression([issue], profile)
    assert out[0].suppressed is True
    assert "which_for_that" in (out[0].suppression_reason or "")


def test_sis_caro_vale_rules_never_suppressed() -> None:
    # Even with every blupper turned to maximum, our own informational style
    # rules should always survive - that is the whole point of running Vale.
    profile = _profile(
        data_singular_verb=1.0, less_for_fewer=1.0, which_for_that=1.0
    )
    em_dash_issue = GrammarIssue(
        tool="vale",
        rule_id="Sis-Caro.NoEmDash",
        message="Avoid em-dashes.",
        offset=0,
        length=1,
    )
    out = apply_blupper_suppression([em_dash_issue], profile)
    assert out[0].suppressed is False


def test_unrelated_issue_passes_through_unchanged() -> None:
    profile = _profile(data_singular_verb=0.6, less_for_fewer=0.3, which_for_that=0.4)
    issue = _issue("proselint", "typography.symbols", "Use a real ellipsis.")
    out = apply_blupper_suppression([issue], profile)
    assert out[0].suppressed is False
    assert out[0].suppression_reason is None


def test_filter_returns_list_preserving_order() -> None:
    profile = _profile(data_singular_verb=0.6)
    issues = [
        _issue("proselint", "x.one", "First", offset=0),
        _issue(
            "languagetool",
            "DATA_VERB_AGREEMENT",
            "data plural agreement",
            offset=10,
        ),
        _issue("proselint", "x.two", "Third", offset=20),
    ]
    out = apply_blupper_suppression(issues, profile)
    assert [o.rule_id for o in out] == ["x.one", "DATA_VERB_AGREEMENT", "x.two"]
    assert [o.suppressed for o in out] == [False, True, False]
