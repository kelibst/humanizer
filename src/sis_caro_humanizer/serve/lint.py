"""Lint engine for ``POST /v1/lint`` (CONTRACT v1.3 §1.1).

Returns flagged spans for editor diagnostics. Cheap; deterministic; no LLM.
Six codes:

* ``llm-vocab``        — AI-flavoured vocabulary token (info)
* ``long-sentence``    — sentence longer than ``profile.sentence_shape``'s
                         soft cap (mean + 2*std, default 41) (info)
* ``topic-perfection`` — paragraph-opening textbook-perfect topic sentence (info)
* ``list-overuse``     — triple-list pattern ``X, Y, and Z`` (info)
* ``missing-citation`` — quantitative claim without nearby citation (warning)
* ``orphan-citation``  — citation present but not in ``references.json`` (warning)

Every span check honours ``build_protected_spans`` so we never flag inside
quoted material, code fences, References sections, etc.

The two citation-related codes here cover only the prose-only (no
``references.json``) side: ``orphan-citation`` is reported when the user
calls ``/v1/lint`` with no workspace context, but we cannot detect orphans
without ``references.json`` so we emit none in that path. The full citation
analysis lives in ``/v1/citations``.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..pipeline.stage3_deterministic.protected import (
    build_protected_spans,
    overlaps_protected,
)
from ..research.citations import (
    _CITATION_PAREN_RE,
    _CLAIM_VERB_RE,
    _HEDGE_PHRASE_RE,
    _QUANT_CLAIM_RE,
    _structural_protected_spans,
)
from ..scoring.features import _LLM_FAVORED_WORDS, _TRIPLE_LIST
from ..text_utils import iter_words, split_paragraphs, split_sentences

LINT_CODES = (
    "llm-vocab",
    "long-sentence",
    "topic-perfection",
    "list-overuse",
    "missing-citation",
    "orphan-citation",
)


@dataclass
class LintSpan:
    start: int
    end: int
    code: str
    severity: str  # "info" | "warning"
    message: str
    suggestions: list[str] = field(default_factory=list)
    token: str | None = None


# ---------------------------------------------------------------------------
# Per-code scanners
# ---------------------------------------------------------------------------


def _scan_llm_vocab(text: str, profile: Any | None, protected: list[tuple[int, int]]) -> list[LintSpan]:
    out: list[LintSpan] = []
    if not _LLM_FAVORED_WORDS:
        return out
    swaps: dict[str, list[str]] = {}
    if profile is not None:
        vocab = getattr(profile, "vocabulary", None)
        if vocab is not None:
            swaps = dict(getattr(vocab, "preferred_swaps", {}) or {})
    for token in _LLM_FAVORED_WORDS:
        # Build pattern for word boundaries (single word or phrase).
        pat = re.compile(r"\b" + re.escape(token) + r"\b", re.IGNORECASE)
        for m in pat.finditer(text):
            if overlaps_protected(m.start(), m.end(), protected):
                continue
            suggestions = swaps.get(token, [])[:3]
            out.append(
                LintSpan(
                    start=m.start(),
                    end=m.end(),
                    code="llm-vocab",
                    severity="info",
                    message=f"AI-flavoured vocabulary: {token!r}",
                    token=text[m.start(): m.end()],
                    suggestions=list(suggestions),
                )
            )
    return out


def _scan_long_sentences(
    text: str, profile: Any | None, protected: list[tuple[int, int]]
) -> list[LintSpan]:
    out: list[LintSpan] = []
    # Soft cap: mean + 2*std, default 41 (~19 + 2*11).
    cap = 41.0
    if profile is not None:
        shape = getattr(profile, "sentence_shape", None)
        if shape is not None:
            mean = float(getattr(shape, "mean_words", 19.0))
            std = float(getattr(shape, "std_words", 10.0))
            cap = mean + 2.0 * std
    cap_int = int(round(cap))

    # Walk sentences but track offsets back into the original text.
    cursor = 0
    for sent in split_sentences(text):
        idx = text.find(sent, cursor)
        if idx == -1:
            continue
        end = idx + len(sent)
        cursor = end
        if overlaps_protected(idx, end, protected):
            continue
        wc = sum(1 for _ in iter_words(sent))
        if wc > cap_int:
            out.append(
                LintSpan(
                    start=idx,
                    end=end,
                    code="long-sentence",
                    severity="info",
                    message=f"Sentence is {wc} words; profile cap {cap_int}",
                    suggestions=[],
                )
            )
    return out


def _scan_topic_perfection(
    text: str, profile: Any | None, protected: list[tuple[int, int]]
) -> list[LintSpan]:
    from ..scoring.features import _looks_perfect_topic_sentence

    out: list[LintSpan] = []
    cursor = 0
    for para in split_paragraphs(text):
        para_idx = text.find(para, cursor)
        if para_idx == -1:
            continue
        cursor = para_idx + len(para)
        sents = split_sentences(para)
        if not sents:
            continue
        first = sents[0]
        s_idx = text.find(first, para_idx)
        if s_idx == -1:
            continue
        s_end = s_idx + len(first)
        if overlaps_protected(s_idx, s_end, protected):
            continue
        if _looks_perfect_topic_sentence(first):
            out.append(
                LintSpan(
                    start=s_idx,
                    end=s_end,
                    code="topic-perfection",
                    severity="info",
                    message="Textbook-perfect topic sentence opener",
                    suggestions=[],
                )
            )
    return out


def _scan_list_overuse(
    text: str, profile: Any | None, protected: list[tuple[int, int]]
) -> list[LintSpan]:
    out: list[LintSpan] = []
    for m in _TRIPLE_LIST.finditer(text):
        if overlaps_protected(m.start(), m.end(), protected):
            continue
        out.append(
            LintSpan(
                start=m.start(),
                end=m.end(),
                code="list-overuse",
                severity="info",
                message="Triple-list pattern (X, Y, and Z)",
                suggestions=[],
            )
        )
    return out


def _scan_missing_citation(
    text: str, profile: Any | None, protected: list[tuple[int, int]]
) -> list[LintSpan]:
    """Standalone variant of ``citations.analyse_citations`` — no refs needed."""
    out: list[LintSpan] = []
    structural = _structural_protected_spans(text)

    # Pre-compute all citation paren positions for proximity lookups.
    citation_offsets: list[tuple[int, int]] = []
    for m in _CITATION_PAREN_RE.finditer(text):
        if not _within(m.start(), structural):
            citation_offsets.append((m.start(), m.end()))

    def _has_nearby(claim_end: int) -> bool:
        for cs, _ in citation_offsets:
            if 0 <= cs - claim_end <= 220:
                return True
            if 0 <= claim_end - cs <= 220:
                return True
        return False

    for m in _QUANT_CLAIM_RE.finditer(text):
        if overlaps_protected(m.start(), m.end(), protected):
            continue
        if _has_nearby(m.end()):
            continue
        out.append(
            LintSpan(
                start=m.start(),
                end=m.end(),
                code="missing-citation",
                severity="warning",
                message="Quantitative claim without nearby citation",
                suggestions=[],
            )
        )

    for m in _HEDGE_PHRASE_RE.finditer(text):
        if overlaps_protected(m.start(), m.end(), protected):
            continue
        if _has_nearby(m.end()):
            continue
        out.append(
            LintSpan(
                start=m.start(),
                end=m.end(),
                code="missing-citation",
                severity="warning",
                message="Hedged claim without nearby citation",
                suggestions=[],
            )
        )

    for m in _CLAIM_VERB_RE.finditer(text):
        if overlaps_protected(m.start(), m.end(), protected):
            continue
        window = text[m.start(): m.end() + 80]
        if not re.search(r"\b\d+(?:\.\d+)?\b", window):
            continue
        if _has_nearby(m.end()):
            continue
        out.append(
            LintSpan(
                start=m.start(),
                end=m.end(),
                code="missing-citation",
                severity="warning",
                message="Numeric claim without nearby citation",
                suggestions=[],
            )
        )

    # Sort + dedupe overlap.
    out.sort(key=lambda s: s.start)
    deduped: list[LintSpan] = []
    last_end = -1
    for s in out:
        if s.start < last_end:
            continue
        deduped.append(s)
        last_end = s.end
    return deduped


def _within(pos: int, spans: list[tuple[int, int]]) -> bool:
    for s, e in spans:
        if s <= pos < e:
            return True
        if s > pos:
            break
    return False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_lint(
    text: str,
    profile: Any | None = None,
    include: Iterable[str] | None = None,
) -> tuple[list[LintSpan], float]:
    """Run lint over ``text``; return ``(spans, elapsed_ms)``.

    ``include`` filters which codes run; default = all codes except
    ``orphan-citation`` (which requires a workspace + ``references.json``
    and is exposed via ``/v1/citations``).
    """
    text = text or ""
    t0 = time.monotonic()
    if include is None:
        codes = set(LINT_CODES) - {"orphan-citation"}
    else:
        codes = {c for c in include if c in LINT_CODES}

    if not text.strip():
        return [], 0.0

    protected = build_protected_spans(text)
    spans: list[LintSpan] = []

    if "llm-vocab" in codes:
        spans.extend(_scan_llm_vocab(text, profile, protected))
    if "long-sentence" in codes:
        spans.extend(_scan_long_sentences(text, profile, protected))
    if "topic-perfection" in codes:
        spans.extend(_scan_topic_perfection(text, profile, protected))
    if "list-overuse" in codes:
        spans.extend(_scan_list_overuse(text, profile, protected))
    if "missing-citation" in codes:
        spans.extend(_scan_missing_citation(text, profile, protected))
    # ``orphan-citation`` requires workspace state; reachable only via /v1/citations.

    spans.sort(key=lambda s: (s.start, s.end))
    elapsed_ms = (time.monotonic() - t0) * 1000.0
    return spans, round(elapsed_ms, 2)


__all__ = ["LINT_CODES", "LintSpan", "run_lint"]
