"""Voice consistency cross-section analysis (Phase 4).

Computes per-section feature vectors from the scoring heuristics and flags
sections that deviate significantly from the document average ("voice outliers").

This is purely additive and heuristic — it provides signals to the user but
does NOT modify any text.

Algorithm
---------
For each section (defined by ATX headings), we compute a lightweight feature
vector:

* ``avg_sent_len``    — mean sentence length in words.
* ``llm_density``     — LLM-phrase density from the existing scorer.
* ``hedge_density``   — hedge-phrase density.
* ``passive_density`` — passive-voice density.

We then compute the z-score of each feature relative to the document mean and
flag sections where the mean absolute z-score exceeds ``threshold`` (default
1.5 σ).

Output
------
A list of :class:`VoiceDiffResult` records, one per section.  The ``is_outlier``
flag is True for sections that deviate from the document voice signature.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _avg_sent_len(text: str) -> float:
    sents = [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]
    if not sents:
        return 0.0
    return sum(len(s.split()) for s in sents) / len(sents)


def _word_density(pattern: re.Pattern, text: str) -> float:
    words = len(text.split())
    if words == 0:
        return 0.0
    return len(pattern.findall(text)) / words


_LLM_PHRASES = re.compile(
    r"\b(furthermore|moreover|additionally|it is worth noting|"
    r"in conclusion|to summarize|notably|significantly|"
    r"delve|tapestry|multifaceted|leverage|robust|stakeholder)\b",
    re.IGNORECASE,
)

_HEDGE_PHRASES = re.compile(
    r"\b(may|might|could|suggests?|appears? to|seems? to|"
    r"it is (possible|likely|suggested)|possibly|perhaps|arguably)\b",
    re.IGNORECASE,
)

_PASSIVE_RE = re.compile(
    r"\b(?:is|are|was|were|been|being)\s+\w+ed\b",
    re.IGNORECASE,
)


def _feature_vector(text: str) -> dict[str, float]:
    return {
        "avg_sent_len": _avg_sent_len(text),
        "llm_density": _word_density(_LLM_PHRASES, text),
        "hedge_density": _word_density(_HEDGE_PHRASES, text),
        "passive_density": _word_density(_PASSIVE_RE, text),
    }


# ---------------------------------------------------------------------------
# Section parsing
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _split_into_sections(text: str) -> list[tuple[str, str]]:
    """Return list of (heading_title, body_text) pairs."""
    headings = list(_HEADING_RE.finditer(text))
    if not headings:
        return [("(body)", text)]
    sections: list[tuple[str, str]] = []
    for i, m in enumerate(headings):
        title = m.group(2).strip()
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[start:end].strip()
        sections.append((title, body))
    return sections


# ---------------------------------------------------------------------------
# Outlier detection
# ---------------------------------------------------------------------------

@dataclass
class VoiceDiffResult:
    title: str
    word_count: int
    features: dict[str, float]
    z_scores: dict[str, float]
    mean_abs_z: float
    is_outlier: bool
    outlier_features: list[str] = field(default_factory=list)


def analyse_voice(text: str, *, threshold: float = 1.5) -> list[VoiceDiffResult]:
    """Analyse per-section voice consistency.

    Parameters
    ----------
    text:
        Full document markdown text.
    threshold:
        Mean absolute z-score threshold above which a section is flagged.

    Returns
    -------
    One :class:`VoiceDiffResult` per section (only sections > 30 words).
    """
    sections = _split_into_sections(text)
    # Filter to substantive sections
    eligible = [
        (title, body)
        for title, body in sections
        if len(body.split()) >= 30
    ]
    if len(eligible) < 2:
        # Not enough sections to compare
        return [
            VoiceDiffResult(
                title=title,
                word_count=len(body.split()),
                features=_feature_vector(body),
                z_scores={},
                mean_abs_z=0.0,
                is_outlier=False,
            )
            for title, body in eligible
        ]

    # Compute feature vectors
    fvecs = [_feature_vector(body) for _, body in eligible]
    feature_names = list(fvecs[0].keys())

    # Compute z-scores per feature
    results: list[VoiceDiffResult] = []
    for i, (title, body) in enumerate(eligible):
        z: dict[str, float] = {}
        for feat in feature_names:
            values = [fv[feat] for fv in fvecs]
            mean = statistics.mean(values)
            try:
                std = statistics.stdev(values)
            except statistics.StatisticsError:
                std = 0.0
            if std == 0.0:
                z[feat] = 0.0
            else:
                z[feat] = (fvecs[i][feat] - mean) / std

        mean_abs_z = sum(abs(v) for v in z.values()) / len(z) if z else 0.0
        outlier_feats = [f for f, v in z.items() if abs(v) >= threshold]
        results.append(
            VoiceDiffResult(
                title=title,
                word_count=len(body.split()),
                features=fvecs[i],
                z_scores=z,
                mean_abs_z=round(mean_abs_z, 3),
                is_outlier=mean_abs_z >= threshold,
                outlier_features=outlier_feats,
            )
        )
    return results


__all__ = ["VoiceDiffResult", "analyse_voice"]
