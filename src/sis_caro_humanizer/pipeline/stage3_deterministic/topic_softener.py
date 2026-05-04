"""Soften 'perfect' topic sentences.

Track the running paragraph-perfection rate (same heuristic as
`scoring.features.topic_sentence_perfection`). When the cumulative rate
exceeds `profile.paragraph_shape.topic_sentence_perfection_max`, prepend a
thinking-marker phrase from `profile.paragraph_shape.thinking_markers` to
the next perfect-looking topic sentence and lowercase its original first
character.
"""
from __future__ import annotations

import random
import re
from typing import TYPE_CHECKING

from ...text_utils import split_paragraphs, word_count
from .protected import is_protected

if TYPE_CHECKING:
    from ...profile.schema import Profile


# Mirrors the perfection heuristic in features.py but kept local so the
# scoring side and the rewriter side can drift independently.
_FORMAL_HEDGES = {
    "may", "might", "could", "would", "suggests", "suggest",
    "appears", "seems", "indicates", "indicate", "implies", "imply",
}
_INFORMAL_HEDGES = [
    "seems like", "looks like", "hard to say",
    "one would think", "kind of", "sort of",
]


def _looks_perfect(sentence: str) -> bool:
    wc = word_count(sentence)
    if wc < 12 or wc > 22:
        return False
    s = sentence.lstrip()
    if not s or not s[0].isalpha() or not s[0].isupper():
        return False
    low = s.lower()
    if any(re.search(r"\b" + re.escape(h) + r"\b", low) for h in _FORMAL_HEDGES):
        return False
    if any(p in low for p in _INFORMAL_HEDGES):
        return False
    if re.match(r"(interestingly|of course|looking at|from the table|what stands out|this raises|and |but )", low):
        return False
    return True


def apply(
    text: str,
    profile: "Profile",
    rng: random.Random,
    protected: list[tuple[int, int]],
) -> tuple[str, list]:
    from .runner import TransformLog

    cap = profile.paragraph_shape.topic_sentence_perfection_max
    markers = list(profile.paragraph_shape.thinking_markers)
    if not markers:
        return text, []

    paras = split_paragraphs(text)
    if not paras:
        return text, []

    # Track which paragraphs we'll soften, then splice back the original
    # text using a left-to-right scan so we know each paragraph's offset.
    perfect_so_far = 0
    seen = 0
    soften: list[int] = []  # indices into `paras` that should be softened
    for i, p in enumerate(paras):
        # Only consider the first sentence as a topic sentence.
        first = re.split(r"(?<=[.!?])\s+", p, maxsplit=1)[0]
        seen += 1
        if not _looks_perfect(first):
            continue
        # Hypothetically include this paragraph's first sentence as perfect.
        rate_if_kept = (perfect_so_far + 1) / seen
        if rate_if_kept > cap:
            soften.append(i)
            # We "fix" it, so don't count it as perfect in the running tally.
        else:
            perfect_so_far += 1

    if not soften:
        return text, []

    logs: list[TransformLog] = []
    # Now splice back into `text` at the actual paragraph offsets.
    new_text = text
    # Find paragraph offsets in the *original* text. `split_paragraphs` strips
    # them, so we re-locate by searching forward.
    offset = 0
    para_offsets: list[int] = []
    for p in paras:
        idx = new_text.find(p, offset)
        if idx == -1:
            # Shouldn't happen, but skip if so.
            para_offsets.append(-1)
            continue
        para_offsets.append(idx)
        offset = idx + len(p)

    # Apply right-to-left.
    for i in sorted(soften, reverse=True):
        para_offset = para_offsets[i]
        if para_offset < 0:
            continue
        if is_protected(para_offset, protected):
            continue
        para = paras[i]
        marker = rng.choice(markers)
        # Lowercase the first letter of the original paragraph.
        if para and para[0].isalpha():
            new_first = para[0].lower() + para[1:]
        else:
            new_first = para
        new_para = f"{marker} {new_first}"
        before = para
        after = new_para
        new_text = (
            new_text[:para_offset]
            + new_para
            + new_text[para_offset + len(para):]
        )
        logs.append(
            TransformLog(
                transform="topic_softener",
                site=(para_offset, para_offset + len(para)),
                before=before[:80] + ("…" if len(before) > 80 else ""),
                after=after[:80] + ("…" if len(after) > 80 else ""),
                reason=f"prepended thinking marker '{marker}' to soften topic sentence",
            )
        )
    logs.reverse()
    return new_text, logs


__all__ = ["apply"]
