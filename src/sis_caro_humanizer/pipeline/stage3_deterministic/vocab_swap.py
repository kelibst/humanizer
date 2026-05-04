"""Profile-driven vocabulary substitution.

For each `(source, [replacement, ...])` entry in `profile.vocabulary.preferred_swaps`:

    - find every word-boundary occurrence of `source` (case-insensitive),
    - skip any hit overlapping a protected span,
    - pick a replacement via `rng.choice(replacements)`,
    - vary picks across the document so the same source word doesn't always
      get the same swap (we re-roll for every hit),
    - preserve the original token's casing pattern (Title / UPPER / lower).

Phrasal-verb handling: when the source word is part of a known phrasal verb
(e.g. ``delve into``, ``navigate through``, ``embark on``), the trailing
preposition in the source text is *always* consumed regardless of whether
the chosen replacement also carries a preposition. This keeps every branch
grammatical:

    delve into challenges + replacement "examine"  -> "examine challenges"
    delve into challenges + replacement "look at"  -> "look at challenges"
    delve into challenges + replacement "go into"  -> "go into challenges"

Leaving the source preposition would produce broken phrases such as
``examine into challenges`` (``examine`` is transitive and does not take
``into``) or duplicate stranding such as ``look at into challenges``.
"""
from __future__ import annotations

import random
import re
from typing import TYPE_CHECKING

from .protected import overlaps_protected

if TYPE_CHECKING:
    from ...profile.schema import Profile


# Source verb + preposition pairs that behave as phrasal verbs in the input
# text. For any pair listed here, the trailing preposition is *always*
# consumed when the source verb is swapped, regardless of whether the
# chosen replacement also carries a preposition. This is the only safe
# rule: leaving the source preposition produces ungrammatical output for
# replacements that are transitive (e.g. ``examine into``) and duplicates
# for replacements that already carry a preposition (e.g. ``look at into``).
PHRASAL_HINTS: dict[tuple[str, str], bool] = {
    ("delve", "into"): True,
    ("navigate", "through"): True,
    ("navigate", "across"): True,
    ("embark", "on"): True,
    ("embark", "upon"): True,
}


def _preserve_case(source_token: str, replacement: str) -> str:
    if source_token.isupper() and len(source_token) > 1:
        return replacement.upper()
    if source_token[:1].isupper():
        # Title-case the first character, leave the rest as-is. Don't
        # capitalize each word in a multi-word replacement.
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _next_token_span(text: str, pos: int) -> tuple[int, int, str] | None:
    """Find the next word-token starting at or after `pos`. Returns
    (whitespace_start, token_end, token_lower) or None."""
    m = re.match(r"(\s+)([A-Za-z][A-Za-z\-]*)", text[pos:])
    if not m:
        return None
    ws_start = pos
    token_end = pos + m.end()
    token = m.group(2)
    return ws_start, token_end, token.lower()


def apply(
    text: str,
    profile: "Profile",
    rng: random.Random,
    protected: list[tuple[int, int]],
) -> tuple[str, list]:
    from .runner import TransformLog

    swaps = profile.vocabulary.preferred_swaps
    if not swaps:
        return text, []

    # Collect every match across all source words so we can apply right-to-left.
    Hit = tuple[int, int, str, str, list[str]]  # start, end, source_lower, original, replacements
    hits: list[Hit] = []
    for source, replacements in swaps.items():
        if not replacements:
            continue
        pat = re.compile(r"\b" + re.escape(source) + r"\b", re.IGNORECASE)
        for m in pat.finditer(text):
            hits.append(
                (m.start(), m.end(), source.lower(), m.group(0), list(replacements))
            )
    if not hits:
        return text, []

    # Sort by start, descending; deterministic order even before randomness.
    hits.sort(key=lambda h: h[0], reverse=True)

    new_text = text
    logs: list[TransformLog] = []
    for start, end, source_lower, original, replacements in hits:
        if overlaps_protected(start, end, protected):
            continue
        chosen = rng.choice(replacements)
        rendered = _preserve_case(original, chosen)

        # Phrasal-verb handling: if the source verb is followed by a
        # preposition that forms a known phrasal verb, always consume the
        # trailing source preposition, regardless of the replacement form.
        # This keeps every branch grammatical (transitive replacements
        # don't get stranded prepositions; phrasal replacements don't
        # duplicate).
        consume_end = end
        next_tok = _next_token_span(text, end)
        if next_tok is not None:
            _, tok_end, tok_lower = next_tok
            if PHRASAL_HINTS.get((source_lower, tok_lower)):
                consume_end = tok_end

        new_text = new_text[:start] + rendered + new_text[consume_end:]
        logs.append(
            TransformLog(
                transform="vocab_swap",
                site=(start, consume_end),
                before=text[start:consume_end],
                after=rendered,
                reason=f"swapped '{text[start:consume_end]}' for '{rendered}'",
            )
        )
    logs.reverse()
    return new_text, logs


__all__ = ["apply"]
