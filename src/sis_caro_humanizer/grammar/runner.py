"""Run all three grammar tools concurrently and merge their findings."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ..profile.schema import Profile
from . import languagetool as _lt
from . import proselint as _prose
from . import vale as _vale
from .filters import apply_blupper_suppression
from .types import GrammarIssue, GrammarReport, ToolStatus

__all__ = ["GrammarIssue", "GrammarReport", "run_grammar"]


def _safe(name: str, func, text: str) -> tuple[str, list[GrammarIssue], ToolStatus]:
    try:
        issues, status = func(text)
    except Exception:
        return name, [], "error"
    return name, list(issues), status


def run_grammar(text: str, profile: Profile) -> GrammarReport:
    """Run LanguageTool, Vale, and proselint in parallel; merge, dedupe, and
    apply profile-aware suppression."""
    tool_status: dict[str, ToolStatus] = {
        "languagetool": "ok",
        "vale": "ok",
        "proselint": "ok",
    }
    aggregated: list[GrammarIssue] = []

    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = [
            ex.submit(_safe, "languagetool", _lt.check, text),
            ex.submit(_safe, "vale", _vale.check, text),
            ex.submit(_safe, "proselint", _prose.check, text),
        ]
        for fut in futures:
            name, issues, status = fut.result()
            tool_status[name] = status
            aggregated.extend(issues)

    # Dedupe by (offset, rule_id). Keep the first occurrence so tool ordering
    # (languagetool, vale, proselint) is the tiebreaker.
    seen: set[tuple[int, str]] = set()
    deduped: list[GrammarIssue] = []
    for issue in aggregated:
        key = (issue.offset, issue.rule_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)

    deduped = apply_blupper_suppression(deduped, profile)
    return GrammarReport(issues=deduped, tool_status=tool_status)
