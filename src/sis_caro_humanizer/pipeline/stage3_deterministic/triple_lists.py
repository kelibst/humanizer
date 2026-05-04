"""Break the AI rule-of-three.

Per researchRules § 27 / § 52: three-item lists are an AI tell. With
probability 0.40 per non-skipped hit, rewrite a `X, Y, and Z` triple as one
of:

    1. two-item     → drop the middle item: `X and Z`
    2. parenthetical aside → keep two items, push the middle into a paren:
       `X and Z (also Y)`
    3. prose-split  → `X and Y. There is also Z.`

Skip rules:
    - if all three terms look like proper nouns (each ends in / contains a
      capitalised token, or the middle item is a single ``^[A-Z][a-z]+$``
      token paired with similarly-shaped neighbours),
    - if the leading verb is one of a small enumeration-cue allowlist
      (``surveyed``, ``visited``, ``sampled``, ``recruited``, ``included``,
      ``comparing``, ``between``, ``among``) AND the middle item is a single
      capitalised token (this catches "We surveyed Accra, Kumasi, and
      Tamale" where the regex greedily swallows surrounding context),
    - if the triple sits inside a citation parenthetical (``(Smith, 2020,
      and Jones, 2021)`` style — overlap with a protected span will already
      block this).
"""
from __future__ import annotations

import random
import re
from typing import TYPE_CHECKING

from .protected import overlaps_protected

if TYPE_CHECKING:
    from ...profile.schema import Profile


# Same shape as the scoring regex but with looser word-character bounds.
_TRIPLE = re.compile(
    r"\b([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,4})"
    r",\s+"
    r"([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,4})"
    r"(?:,)?\s+and\s+"
    r"([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,4})\b"
)

PROBABILITY = 0.40

# Verbs/prepositions that strongly signal a list of place / person /
# institution names. When these lead into the list and the middle item is
# a bare capitalised token, treat the whole triple as proper nouns even if
# the greedy regex captured extra context on either side.
_ENUMERATION_CUES: frozenset[str] = frozenset(
    {
        "surveyed",
        "visited",
        "sampled",
        "recruited",
        "included",
        "comparing",
        "between",
        "among",
        "from",
        "across",
    }
)

# Common-noun openers that look capitalised because they start a sentence
# but are NOT proper nouns. If the first term is one of these, do not treat
# the triple as a proper-noun list.
_COMMON_NOUN_OPENERS: frozenset[str] = frozenset(
    {"Many", "Some", "Few", "Several", "Most", "All", "Both", "These", "Those"}
)

_SINGLE_CAP_TOKEN = re.compile(r"^[A-Z][a-z]+$")


def _is_single_cap_token(term: str) -> bool:
    """True when the term is exactly one capitalised word like 'Accra'
    (and not a sentence-opening common noun like 'Many')."""
    term = term.strip()
    if term in _COMMON_NOUN_OPENERS:
        return False
    return bool(_SINGLE_CAP_TOKEN.match(term))


def _final_token_capitalised(term: str) -> bool:
    """True when the *last* token of the term starts with a capital letter."""
    parts = term.split()
    if not parts:
        return False
    last = parts[-1]
    if last in _COMMON_NOUN_OPENERS:
        return False
    return last[:1].isupper()


def _first_token_capitalised(term: str) -> bool:
    """True when the *first* token of the term starts with a capital letter
    (and is not a sentence-opening common noun)."""
    parts = term.split()
    if not parts:
        return False
    first = parts[0]
    if first in _COMMON_NOUN_OPENERS:
        return False
    return first[:1].isupper()


def _looks_proper_noun_list(x: str, y: str, z: str) -> bool:
    """Heuristic: the triple is a list of proper nouns.

    We accept the list as proper-nouns if any of:
      (a) every term is a single capitalised token (e.g. ``Accra``,
          ``Kumasi``, ``Tamale``), OR
      (b) the middle term is a single capitalised token AND both the last
          token of `x` and the first token of `z` are capitalised — this
          covers the greedy-capture case ``"We surveyed Accra"`` /
          ``"Tamale extensively"`` where the actual list items are still
          proper nouns at the inner edges.
    """
    if all(_is_single_cap_token(t) for t in (x, y, z)):
        return True
    if (
        _is_single_cap_token(y)
        and _final_token_capitalised(x)
        and _first_token_capitalised(z)
    ):
        return True
    return False


def _has_enumeration_cue(text_before_x: str) -> bool:
    """True when the last alphabetic word in `text_before_x` is one of the
    enumeration-cue verbs/prepositions."""
    tokens = re.findall(r"[A-Za-z]+", text_before_x)
    if not tokens:
        return False
    return tokens[-1].lower() in _ENUMERATION_CUES


def apply(
    text: str,
    profile: "Profile",
    rng: random.Random,
    protected: list[tuple[int, int]],
) -> tuple[str, list]:
    from .runner import TransformLog

    matches = list(_TRIPLE.finditer(text))
    if not matches:
        return text, []
    logs: list[TransformLog] = []
    new_text = text
    # Apply right-to-left to preserve offsets.
    for m in reversed(matches):
        if overlaps_protected(m.start(), m.end(), protected):
            continue
        x, y, z = m.group(1), m.group(2), m.group(3)

        # Strengthened proper-noun skip: covers single-token lists like
        # "Accra, Kumasi, and Tamale" even when the regex greedily swallows
        # neighbouring context on either side.
        if _looks_proper_noun_list(x, y, z):
            continue

        # Enumeration-cue skip: when the leading verb/preposition signals a
        # list of names AND the middle item is a single capitalised token,
        # treat the whole triple as off-limits.
        if _is_single_cap_token(y) and _has_enumeration_cue(text[: m.start()]):
            continue

        if rng.random() > PROBABILITY:
            continue
        choice = rng.choice(("two", "aside", "split"))
        if choice == "two":
            replacement = f"{x} and {z}"
            reason = "rewrote triple as two items (dropped middle)"
        elif choice == "aside":
            replacement = f"{x} and {z} (also {y})"
            reason = "rewrote triple with parenthetical aside"
        else:
            replacement = f"{x} and {y}. There is also {z}"
            reason = "rewrote triple as prose split"
        before = m.group(0)
        new_text = new_text[: m.start()] + replacement + new_text[m.end():]
        logs.append(
            TransformLog(
                transform="break_triple_list",
                site=(m.start(), m.end()),
                before=before,
                after=replacement,
                reason=reason,
            )
        )
    logs.reverse()
    return new_text, logs


__all__ = ["apply"]
