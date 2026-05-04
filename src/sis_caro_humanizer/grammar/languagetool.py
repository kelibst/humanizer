"""LanguageTool wrapper.

LanguageTool needs Java on PATH. The first call to :func:`check` spins up the
JVM, which is slow, so we cache the tool instance at module level. If Java is
absent we report ``status="missing"`` and return an empty list - this is not an
error condition for the rest of the pipeline.
"""
from __future__ import annotations

from threading import Lock
from typing import Optional

from .types import GrammarIssue, ToolStatus

_TOOL: Optional[object] = None
_STATUS: ToolStatus = "ok"
_LOCK = Lock()


def _get_tool() -> tuple[Optional[object], ToolStatus]:
    global _TOOL, _STATUS
    with _LOCK:
        if _TOOL is not None or _STATUS != "ok":
            return _TOOL, _STATUS
        try:
            import language_tool_python  # type: ignore
        except Exception:
            _STATUS = "missing"
            return None, _STATUS
        try:
            _TOOL = language_tool_python.LanguageTool("en-US")
            _STATUS = "ok"
        except Exception:
            # Most commonly: JavaError because Java is not installed.
            _TOOL = None
            _STATUS = "missing"
    return _TOOL, _STATUS


def check(text: str) -> tuple[list[GrammarIssue], ToolStatus]:
    """Run LanguageTool. Returns (issues, status). Status is ``missing`` when
    the JVM cannot be started or the package is unavailable; ``error`` for any
    runtime exception during the actual check."""
    if not text.strip():
        return [], "ok"
    tool, status = _get_tool()
    if status != "ok" or tool is None:
        return [], status
    try:
        matches = tool.check(text)  # type: ignore[attr-defined]
    except Exception:
        return [], "error"

    out: list[GrammarIssue] = []
    for m in matches:
        rule_id = getattr(m, "ruleId", "") or getattr(m, "rule_id", "") or ""
        message = getattr(m, "message", "") or ""
        offset = int(getattr(m, "offset", 0) or 0)
        length = int(getattr(m, "errorLength", 0) or getattr(m, "error_length", 0) or 0)
        replacements = list(getattr(m, "replacements", []) or [])[:5]
        out.append(
            GrammarIssue(
                tool="languagetool",
                rule_id=str(rule_id),
                message=str(message),
                offset=offset,
                length=length,
                suggestions=[str(r) for r in replacements],
            )
        )
    return out, "ok"


def shutdown() -> None:
    """Best-effort tear-down for tests / CLI exit."""
    global _TOOL
    with _LOCK:
        if _TOOL is not None:
            try:
                _TOOL.close()  # type: ignore[attr-defined]
            except Exception:
                pass
            _TOOL = None
