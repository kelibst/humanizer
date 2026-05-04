"""proselint wrapper.

proselint is pure-Python so the only failure modes are import errors and the
occasional bug inside a check. Both are demoted to a status flag.
"""
from __future__ import annotations

from .types import GrammarIssue, ToolStatus


def check(text: str) -> tuple[list[GrammarIssue], ToolStatus]:
    if not text.strip():
        return [], "ok"
    try:
        from proselint import tools  # type: ignore
    except Exception:
        return [], "missing"

    try:
        results = tools.lint(text)
    except Exception:
        return [], "error"

    # proselint result tuple: (check_name, message, line, column, start, end, extent, severity, replacements)
    issues: list[GrammarIssue] = []
    for r in results or []:
        try:
            check_name = str(r[0])
            message = str(r[1])
            start = int(r[4])
            extent = int(r[6]) if len(r) > 6 and r[6] is not None else 0
            replacements = r[8] if len(r) > 8 else None
        except (IndexError, TypeError, ValueError):
            continue
        suggestions: list[str]
        if isinstance(replacements, (list, tuple)):
            suggestions = [str(x) for x in replacements][:5]
        elif replacements:
            suggestions = [str(replacements)]
        else:
            suggestions = []
        issues.append(
            GrammarIssue(
                tool="proselint",
                rule_id=check_name,
                message=message,
                offset=start,
                length=extent,
                suggestions=suggestions,
            )
        )
    return issues, "ok"
