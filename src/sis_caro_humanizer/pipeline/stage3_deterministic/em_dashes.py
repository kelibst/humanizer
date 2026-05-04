"""Strip em-dashes (— and ASCII `--`).

Per researchRules § 35: em-dashes are an AI tell. Replace each non-protected
occurrence with the contextually appropriate alternative:

    1. Numeric range  `\\d—\\d`             → `-`
    2. Paired around an aside (two —s in
       the same clause)                    → `(...)` around the aside
    3. Explanation (the part after the —
       expands the part before)            → `: `
    4. Default                              → `, `

The classification is purely positional/lexical; we do not parse syntax.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .protected import is_protected

if TYPE_CHECKING:
    from ...profile.schema import Profile


# Each occurrence of an em-dash in normalized form.
_DASH_RE = re.compile(r"\s*(—|--)\s*")

# Words after a dash that suggest the right-hand side is a list/explanation.
_EXPLAIN_TRIGGERS = ("namely", "for example", "for instance", "such as", "i.e.", "e.g.")


@dataclass
class _Hit:
    start: int
    end: int
    raw: str
    left_ws: bool
    right_ws: bool


def _find_dashes(text: str, protected: list[tuple[int, int]]) -> list[_Hit]:
    hits: list[_Hit] = []
    for m in _DASH_RE.finditer(text):
        if is_protected(m.start(), protected):
            continue
        raw = m.group(0)
        left_ws = m.start() > 0 and text[m.start()].isspace() if raw[0].isspace() else (
            m.start() > 0 and text[m.start() - 1].isspace()
        )
        # We re-derive simply: if there is whitespace immediately before the
        # match (or the match itself starts with whitespace), call it spaced.
        left_ws = bool(re.match(r"^\s", raw)) or (
            m.start() > 0 and text[m.start() - 1] == " "
        )
        right_ws = bool(re.search(r"\s$", raw)) or (
            m.end() < len(text) and text[m.end()] == " "
        )
        hits.append(_Hit(m.start(), m.end(), raw, left_ws, right_ws))
    return hits


def _is_numeric_range(text: str, hit: _Hit) -> bool:
    # `\d\s*—\s*\d` style. Ignore surrounding whitespace.
    left = text[max(0, hit.start - 4):hit.start].rstrip()
    right = text[hit.end:hit.end + 4].lstrip()
    return bool(left and left[-1].isdigit() and right and right[0].isdigit())


def _classify(text: str, hit: _Hit, paired_partner: int | None) -> str:
    """Return one of: 'range', 'aside', 'explain', 'default'."""
    if _is_numeric_range(text, hit):
        return "range"
    if paired_partner is not None:
        return "aside"
    # Explanation if right-hand side begins with a trigger word, OR if the
    # left side ends with a colon-like cue (verb of being / definition cue).
    rhs_lower = text[hit.end:hit.end + 30].lstrip().lower()
    if any(rhs_lower.startswith(t) for t in _EXPLAIN_TRIGGERS):
        return "explain"
    # Look for "is/are/was/were/means" just before the dash.
    lhs_tail = text[max(0, hit.start - 20):hit.start].rstrip().lower()
    if re.search(r"\b(is|are|was|were|means|namely)$", lhs_tail):
        return "explain"
    return "default"


def _pair_asides(hits: list[_Hit], text: str) -> dict[int, int]:
    """Return mapping of hit-index → partner-hit-index for paired asides.

    Two consecutive em-dashes within the same paragraph (no blank line
    between them) form an aside.
    """
    pairs: dict[int, int] = {}
    used: set[int] = set()
    for i in range(len(hits) - 1):
        if i in used:
            continue
        a, b = hits[i], hits[i + 1]
        between = text[a.end:b.start]
        if "\n\n" in between:
            continue
        if "\n" in between:
            continue
        # Heuristic: aside body should be short (< 80 chars) and not contain
        # a sentence terminator at the very end.
        if len(between.strip()) > 100:
            continue
        if "." in between[:-1]:  # full stop inside aside is suspicious
            continue
        pairs[i] = i + 1
        pairs[i + 1] = i
        used.add(i)
        used.add(i + 1)
    return pairs


def apply(
    text: str,
    profile: "Profile",
    rng: random.Random,
    protected: list[tuple[int, int]],
) -> tuple[str, list]:
    from .runner import TransformLog  # local import to avoid cycle

    hits = _find_dashes(text, protected)
    if not hits:
        return text, []
    pairs = _pair_asides(hits, text)
    logs: list[TransformLog] = []

    # Build replacements bottom-up so offsets remain valid as we splice.
    pieces: list[tuple[int, int, str, str]] = []  # (start, end, replacement, kind)
    for i, hit in enumerate(hits):
        partner = pairs.get(i)
        kind = _classify(text, hit, partner)
        if kind == "range":
            replacement = "-"
        elif kind == "aside":
            # Open / close a parenthetical depending on which one this is.
            replacement = " (" if partner is not None and partner > i else ") "
            # Ensure a single space context: collapse leading/trailing spaces in raw.
            if partner is not None and partner > i:
                # Opening: drop preceding space, add single space + "(".
                # Use " (" and rely on existing left-space being absorbed.
                replacement = " ("
            else:
                replacement = ") "
        elif kind == "explain":
            replacement = ": "
        else:
            replacement = ", "
        pieces.append((hit.start, hit.end, replacement, kind))

    # Apply in reverse so earlier offsets stay valid.
    new_text = text
    for start, end, replacement, kind in reversed(pieces):
        before = text[start:end]
        # When inserting an opening paren we want to remove the space that
        # already preceded the dash. Same idea on the closing side: kill the
        # trailing space.
        adj_start, adj_end = start, end
        if kind == "aside" and replacement == " (":
            # If text immediately before is a space, swallow it so we don't
            # produce double space.
            if adj_start > 0 and new_text[adj_start - 1] == " ":
                adj_start -= 1
                replacement = " ("  # already has a leading space
        if kind == "aside" and replacement == ") ":
            # If text immediately after is a space, swallow it.
            if adj_end < len(new_text) and new_text[adj_end] == " ":
                adj_end += 1
                replacement = ") "
        new_text = new_text[:adj_start] + replacement + new_text[adj_end:]
        logs.append(
            TransformLog(
                transform="strip_em_dashes",
                site=(start, end),
                before=before,
                after=replacement,
                reason=f"em-dash classified as {kind}",
            )
        )
    logs.reverse()
    return new_text, logs


__all__ = ["apply"]
