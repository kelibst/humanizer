"""Section completeness checklist (CONTRACT §3.3, §1.2).

Reads ``checklist_rules.yaml`` once at import time, parses ATX markdown
headings out of the document, classifies each section by alias match, and
returns per-component presence (``hook`` / ``problem_statement`` / etc).

A component is *present* when ANY pattern matches OR ANY keyword appears in
the section body. Match is case-insensitive. ``re.MULTILINE`` lets patterns
anchor on line starts (``^``).

The runner is pure / deterministic — no LLM, no I/O. Pattern compilation is
cached at import time.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..text_utils import word_count

_RULES_PATH = Path(__file__).with_name("checklist_rules.yaml")


# ---------------------------------------------------------------------------
# Public dataclasses (CONTRACT §1.2 response shape, snake_case for JSON)
# ---------------------------------------------------------------------------


@dataclass
class ChecklistComponent:
    name: str
    present: bool
    evidence: str


@dataclass
class ChecklistSection:
    heading: str
    line_start: int
    line_end: int
    type: str
    components: list[ChecklistComponent] = field(default_factory=list)
    score: str = "0/0"
    word_count: int = 0


# ---------------------------------------------------------------------------
# Compiled rules
# ---------------------------------------------------------------------------


@dataclass
class _ComponentRule:
    name: str
    patterns: list[re.Pattern[str]]
    keywords: list[re.Pattern[str]]


@dataclass
class _ArchetypeRule:
    type: str
    aliases: list[str]
    components: list[_ComponentRule]


def _compile_rules(raw: dict[str, Any]) -> list[_ArchetypeRule]:
    archetypes: list[_ArchetypeRule] = []
    for type_name, body in (raw or {}).items():
        if not isinstance(body, dict):
            continue
        aliases = [str(a).lower().strip() for a in body.get("aliases", []) if a]
        comps_raw: dict[str, Any] = body.get("components", {}) or {}
        comps: list[_ComponentRule] = []
        for cname, cbody in comps_raw.items():
            cbody = cbody or {}
            patterns = []
            for p in cbody.get("patterns", []) or []:
                try:
                    patterns.append(re.compile(p, re.IGNORECASE | re.MULTILINE))
                except re.error:
                    # Bad pattern — silently drop; YAML is data not code.
                    continue
            keywords = []
            for k in cbody.get("keywords", []) or []:
                k_str = str(k).strip()
                if not k_str:
                    continue
                keywords.append(
                    re.compile(r"\b" + re.escape(k_str) + r"\b", re.IGNORECASE)
                )
            comps.append(_ComponentRule(name=cname, patterns=patterns, keywords=keywords))
        archetypes.append(
            _ArchetypeRule(type=type_name, aliases=aliases, components=comps)
        )
    return archetypes


def _load_rules() -> list[_ArchetypeRule]:
    if not _RULES_PATH.exists():
        return []
    try:
        raw = yaml.safe_load(_RULES_PATH.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return []
    if not isinstance(raw, dict):
        return []
    return _compile_rules(raw)


_ARCHETYPES: list[_ArchetypeRule] = _load_rules()


# ---------------------------------------------------------------------------
# Heading parser
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*\s*$", re.MULTILINE)


@dataclass
class _Section:
    heading: str
    level: int
    line_start: int
    line_end: int  # exclusive
    body: str


def _parse_sections(text: str) -> list[_Section]:
    """Split a markdown document into sections by ATX headings.

    A section ends at the next heading of the same or shallower level, or EOF.
    The heading line itself is included in the section's body (so patterns
    that match against the heading text still fire — but in practice patterns
    target the body).

    Returns sections with 0-based ``line_start`` (the heading line) and
    exclusive ``line_end`` (line after the last body line).
    """
    if not text:
        return []
    lines = text.split("\n")
    headings: list[tuple[int, int, str]] = []  # (line, level, title)
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*\s*$", line)
        if m:
            headings.append((i, len(m.group(1)), m.group(2).strip()))
    if not headings:
        return []

    sections: list[_Section] = []
    for idx, (start, level, title) in enumerate(headings):
        # Find the next heading at level <= current level.
        end_line = len(lines)
        for next_start, next_level, _ in headings[idx + 1:]:
            if next_level <= level:
                end_line = next_start
                break
        body_lines = lines[start:end_line]
        body = "\n".join(body_lines)
        sections.append(
            _Section(
                heading=title,
                level=level,
                line_start=start,
                line_end=end_line,
                body=body,
            )
        )
    return sections


# ---------------------------------------------------------------------------
# Section-type matching
# ---------------------------------------------------------------------------


def _match_archetype(heading: str) -> _ArchetypeRule | None:
    """Resolve a heading title to its archetype via alias substring match.

    Case-insensitive. Returns the first archetype whose alias appears as a
    word-boundary substring of the heading; falls back to ``None`` (the
    section will be classified as ``unknown``).
    """
    h = heading.lower().strip()
    if not h:
        return None
    # Prefer the most specific (longest) alias to win — sort once.
    candidates: list[tuple[int, _ArchetypeRule, str]] = []
    for arch in _ARCHETYPES:
        for alias in arch.aliases:
            # Word boundary or substring match. We only need an "in" + word
            # boundary; the heading is short.
            pattern = r"\b" + re.escape(alias) + r"\b"
            if re.search(pattern, h):
                candidates.append((len(alias), arch, alias))
                break
    if not candidates:
        return None
    candidates.sort(key=lambda t: -t[0])
    return candidates[0][1]


# ---------------------------------------------------------------------------
# Component evaluation
# ---------------------------------------------------------------------------


def _line_of_offset(body: str, offset: int) -> int:
    """Return the 1-based line index within ``body`` for character offset.

    Used to build ``evidence`` strings like ``"L4: Despite three decades…"``.
    """
    if offset <= 0:
        return 1
    return body.count("\n", 0, offset) + 1


def _evidence_snippet(body: str, match: re.Match[str], width: int = 80) -> str:
    line_no = _line_of_offset(body, match.start())
    # Find the line text at the match.
    lines = body.split("\n")
    if 0 <= line_no - 1 < len(lines):
        line_text = lines[line_no - 1].strip()
    else:
        line_text = match.group(0)
    if len(line_text) > width:
        line_text = line_text[: width - 1] + "…"
    return f"L{line_no}: {line_text}"


def _evaluate_component(rule: _ComponentRule, body: str) -> ChecklistComponent:
    for pat in rule.patterns:
        m = pat.search(body)
        if m:
            return ChecklistComponent(
                name=rule.name,
                present=True,
                evidence=_evidence_snippet(body, m),
            )
    for kw in rule.keywords:
        m = kw.search(body)
        if m:
            return ChecklistComponent(
                name=rule.name,
                present=True,
                evidence=_evidence_snippet(body, m),
            )
    return ChecklistComponent(name=rule.name, present=False, evidence="")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyse_sections(text: str, profile: Any | None = None) -> list[ChecklistSection]:
    """Return per-section completeness for the document.

    ``profile`` is accepted for parity with other research modules but is not
    currently used — the YAML rules drive every decision. Future work may
    overlay profile-specific terminology preferences.
    """
    sections = _parse_sections(text or "")
    out: list[ChecklistSection] = []
    for sec in sections:
        archetype = _match_archetype(sec.heading)
        if archetype is None:
            out.append(
                ChecklistSection(
                    heading=sec.heading,
                    line_start=sec.line_start,
                    line_end=sec.line_end,
                    type="unknown",
                    components=[],
                    score="0/0",
                    word_count=word_count(sec.body),
                )
            )
            continue

        components = [_evaluate_component(r, sec.body) for r in archetype.components]
        present = sum(1 for c in components if c.present)
        out.append(
            ChecklistSection(
                heading=sec.heading,
                line_start=sec.line_start,
                line_end=sec.line_end,
                type=archetype.type,
                components=components,
                score=f"{present}/{len(components)}",
                word_count=word_count(sec.body),
            )
        )
    return out


__all__ = [
    "ChecklistComponent",
    "ChecklistSection",
    "analyse_sections",
]
