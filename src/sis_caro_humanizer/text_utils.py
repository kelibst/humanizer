"""Lightweight tokenization and segmentation. No spaCy dependency."""
from __future__ import annotations

import re
from typing import Iterator

# Sentence terminators followed by space + capital letter, or end of input.
# Tolerates abbreviations crudely by requiring a following space + uppercase or end.
_SENT_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])")
_PARA_BREAK = re.compile(r"\n{2,}")
_WORD = re.compile(r"\b[\w'-]+\b", re.UNICODE)


def split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in _PARA_BREAK.split(text) if p.strip()]


def split_sentences(text: str) -> list[str]:
    """Split into sentences; respects paragraph boundaries.

    Crude: a single regex over each paragraph. Misses some abbreviations
    ("Dr. Smith"), but fast and zero-dep.
    """
    out: list[str] = []
    for para in split_paragraphs(text):
        # First pass: regex-split.
        parts = _SENT_END.split(para)
        for p in parts:
            p = p.strip()
            if p:
                out.append(p)
    return out


def iter_words(text: str) -> Iterator[str]:
    for m in _WORD.finditer(text):
        yield m.group(0)


def word_count(text: str) -> int:
    return sum(1 for _ in iter_words(text))


def sentence_lengths(sentences: list[str]) -> list[int]:
    return [word_count(s) for s in sentences]


def coefficient_of_variation(values: list[int | float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    sd = var**0.5
    return sd / mean
