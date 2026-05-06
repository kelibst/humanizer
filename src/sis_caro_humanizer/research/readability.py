"""Readability metrics + profile-target checks (CONTRACT §1.3).

Pure / deterministic; uses ``text_utils`` for sentence + word splitting and a
local zero-dep syllable counter for Flesch-Kincaid / Gunning-Fog.

The two sentence-derived metrics (``mean_sentence_words``, ``sentence_cv``)
mirror the scorer's burstiness feature — sharing ``text_utils`` keeps the
numbers consistent across the surfaces.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..text_utils import (
    coefficient_of_variation,
    iter_words,
    sentence_lengths,
    split_sentences,
    word_count,
)

if TYPE_CHECKING:  # pragma: no cover
    from ..profile.schema import Profile


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ReadabilityMetrics:
    word_count: int
    sentence_count: int
    mean_sentence_words: float
    sentence_cv: float
    flesch_kincaid_grade: float
    gunning_fog: float


@dataclass
class TargetCheck:
    target: float | int | None
    actual: float | int | None
    ok: bool | None


@dataclass
class TargetChecks:
    words_per_section: TargetCheck
    fk_grade_max: TargetCheck
    sentence_cv_min: TargetCheck


# ---------------------------------------------------------------------------
# Syllable counter (no nltk; vowel-cluster heuristic)
# ---------------------------------------------------------------------------

_VOWELS = "aeiouy"


def _count_syllables(word: str) -> int:
    """Approximate English syllable count.

    Strategy:
    - Lowercase.
    - Strip non-letters.
    - Each contiguous vowel cluster counts as 1 syllable.
    - Drop a silent trailing 'e' unless the word would otherwise have 0.
    - Floor at 1 for any non-empty word.
    """
    w = re.sub(r"[^a-zA-Z]", "", word).lower()
    if not w:
        return 0
    count = 0
    in_vowel = False
    for ch in w:
        is_v = ch in _VOWELS
        if is_v and not in_vowel:
            count += 1
        in_vowel = is_v
    if w.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


def _is_complex_word(word: str) -> bool:
    """Gunning-Fog "complex" word: 3+ syllables, not a proper noun, not a
    common verb suffix.

    The full heuristic excludes proper nouns and ``-es``/``-ed``/``-ing``
    inflections of simpler words. We approximate by allowing them to count;
    the index becomes slightly higher than a strict implementation but is
    still useful as a relative target.
    """
    if _count_syllables(word) < 3:
        return False
    # Drop obvious proper nouns (capitalised in the middle of a sentence).
    if word and word[0].isupper() and not word.isupper():
        return False
    return True


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------


def _compute_metrics(text: str) -> ReadabilityMetrics:
    sents = split_sentences(text)
    sent_count = max(0, len(sents))
    if sent_count == 0:
        return ReadabilityMetrics(
            word_count=0,
            sentence_count=0,
            mean_sentence_words=0.0,
            sentence_cv=0.0,
            flesch_kincaid_grade=0.0,
            gunning_fog=0.0,
        )

    words = list(iter_words(text))
    wc = len(words)
    if wc == 0:
        return ReadabilityMetrics(
            word_count=0,
            sentence_count=sent_count,
            mean_sentence_words=0.0,
            sentence_cv=0.0,
            flesch_kincaid_grade=0.0,
            gunning_fog=0.0,
        )

    lens = sentence_lengths(sents)
    mean_words = sum(lens) / len(lens) if lens else 0.0
    cv = coefficient_of_variation(lens)

    syllables = sum(_count_syllables(w) for w in words)
    asl = wc / sent_count
    asw = syllables / wc

    # Flesch-Kincaid grade level.
    fk = 0.39 * asl + 11.8 * asw - 15.59

    complex_count = sum(1 for w in words if _is_complex_word(w))
    pct_complex = (complex_count / wc) * 100
    fog = 0.4 * (asl + pct_complex)

    return ReadabilityMetrics(
        word_count=wc,
        sentence_count=sent_count,
        mean_sentence_words=round(mean_words, 2),
        sentence_cv=round(cv, 3),
        flesch_kincaid_grade=round(fk, 2),
        gunning_fog=round(fog, 2),
    )


# ---------------------------------------------------------------------------
# Target checking
# ---------------------------------------------------------------------------


def _profile_targets(profile: Any | None) -> tuple[Any | None, Any | None, Any | None]:
    """Pull (words_per_section, fk_grade_max, sentence_cv_min) from a profile.

    Tolerates missing ``targets`` attribute (older profiles) by returning
    Nones — which surface as ``ok: null`` in the API.
    """
    if profile is None:
        return None, None, None
    targets = getattr(profile, "targets", None)
    if targets is None:
        return None, None, None
    return (
        getattr(targets, "words_per_section", None),
        getattr(targets, "fk_grade_max", None),
        getattr(targets, "sentence_cv_min", None),
    )


def _check_targets(
    metrics: ReadabilityMetrics, profile: Any | None
) -> TargetChecks:
    wps_target, fk_target, cv_target = _profile_targets(profile)

    # words_per_section: "actual" is unknown without a section context (the
    # caller scopes the text to the section before calling). When the user
    # passes an entire document we still report None — per the contract.
    wps_actual: int | None = None
    wps_ok: bool | None = None
    if wps_target is not None:
        wps_actual = metrics.word_count
        wps_ok = wps_actual >= wps_target

    fk_actual: float | None = None
    fk_ok: bool | None = None
    if fk_target is not None:
        fk_actual = metrics.flesch_kincaid_grade
        fk_ok = fk_actual <= fk_target

    cv_actual: float | None = None
    cv_ok: bool | None = None
    if cv_target is not None:
        cv_actual = metrics.sentence_cv
        cv_ok = cv_actual >= cv_target

    return TargetChecks(
        words_per_section=TargetCheck(target=wps_target, actual=wps_actual, ok=wps_ok),
        fk_grade_max=TargetCheck(target=fk_target, actual=fk_actual, ok=fk_ok),
        sentence_cv_min=TargetCheck(target=cv_target, actual=cv_actual, ok=cv_ok),
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def compute(
    text: str, profile: Any | None = None
) -> tuple[ReadabilityMetrics, TargetChecks]:
    """Return ``(metrics, targets)`` for the given text + profile."""
    metrics = _compute_metrics(text or "")
    targets = _check_targets(metrics, profile)
    return metrics, targets


__all__ = [
    "ReadabilityMetrics",
    "TargetCheck",
    "TargetChecks",
    "compute",
]
