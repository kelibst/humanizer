"""Ghanaian-English article drop.

Per researchRules § 25: phrases like "at hospital" / "the mortality at
community level" are natural in Ghanaian English. Only triggers when
`profile.dialect == 'ghanaian'`.

Pattern: `(at|to|from|in)\\s+the\\s+(hospital|clinic|community|district|
ministry|polyclinic|facility)` → drop `the`.

Probability: `profile.blupper_probabilities.article_drop_ghanaian`.

We never apply to the FIRST occurrence in the document, so the reader gets
the canonical phrase at least once before the slip.
"""
from __future__ import annotations

import random
import re
from typing import TYPE_CHECKING

from .protected import overlaps_protected

if TYPE_CHECKING:
    from ...profile.schema import Profile


_PATTERN = re.compile(
    r"\b(?P<prep>at|to|from|in)\s+(?P<the>the)\s+"
    r"(?P<noun>hospital|clinic|community|district|ministry|polyclinic|facility)\b",
    re.IGNORECASE,
)


def apply(
    text: str,
    profile: "Profile",
    rng: random.Random,
    protected: list[tuple[int, int]],
) -> tuple[str, list]:
    from .runner import TransformLog

    if profile.dialect != "ghanaian":
        return text, []
    prob = profile.blupper_probabilities.article_drop_ghanaian
    if prob <= 0:
        return text, []

    matches = list(_PATTERN.finditer(text))
    if len(matches) < 2:
        return text, []  # need at least 2 so we can skip the first

    logs: list[TransformLog] = []
    new_text = text
    # Skip the very first occurrence; iterate the rest right-to-left.
    eligible = matches[1:]
    for m in reversed(eligible):
        if overlaps_protected(m.start(), m.end(), protected):
            continue
        if rng.random() > prob:
            continue
        prep = m.group("prep")
        noun = m.group("noun")
        # Replace the matched span with `prep + " " + noun` (drop "the ").
        replacement = f"{prep} {noun}"
        before = m.group(0)
        new_text = new_text[: m.start()] + replacement + new_text[m.end():]
        logs.append(
            TransformLog(
                transform="ghanaian.article_drop",
                site=(m.start(), m.end()),
                before=before,
                after=replacement,
                reason=f"dropped 'the' before '{noun}' (Ghanaian English)",
            )
        )
    logs.reverse()
    return new_text, logs


__all__ = ["apply"]
