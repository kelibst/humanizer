"""Deterministic "what's missing" inspector (v1.4).

Given a section_text and a section_type, surface a list of missing
elements. The runner is pure / regex-driven / no LLM. The findings carry a
ready-to-paste drill-down prompt the user can copy or send to their backend
of choice.

Reuses the v1.3 checklist component rules and adds methods-specific
must-have items (sample size, ethics approval, sampling strategy,
instrument validation, analysis plan) per V1_4_CONTRACT §1.3.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .prompts import render

# ---------------------------------------------------------------------------
# Per-section "must have" rule sets. Each rule has a name, an issue
# description, a suggestion, and one-or-more compiled regex patterns. A
# pattern HIT means the item is *present*; a miss means the inspector
# reports it as a finding.
# ---------------------------------------------------------------------------


@dataclass
class _MissingRule:
    name: str
    issue: str
    suggestion: str
    patterns: list[re.Pattern[str]]


def _re(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


_METHODS_RULES: list[_MissingRule] = [
    _MissingRule(
        name="sample_size_missing",
        issue="No sample size reported.",
        suggestion="State the n with a justification (power calc / saturation / pragmatic).",
        patterns=[
            _re(r"\b(?:sample size|n\s*=\s*\d+|sample of\s+\d+|\d+\s+participants?|\d+\s+respondents?|\d+\s+subjects?)\b"),
        ],
    ),
    _MissingRule(
        name="ethics_approval_missing",
        issue="No ethics approval / consent statement found.",
        suggestion="Add the ethics committee name, approval id, and a one-line consent statement.",
        patterns=[
            _re(r"\b(ethic(?:s|al)\s+(?:approval|clearance|committee|board|review))\b"),
            _re(r"\b(informed\s+consent|consent\s+was\s+(?:obtained|sought))\b"),
            _re(r"\b(IRB|institutional review board)\b"),
        ],
    ),
    _MissingRule(
        name="sampling_strategy_missing",
        issue="Sampling strategy is not described.",
        suggestion="Name the sampling method (purposive, convenience, stratified, random) and justify it.",
        patterns=[
            _re(r"\b(purposive|convenience|stratified|simple random|cluster|snowball|theoretical|systematic|maximum variation)\s+sampling\b"),
            _re(r"\bsampling\s+(?:method|strategy|technique|frame)\b"),
        ],
    ),
    _MissingRule(
        name="instrument_validation_missing",
        issue="Instrument validation / reliability not reported.",
        suggestion="Report Cronbach's alpha, pilot-test results, expert review, or comparable validation evidence.",
        patterns=[
            _re(r"\b(cronbach[' ]?s?\s+alpha|reliability|validity|pilot[- ]?test(?:ed)?|inter[- ]?rater|test[- ]?retest|construct\s+validity|content\s+validity)\b"),
        ],
    ),
    _MissingRule(
        name="analysis_plan_missing",
        issue="Analysis plan is not stated.",
        suggestion="Name the technique (thematic / regression / chi-square / etc.) and the software used.",
        patterns=[
            _re(r"\b(thematic|content|discourse|narrative|regression|chi[- ]?square|t[- ]?test|ANOVA|MANOVA|SEM|qualitative\s+coding)\s+analysis\b"),
            _re(r"\b(SPSS|R\s+(?:software|version)|STATA|NVivo|MAXQDA|ATLAS\.ti|Excel|Python)\b"),
        ],
    ),
]

_INTRODUCTION_RULES: list[_MissingRule] = [
    _MissingRule(
        name="problem_statement_missing",
        issue="Problem statement is not crisp.",
        suggestion="Add one sentence saying what the gap is and why it matters now.",
        patterns=[_re(r"\b(?:gap|problem|issue|challenge|limitation|despite|however|yet|still)\b")],
    ),
    _MissingRule(
        name="aim_objectives_missing",
        issue="Aim or objectives not stated.",
        suggestion="State the aim in one sentence; list 2-4 objectives as bullets.",
        patterns=[_re(r"\b(?:aim|objective|purpose|this study|this paper|we (?:aim|seek|set out))\b")],
    ),
]

_RESULTS_RULES: list[_MissingRule] = [
    _MissingRule(
        name="effect_size_missing",
        issue="No effect sizes / magnitudes reported.",
        suggestion="Report effect sizes (Cohen's d, OR, RR, η²) alongside p-values where applicable.",
        patterns=[
            _re(r"\b(cohen[' ]?s?\s+d|odds\s+ratio|OR\s*=|risk\s+ratio|RR\s*=|eta\s+squared|η²|95%\s+CI|confidence\s+interval)\b"),
        ],
    ),
    _MissingRule(
        name="participant_flow_missing",
        issue="Participant flow / response rate not reported.",
        suggestion="Report enrolment, completion, and any attrition with reasons.",
        patterns=[
            _re(r"\b(response\s+rate|attrition|dropped\s+out|drop[- ]?out|completed|enrolled|recruited)\b"),
        ],
    ),
]

_DISCUSSION_RULES: list[_MissingRule] = [
    _MissingRule(
        name="prior_work_missing",
        issue="Findings not contextualised against prior work.",
        suggestion="Compare each principal finding to at least one cited prior study.",
        patterns=[
            _re(r"\b(consistent\s+with|in line with|in contrast to|similar to|differs from|extends|aligns?\s+with)\b"),
        ],
    ),
    _MissingRule(
        name="limitations_missing",
        issue="Limitations not flagged.",
        suggestion="Add a Limitations paragraph covering at least three threats to validity.",
        patterns=[_re(r"\b(limitation|caveat|threat\s+to\s+validity|generalis(?:ability|ation))\b")],
    ),
]


def _rules_for(section_type: str) -> list[_MissingRule]:
    st = (section_type or "").lower().strip()
    if st in ("methods", "methodology", "method"):
        return _METHODS_RULES
    if st in ("introduction", "intro"):
        return _INTRODUCTION_RULES
    if st in ("results",):
        return _RESULTS_RULES
    if st in ("discussion",):
        return _DISCUSSION_RULES
    return []


@dataclass
class InspectFinding:
    name: str
    issue: str
    suggestion: str
    prompt: str


def inspect_section(section_text: str, section_type: str) -> list[InspectFinding]:
    """Return one finding per missing must-have for the given section type.

    Section types not in the known set return an empty list (no false
    positives).
    """
    text = section_text or ""
    findings: list[InspectFinding] = []
    for rule in _rules_for(section_type):
        if _any_pattern_hits(rule.patterns, text):
            continue
        # Render a focused drill-down prompt so the UI can offer copy /
        # send-to-backend without round-tripping the inspector.
        prompt = _drill_prompt(rule, section_text, section_type)
        findings.append(
            InspectFinding(
                name=rule.name,
                issue=rule.issue,
                suggestion=rule.suggestion,
                prompt=prompt,
            )
        )
    return findings


def _any_pattern_hits(patterns: Iterable[re.Pattern[str]], text: str) -> bool:
    return any(p.search(text) for p in patterns)


def _drill_prompt(rule: _MissingRule, section_text: str, section_type: str) -> str:
    """Build a focused prompt by extending ``missing_inspector`` with the
    finding-specific framing."""
    framed = (
        f"FOCUSED FINDING: **{rule.name}** — {rule.issue}\n"
        f"SUGGESTED FIX: {rule.suggestion}\n\n"
        + section_text
    )
    return render(
        "missing_inspector",
        {"section_text": framed, "section_type": section_type},
    )


__all__ = ["InspectFinding", "inspect_section"]
