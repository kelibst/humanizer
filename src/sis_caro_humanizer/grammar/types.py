"""Shared dataclasses for the grammar subsystem.

Lives in its own module so each tool wrapper can import the types without a
circular import through ``grammar/runner.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ToolName = Literal["languagetool", "vale", "proselint"]
ToolStatus = Literal["ok", "missing", "skipped", "error"]


@dataclass
class GrammarIssue:
    tool: ToolName
    rule_id: str
    message: str
    offset: int
    length: int
    suggestions: list[str] = field(default_factory=list)
    suppressed: bool = False
    suppression_reason: str | None = None


@dataclass
class GrammarReport:
    issues: list[GrammarIssue]
    tool_status: dict[str, ToolStatus]
