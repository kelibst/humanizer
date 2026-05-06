"""Citation hygiene analysis (CONTRACT §1.4).

Three findings:

* **Missing** — quantitative claim or hedged claim with no nearby
  ``(Author, Year)`` parenthetical.
* **Orphan** — ``(Author, Year)`` in prose with no matching entry in
  ``references.json``.
* **Unused** — entry in ``references.json`` not cited anywhere in prose.

All scanning honours ``build_protected_spans`` so we don't flag claims
inside code fences, quoted material, or the References section itself.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..pipeline.stage3_deterministic.protected import (
    build_protected_spans,
    overlaps_protected,
)
from .refs_store import Reference, _last_name_from_author


# ---------------------------------------------------------------------------
# Public dataclasses (CONTRACT §1.4)
# ---------------------------------------------------------------------------


@dataclass
class MissingCitation:
    start: int
    end: int
    claim: str


@dataclass
class OrphanCitation:
    start: int
    end: int
    key: str


@dataclass
class UnusedReference:
    id: str
    raw_apa: str


@dataclass
class CitationsReport:
    missing: list[MissingCitation] = field(default_factory=list)
    orphans: list[OrphanCitation] = field(default_factory=list)
    unused: list[UnusedReference] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Citation parenthetical: matches "(Smith, 2020)", "(Smith & Doe, 2020)",
# "(Smith, Doe, & Tan, 2020)", "(Smith et al., 2020)", "(Smith, 2020a)".
_CITATION_PAREN_RE = re.compile(
    r"\("
    r"(?P<key>"
    r"[A-Z][\w\-']+"
    r"(?:\s+et\s+al\.)?"
    r"(?:\s*(?:,\s+|\s+(?:and|&)\s+)[A-Z][\w\-']+)*"
    r")"
    r"\s*,\s*"
    r"(?P<year>\d{4}[a-z]?)"
    r"(?:,\s*p{1,2}\.\s*\d+(?:[–\-]\d+)?)?"
    r"\)"
)

# Quantitative claim: a percentage / large number that should be sourced.
_QUANT_CLAIM_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:%|percent\b|per\s+cent\b|per\s+1000\b|per\s+capita\b)",
    re.IGNORECASE,
)

# Hedge phrases that often precede an unsourced claim.
_HEDGE_PHRASES = [
    "studies show",
    "studies have shown",
    "research has shown",
    "research shows",
    "research suggests",
    "evidence suggests",
    "evidence shows",
    "according to",
    "it has been shown",
    "it has been found",
    "it is well established",
    "it is widely accepted",
    "it is reported that",
    "scholars argue",
    "researchers (?:have )?found",
    "researchers (?:have )?reported",
    "experts (?:have )?argued",
]
_HEDGE_PHRASE_RE = re.compile(
    r"\b(?:" + "|".join(_HEDGE_PHRASES) + r")\b",
    re.IGNORECASE,
)

# Claim verbs near a number.
_CLAIM_VERB_RE = re.compile(
    r"\b(?:found|demonstrated|reported|showed|revealed|concluded)\b",
    re.IGNORECASE,
)

# Window in characters: a citation must appear within this distance after the
# claim to count as "supporting" it.
_CITATION_PROXIMITY = 220


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _author_keys(authors: list[str]) -> list[str]:
    """Lowercase last-name forms of each author."""
    return [_last_name_from_author(a) for a in authors if a]


def _matches_reference(citation_key: str, refs: list[Reference], year: str) -> bool:
    """Does ``citation_key`` (e.g. ``"Smith"`` or ``"Smith & Doe"``) and
    ``year`` resolve to any record in ``refs``?

    Strategy: split the key on ``,``, ``&``, or ``and``; the first author
    surname must match the lowercase last-name of any author in a record
    whose year matches. ``et al.`` collapses to the lead author only.
    """
    # Normalise.
    key = citation_key.strip()
    key = re.sub(r"\s*&\s*", " ", key)
    key = re.sub(r"\s+and\s+", " ", key)
    key = re.sub(r"\s+et\s+al\.?", "", key, flags=re.IGNORECASE)
    parts = [p.strip() for p in re.split(r"[,\s]+", key) if p.strip()]
    if not parts:
        return False
    lead = parts[0].lower()

    # Year normalisation: drop trailing letter.
    year_digits = re.match(r"(\d{4})", year)
    if not year_digits:
        return False
    year_int = int(year_digits.group(1))

    for r in refs:
        if r.year != year_int:
            continue
        keys = _author_keys(r.authors)
        if lead in keys:
            return True
    return False


def _ref_is_cited(ref: Reference, citations: list[tuple[str, str, int, int]]) -> bool:
    keys = _author_keys(ref.authors)
    for key, yr, _, _ in citations:
        # Match any author in the reference (loose; APA citations only show
        # the first author after a few co-authors anyway).
        key_norm = re.sub(r"\s*&\s*", " ", key)
        key_norm = re.sub(r"\s+and\s+", " ", key_norm)
        key_norm = re.sub(r"\s+et\s+al\.?", "", key_norm, flags=re.IGNORECASE)
        head_match = re.match(r"[A-Za-z][\w\-']+", key_norm)
        if not head_match:
            continue
        lead = head_match.group(0).lower()
        if lead in keys:
            yr_m = re.match(r"(\d{4})", yr)
            if yr_m and int(yr_m.group(1)) == ref.year:
                return True
    return False


def _claim_snippet(text: str, start: int, end: int, width: int = 80) -> str:
    snippet = text[start:end]
    # Pad to reach ``width`` chars total — useful in the UI.
    if len(snippet) >= width:
        return snippet[:width]
    pad_each = (width - len(snippet)) // 2
    s2 = max(0, start - pad_each)
    e2 = min(len(text), end + pad_each)
    return text[s2:e2].strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyse_citations(
    text: str,
    refs: list[Reference],
    profile: Any | None = None,
) -> CitationsReport:
    """Run the three-way analysis. ``profile`` reserved for future tuning."""
    text = text or ""
    if not text:
        return CitationsReport()

    protected = build_protected_spans(text)

    # ---- 1. Collect citations in prose (skip ones in protected spans
    # *other than* the citation-pattern protection itself; build_protected_spans
    # marks them as protected so we walk the text directly using our own
    # citation regex). ----
    citations: list[tuple[str, str, int, int]] = []
    # We need to ignore citations inside code fences, quotes, table rows,
    # blockquotes, and the References section. The citation-paren protection
    # itself trivially overlaps every (Author, Year) so we can't just check
    # ``overlaps_protected`` — instead we rebuild "structural protected
    # spans" without the citation guard.
    structural_protected = _structural_protected_spans(text)

    for m in _CITATION_PAREN_RE.finditer(text):
        if _within(m.start(), structural_protected):
            continue
        citations.append((m.group("key"), m.group("year"), m.start(), m.end()))

    # ---- 2. Orphans: citation present but no matching reference ----
    orphans: list[OrphanCitation] = []
    for key, yr, start, end in citations:
        if not _matches_reference(key, refs, yr):
            orphans.append(
                OrphanCitation(start=start, end=end, key=f"{key}, {yr}")
            )

    # ---- 3. Unused: reference exists, never cited ----
    unused: list[UnusedReference] = []
    for r in refs:
        if not _ref_is_cited(r, citations):
            unused.append(UnusedReference(id=r.id, raw_apa=r.raw_apa))

    # ---- 4. Missing: claim with no proximate citation ----
    citation_offsets = [(c[2], c[3]) for c in citations]
    missing: list[MissingCitation] = []

    def _has_nearby_citation(claim_end: int) -> bool:
        for cs, _ce in citation_offsets:
            if 0 <= cs - claim_end <= _CITATION_PROXIMITY:
                return True
            # Also accept a citation immediately before the claim.
            if 0 <= claim_end - cs <= _CITATION_PROXIMITY:
                return True
        return False

    for m in _QUANT_CLAIM_RE.finditer(text):
        if overlaps_protected(m.start(), m.end(), protected):
            continue
        if _within(m.start(), structural_protected):
            continue
        if not _has_nearby_citation(m.end()):
            missing.append(
                MissingCitation(
                    start=m.start(),
                    end=m.end(),
                    claim=_claim_snippet(text, m.start(), m.end()),
                )
            )

    for m in _HEDGE_PHRASE_RE.finditer(text):
        if overlaps_protected(m.start(), m.end(), protected):
            continue
        if _within(m.start(), structural_protected):
            continue
        if not _has_nearby_citation(m.end()):
            missing.append(
                MissingCitation(
                    start=m.start(),
                    end=m.end(),
                    claim=_claim_snippet(text, m.start(), m.end()),
                )
            )

    # Claim verbs are noisier — only flag them when adjacent to a number.
    for m in _CLAIM_VERB_RE.finditer(text):
        if overlaps_protected(m.start(), m.end(), protected):
            continue
        if _within(m.start(), structural_protected):
            continue
        # Look at the next 80 chars for a number.
        window = text[m.start(): m.end() + 80]
        if not re.search(r"\b\d+(?:\.\d+)?\b", window):
            continue
        if _has_nearby_citation(m.end()):
            continue
        missing.append(
            MissingCitation(
                start=m.start(),
                end=m.end(),
                claim=_claim_snippet(text, m.start(), m.end()),
            )
        )

    # Sort missing by position and deduplicate exact-overlap entries.
    missing.sort(key=lambda c: c.start)
    deduped: list[MissingCitation] = []
    last_end = -1
    for c in missing:
        if c.start < last_end:
            continue
        deduped.append(c)
        last_end = c.end

    return CitationsReport(missing=deduped, orphans=orphans, unused=unused)


# ---------------------------------------------------------------------------
# Structural protected spans (everything except citation parentheticals)
# ---------------------------------------------------------------------------


def _within(pos: int, spans: list[tuple[int, int]]) -> bool:
    for s, e in spans:
        if s <= pos < e:
            return True
        if s > pos:
            break
    return False


def _structural_protected_spans(text: str) -> list[tuple[int, int]]:
    """Subset of ``build_protected_spans`` that excludes the citation-paren
    rule.

    We need to flag orphan citations *inside* a citation paren (every
    citation does, by definition), so we can't filter them out using the
    full protected list. This function returns the *other* protections.
    """
    from ..pipeline.stage3_deterministic.protected import (
        _ascii_squote_spans,
        _ASCII_DQUOTE,
        _BLOCKQUOTE,
        _CURLY_DQUOTE,
        _CURLY_SQUOTE,
        _FENCED,
        _findall_spans,
        _INLINE_CODE,
        _INLINE_MATH,
        _merge,
        _references_spans,
        _TABLE_ROW,
    )

    spans: list[tuple[int, int]] = []
    spans.extend(_findall_spans(_FENCED, text))
    spans.extend(_findall_spans(_INLINE_CODE, text))
    spans.extend(_findall_spans(_ASCII_DQUOTE, text))
    spans.extend(_findall_spans(_CURLY_DQUOTE, text))
    spans.extend(_findall_spans(_CURLY_SQUOTE, text))
    spans.extend(_findall_spans(_INLINE_MATH, text))
    spans.extend(_findall_spans(_TABLE_ROW, text))
    spans.extend(_findall_spans(_BLOCKQUOTE, text))
    spans.extend(_ascii_squote_spans(text))
    spans.extend(_references_spans(text))
    return _merge(spans)


__all__ = [
    "CitationsReport",
    "MissingCitation",
    "OrphanCitation",
    "UnusedReference",
    "analyse_citations",
]
