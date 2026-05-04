"""Break clusters of same-length sentences.

Per researchRules § 21: avoid 3+ sentences in a row that are roughly the
same length. We slide a 3-sentence window across each paragraph; if
`max_len - min_len < 5` and `mean_len > 12` (i.e. tightly clustered, not
short staccato), we either:

    - split the longest sentence at a coordinator (`, and `, `, but `,
      ` because `, ` since `) into two sentences, OR
    - merge the shortest sentence with its successor (turning two short
      sentences into one comma-joined sentence).

Apply at most once per paragraph; run last so it sees the final structure.
"""
from __future__ import annotations

import random
import re
from typing import TYPE_CHECKING

from ...text_utils import word_count
from .protected import overlaps_protected

if TYPE_CHECKING:
    from ...profile.schema import Profile


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])")
_COORD_PATTERNS = (
    re.compile(r",\s+and\s+"),
    re.compile(r",\s+but\s+"),
    re.compile(r"\s+because\s+"),
    re.compile(r"\s+since\s+"),
    re.compile(r",\s+so\s+"),
)


def _split_into_sentences(paragraph: str) -> list[tuple[int, int, str]]:
    """Return [(start, end, sentence)] inside the paragraph string."""
    out: list[tuple[int, int, str]] = []
    cursor = 0
    # Use finditer to locate split points; each split point is a delimiter
    # *between* sentences, so sentence i ends at split_point i's start.
    splits = [(m.start(), m.end()) for m in _SENT_SPLIT.finditer(paragraph)]
    for s_start, s_end in splits:
        out.append((cursor, s_start, paragraph[cursor:s_start]))
        cursor = s_end
    if cursor < len(paragraph):
        out.append((cursor, len(paragraph), paragraph[cursor:]))
    return out


def _split_at_coordinator(sentence: str) -> str | None:
    """Split a long sentence at a coordinator. Returns the rewritten sentence
    or None if no suitable split point is found.
    """
    # Find the LATEST coordinator past the half-point so we get two non-trivial
    # halves.
    half = len(sentence) // 2
    best: tuple[int, int] | None = None  # (start, end) of the coordinator span
    for pat in _COORD_PATTERNS:
        for m in pat.finditer(sentence):
            if m.start() < half:
                continue
            if best is None or m.start() > best[0]:
                best = (m.start(), m.end())
    if best is None:
        return None
    start, end = best
    # The text up to `start` is clause A (without trailing punctuation); from
    # `end` onwards is clause B.
    a = sentence[:start].rstrip()
    b = sentence[end:].lstrip()
    if not a or not b:
        return None
    # Strip trailing punctuation from `a` (we'll add `.`) and trailing space.
    a = a.rstrip(",;:")
    if not a.endswith((".", "!", "?")):
        a = a + "."
    # Capitalize start of B.
    if b and b[0].isalpha():
        b = b[0].upper() + b[1:]
    # If the original sentence ended in `.`, keep that; otherwise punctuate.
    if not b.endswith((".", "!", "?")):
        b = b + sentence[-1] if sentence and sentence[-1] in ".!?" else b + "."
    return f"{a} {b}"


def _merge_with_next(a: str, b: str) -> str:
    # Drop terminator from `a`, lowercase first letter of `b`, comma-join.
    a_stripped = a.rstrip().rstrip(".!?")
    b_lower = b
    if b_lower and b_lower[0].isalpha():
        b_lower = b_lower[0].lower() + b_lower[1:]
    return f"{a_stripped}, {b_lower}"


def apply(
    text: str,
    profile: "Profile",
    rng: random.Random,
    protected: list[tuple[int, int]],
) -> tuple[str, list]:
    from .runner import TransformLog

    logs: list[TransformLog] = []
    paras = text.split("\n\n")
    new_paras: list[str] = []
    cursor = 0  # absolute offset in `text`

    for para in paras:
        para_start = cursor
        cursor += len(para) + 2
        sents = _split_into_sentences(para)
        if len(sents) < 3:
            new_paras.append(para)
            continue
        lens = [word_count(s[2]) for s in sents]
        # Slide a window of 3.
        target_window: tuple[int, int, int] | None = None
        for i in range(len(lens) - 2):
            window = lens[i:i + 3]
            if max(window) - min(window) < 5 and sum(window) / 3 > 12:
                target_window = (i, i + 1, i + 2)
                break
        if target_window is None:
            new_paras.append(para)
            continue

        a, b, c = target_window
        # Try to split the longest first.
        idxs_by_len = sorted([a, b, c], key=lambda i: lens[i], reverse=True)
        new_para = para
        applied = False
        for idx in idxs_by_len:
            s_start, s_end, sent = sents[idx]
            abs_start = para_start + s_start
            abs_end = para_start + s_end
            if overlaps_protected(abs_start, abs_end, protected):
                continue
            split = _split_at_coordinator(sent)
            if split is not None:
                new_para = para[:s_start] + split + para[s_end:]
                logs.append(
                    TransformLog(
                        transform="anti_cluster.split",
                        site=(abs_start, abs_end),
                        before=sent[:60] + ("…" if len(sent) > 60 else ""),
                        after=split[:60] + ("…" if len(split) > 60 else ""),
                        reason="split long sentence in same-length cluster",
                    )
                )
                applied = True
                break
        if not applied:
            # Fallback: merge the shortest with its successor.
            shortest_idx = min([a, b, c], key=lambda i: lens[i])
            successor = shortest_idx + 1
            if successor < len(sents):
                s_start, _s_end, sent_a = sents[shortest_idx]
                _t_start, t_end, sent_b = sents[successor]
                abs_start = para_start + s_start
                abs_end = para_start + t_end
                if not overlaps_protected(abs_start, abs_end, protected):
                    merged = _merge_with_next(sent_a, sent_b)
                    new_para = para[:s_start] + merged + para[t_end:]
                    logs.append(
                        TransformLog(
                            transform="anti_cluster.merge",
                            site=(abs_start, abs_end),
                            before=(sent_a + " " + sent_b)[:60] + "…",
                            after=merged[:60] + ("…" if len(merged) > 60 else ""),
                            reason="merged short sentence into successor in same-length cluster",
                        )
                    )
                    applied = True
        new_paras.append(new_para)

    return "\n\n".join(new_paras), logs


__all__ = ["apply"]
