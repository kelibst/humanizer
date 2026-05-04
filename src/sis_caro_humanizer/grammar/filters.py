"""Suppress grammar-tool issues that conflict with the active profile's
intentional bluppers. We *mark* issues as suppressed (with a reason) rather
than dropping them so the report can still surface them on demand.
"""
from __future__ import annotations

import re
from typing import Iterable

from ..profile.schema import Profile
from .types import GrammarIssue

# Heuristic substring/regex patterns used when the rule_id is unhelpful.
_LESS_FEWER_RX = re.compile(r"\bless\b.*\bfewer\b|\bfewer\b.*\bless\b", re.IGNORECASE)
_DATA_VERB_RX = re.compile(r"\bdata\b.*(is|are|verb|agreement)", re.IGNORECASE)
_WHICH_THAT_RX = re.compile(
    r"\b(which|that)\b.*(restrictive|nonrestrictive|relative)", re.IGNORECASE
)


def _matches_rule(issue: GrammarIssue, *needles: str) -> bool:
    blob = f"{issue.rule_id} {issue.message}".lower()
    return any(n.lower() in blob for n in needles)


def apply_blupper_suppression(
    issues: Iterable[GrammarIssue], profile: Profile
) -> list[GrammarIssue]:
    """Walk the issue list and flip ``suppressed`` for items the profile
    would deliberately produce. The list is returned (a new list); items keep
    their order and identity."""
    bp = profile.blupper_probabilities
    out: list[GrammarIssue] = []
    for issue in issues:
        # Vale style rules from our own bundled folder are never suppressed
        # (NoEmDash et al are the whole point of running Vale).
        if issue.tool == "vale" and issue.rule_id.startswith("Sis-Caro."):
            out.append(issue)
            continue

        suppressed = False
        reason: str | None = None

        # --- "data" singular verb agreement ---------------------------------
        if bp.data_singular_verb > 0.3:
            blob = f"{issue.rule_id} {issue.message}".lower()
            if "data" in blob and (
                _matches_rule(issue, "DATA_", "agreement", "subject_verb", "subject-verb")
                or _DATA_VERB_RX.search(blob)
            ):
                suppressed = True
                reason = (
                    "profile.blupper_probabilities.data_singular_verb "
                    f"= {bp.data_singular_verb:.2f}"
                )

        # --- "less" used with countable noun --------------------------------
        if not suppressed and bp.less_for_fewer > 0.1:
            blob = f"{issue.rule_id} {issue.message}".lower()
            if (
                "less" in blob
                and (
                    "fewer" in blob
                    or _matches_rule(issue, "LESS_COMP", "less/fewer", "countable")
                )
            ) or _LESS_FEWER_RX.search(blob):
                suppressed = True
                reason = (
                    "profile.blupper_probabilities.less_for_fewer "
                    f"= {bp.less_for_fewer:.2f}"
                )

        # --- which / that restrictive-clause distinction --------------------
        if not suppressed and bp.which_for_that > 0.1:
            if _matches_rule(issue, "WHICH_THAT", "WHO_WHOM", "restrictive"):
                suppressed = True
                reason = (
                    "profile.blupper_probabilities.which_for_that "
                    f"= {bp.which_for_that:.2f}"
                )
            else:
                blob = f"{issue.rule_id} {issue.message}".lower()
                if _WHICH_THAT_RX.search(blob):
                    suppressed = True
                    reason = (
                        "profile.blupper_probabilities.which_for_that "
                        f"= {bp.which_for_that:.2f}"
                    )

        if suppressed:
            issue.suppressed = True
            issue.suppression_reason = reason
        out.append(issue)
    return out
