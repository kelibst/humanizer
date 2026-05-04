"""Replace semicolons in flowing prose.

Per researchRules § 36: semicolons feel edited. Rules:

    1. Inside a list (a; b; c) → leave alone.
    2. If the next clause begins with a coordinating conjunction
       ("and", "but", "or", "nor", "so", "yet", "for"), replace `;` with `, `.
    3. Otherwise, replace `;` with `. ` and capitalize the next non-space
       character.
"""
from __future__ import annotations

import random
import re
from typing import TYPE_CHECKING

from .protected import is_protected

if TYPE_CHECKING:
    from ...profile.schema import Profile


_CONJ = ("and", "but", "or", "nor", "so", "yet", "for")


def _is_in_list(text: str, pos: int) -> bool:
    """Heuristic: a semicolon is *list-style* if there's another semicolon
    within the same sentence (delimited by `.`/`!`/`?`/newline) on either
    side. Crude but matches "a; b; c" without parsing.
    """
    # Look left for sentence boundary or another ; ; if we hit ; first → list.
    i = pos - 1
    while i >= 0:
        ch = text[i]
        if ch in ".!?\n":
            break
        if ch == ";":
            return True
        i -= 1
    j = pos + 1
    while j < len(text):
        ch = text[j]
        if ch in ".!?\n":
            break
        if ch == ";":
            return True
        j += 1
    return False


def apply(
    text: str,
    profile: "Profile",
    rng: random.Random,
    protected: list[tuple[int, int]],
) -> tuple[str, list]:
    from .runner import TransformLog

    logs: list[TransformLog] = []
    out_chars = list(text)
    # Walk in reverse so we can mutate without remapping offsets.
    indices = [i for i, ch in enumerate(text) if ch == ";"]
    for pos in reversed(indices):
        if is_protected(pos, protected):
            continue
        if _is_in_list(text, pos):
            continue
        # Find following non-space context for classification.
        m = re.match(r"\s*(\w+)", text[pos + 1:])
        next_word = m.group(1).lower() if m else ""
        if next_word in _CONJ:
            replacement = ", "
            reason = f"semicolon before conjunction '{next_word}'"
            # Replace the ; plus following whitespace with ", ".
            ws_end = pos + 1
            while ws_end < len(out_chars) and out_chars[ws_end].isspace():
                ws_end += 1
            before = "".join(out_chars[pos:ws_end])
            out_chars[pos:ws_end] = list(replacement)
            logs.append(
                TransformLog(
                    transform="strip_semicolons",
                    site=(pos, pos + len(before)),
                    before=before,
                    after=replacement,
                    reason=reason,
                )
            )
        else:
            # `. ` plus capitalize next letter.
            ws_end = pos + 1
            while ws_end < len(out_chars) and out_chars[ws_end].isspace():
                ws_end += 1
            before = "".join(out_chars[pos:ws_end])
            replacement = ". "
            # Capitalize the letter at ws_end if it's lowercase ASCII.
            if ws_end < len(out_chars) and out_chars[ws_end].isalpha():
                out_chars[ws_end] = out_chars[ws_end].upper()
            out_chars[pos:ws_end] = list(replacement)
            logs.append(
                TransformLog(
                    transform="strip_semicolons",
                    site=(pos, pos + len(before)),
                    before=before,
                    after=replacement,
                    reason="semicolon split into two sentences",
                )
            )
    logs.reverse()
    return "".join(out_chars), logs


__all__ = ["apply"]
