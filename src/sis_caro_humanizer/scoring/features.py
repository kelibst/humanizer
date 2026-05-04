"""Six pure feature functions for the AI-risk scorer.

Each function takes raw text and returns a `FeatureContribution`. They are
deliberately independent and side-effect-free; the aggregator in
`scoring.risk` composes them and applies the sigmoid.

See CONTRACTS.md § 3 for the formulas. All component values are clamped to
[0, 1] before being returned.
"""
from __future__ import annotations

import re
from pathlib import Path

import regex as re_u

from ..text_utils import (
    coefficient_of_variation,
    iter_words,
    sentence_lengths,
    split_paragraphs,
    split_sentences,
    word_count,
)
from .risk import FeatureContribution


_LLM_FAVORED_FILE = Path(__file__).with_name("llm_favored.txt")


def _load_llm_favored() -> list[str]:
    if not _LLM_FAVORED_FILE.exists():
        return []
    return [
        line.strip().lower()
        for line in _LLM_FAVORED_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


_LLM_FAVORED_WORDS = _load_llm_favored()


# Hedge token pools. Formal hedges = AI-flavoured "may/might/could". Informal hedges
# are the conversational ones. Used by hedge_formality_skew and topic_sentence_perfection.
_FORMAL_HEDGES = {
    "may",
    "might",
    "could",
    "would",
    "suggests",
    "suggest",
    "appears",
    "appears to",
    "seems to",
    "indicates",
    "indicate",
    "implies",
    "imply",
}

_INFORMAL_HEDGES_PHRASES = [
    "seems like",
    "looks like",
    "hard to say",
    "one would think",
    "it is not clear",
    "kind of",
    "sort of",
    "i think",
    "i guess",
    "maybe",
    "probably",
    "perhaps",
]

# Triple-list pattern: "X, Y, and Z" or "X, Y and Z". Loose; no protection here.
_TRIPLE_LIST = re.compile(
    r"\b(\w[\w\s]{0,30}?),\s+(\w[\w\s]{0,30}?),?\s+and\s+(\w[\w\s]{0,30}?)\b",
    re.IGNORECASE,
)


def _examples(matches: list[str], k: int = 3) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for m in matches:
        m_norm = m.strip()
        if not m_norm or m_norm.lower() in seen:
            continue
        seen.add(m_norm.lower())
        out.append(m_norm[:60])
        if len(out) >= k:
            break
    return out


# ---------------------------------------------------------------------------
# Feature 1: burstiness_deficit
# ---------------------------------------------------------------------------
def burstiness_deficit(text: str) -> FeatureContribution:
    """Low sentence-length variance is an AI tell.

    value = clamp(1 - cv / 0.7, 0, 1)
    """
    sents = split_sentences(text)
    lens = sentence_lengths(sents)
    if len(lens) < 2:
        return FeatureContribution(
            name="burstiness_deficit",
            value=0.0,
            weight=0.18,
            detail="too few sentences to score",
            examples=[],
        )
    cv = coefficient_of_variation(lens)
    value = max(0.0, min(1.0, 1.0 - cv / 0.7))
    return FeatureContribution(
        name="burstiness_deficit",
        value=value,
        weight=0.18,
        detail=f"sentence-length CV = {cv:.2f} over {len(lens)} sentences",
        examples=[],
    )


# ---------------------------------------------------------------------------
# Feature 2: punct_signature
# ---------------------------------------------------------------------------
def punct_signature(text: str) -> FeatureContribution:
    """Em-dashes and semicolons are AI fingerprints.

    value = min(1, em_per_1k * 0.5 + semi_per_1k * 0.15)
    """
    wc = max(1, word_count(text))
    em_dashes = len(re.findall(r"—|--|\s—\s| - ", text))  # count obvious em-dashes
    em_dashes = text.count("—") + text.count(" -- ")
    semicolons = text.count(";")
    em_per_1k = em_dashes * 1000 / wc
    semi_per_1k = semicolons * 1000 / wc
    value = min(1.0, em_per_1k * 0.5 + semi_per_1k * 0.15)
    detail = f"{em_dashes} em-dashes, {semicolons} semicolons / {wc} words"
    examples: list[str] = []
    if em_dashes:
        # Show one snippet around the first em-dash.
        idx = text.find("—")
        if idx >= 0:
            examples.append(text[max(0, idx - 25): idx + 25].replace("\n", " "))
    return FeatureContribution(
        name="punct_signature",
        value=value,
        weight=0.15,
        detail=detail,
        examples=examples,
    )


# ---------------------------------------------------------------------------
# Feature 3: llm_vocab_density
# ---------------------------------------------------------------------------
def llm_vocab_density(text: str, favored: list[str] | None = None) -> FeatureContribution:
    """Frequency of AI-flavoured vocabulary per 1000 words.

    value = min(1, hits_per_1k / 8)
    """
    favored = favored if favored is not None else _LLM_FAVORED_WORDS
    if not favored:
        return FeatureContribution(
            name="llm_vocab_density",
            value=0.0,
            weight=0.20,
            detail="no llm_favored.txt loaded",
            examples=[],
        )
    wc = max(1, word_count(text))
    text_lower = text.lower()
    hits: list[str] = []
    counts: dict[str, int] = {}
    for w in favored:
        # Multi-word phrases vs single tokens; use word boundaries on edges.
        if " " in w:
            pat = re.compile(r"\b" + re.escape(w) + r"\b", re.IGNORECASE)
        else:
            pat = re.compile(r"\b" + re.escape(w) + r"\b", re.IGNORECASE)
        n = len(pat.findall(text_lower))
        if n:
            counts[w] = n
            hits.extend([w] * n)
    total = sum(counts.values())
    per_1k = total * 1000 / wc
    value = min(1.0, per_1k / 8.0)
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:3]
    examples = [f'"{w}" x{n}' for w, n in top]
    return FeatureContribution(
        name="llm_vocab_density",
        value=value,
        weight=0.20,
        detail=f"{total} hits / {wc} words ({per_1k:.1f} per 1k)",
        examples=examples,
    )


# ---------------------------------------------------------------------------
# Feature 4: triple_list_rate
# ---------------------------------------------------------------------------
def triple_list_rate(text: str) -> FeatureContribution:
    """Three-item lists per 100 sentences. AI loves the rule of three.

    value = min(1, triples_per_100_sents / 25)
    """
    sents = split_sentences(text)
    n_sents = max(1, len(sents))
    matches = _TRIPLE_LIST.findall(text)
    n_triples = len(matches)
    per_100 = n_triples * 100 / n_sents
    value = min(1.0, per_100 / 25.0)
    examples = _examples([" ".join(m) if isinstance(m, tuple) else m for m in matches])
    return FeatureContribution(
        name="triple_list_rate",
        value=value,
        weight=0.12,
        detail=f"{n_triples} triple-lists in {n_sents} sentences ({per_100:.1f} per 100)",
        examples=examples,
    )


# ---------------------------------------------------------------------------
# Feature 5: topic_sentence_perfection
# ---------------------------------------------------------------------------
def _looks_perfect_topic_sentence(sentence: str) -> bool:
    """Heuristic: 12-22 words, starts with NP-like token (capitalized, not a hedge),
    and contains no hedge token."""
    wc = word_count(sentence)
    if wc < 12 or wc > 22:
        return False
    s = sentence.lstrip()
    if not s:
        return False
    # First word must be capitalized and not in forbidden_openers / informal hedge tokens.
    first_word_match = re.match(r"[\"'\(\[]?([A-Za-z][\w'-]*)", s)
    if not first_word_match:
        return False
    first = first_word_match.group(1)
    if not first[0].isupper():
        return False
    low = s.lower()
    # Reject if any hedge token in the sentence.
    if any(re.search(r"\b" + re.escape(h) + r"\b", low) for h in _FORMAL_HEDGES):
        return False
    if any(p in low for p in _INFORMAL_HEDGES_PHRASES):
        return False
    # Reject obvious thinking-marker openers (those are the *anti-perfection* pattern).
    if re.match(r"(interestingly|of course|looking at|from the table|what stands out|this raises)", low):
        return False
    return True


def topic_sentence_perfection(text: str) -> FeatureContribution:
    """Fraction of paragraphs whose first sentence is a textbook topic sentence."""
    paras = split_paragraphs(text)
    if not paras:
        return FeatureContribution(
            name="topic_sentence_perfection",
            value=0.0,
            weight=0.10,
            detail="no paragraphs",
            examples=[],
        )
    first_sents: list[str] = []
    perfect = 0
    for p in paras:
        sents = split_sentences(p)
        if not sents:
            continue
        first = sents[0]
        first_sents.append(first)
        if _looks_perfect_topic_sentence(first):
            perfect += 1
    n = max(1, len(first_sents))
    value = max(0.0, min(1.0, perfect / n))
    examples = _examples(first_sents)
    return FeatureContribution(
        name="topic_sentence_perfection",
        value=value,
        weight=0.10,
        detail=f"{perfect}/{n} paragraphs open with textbook topic sentences",
        examples=examples,
    )


# ---------------------------------------------------------------------------
# Feature 6: hedge_formality_skew
# ---------------------------------------------------------------------------
def hedge_formality_skew(text: str) -> FeatureContribution:
    """Skew toward formal hedges (AI-style) vs informal hedges (human).

    value = clamp((formal/(formal+informal+1) - 0.6) / 0.4, 0, 1)
    """
    low = text.lower()
    formal = 0
    informal = 0
    for h in _FORMAL_HEDGES:
        formal += len(re.findall(r"\b" + re.escape(h) + r"\b", low))
    for p in _INFORMAL_HEDGES_PHRASES:
        informal += low.count(p)
    ratio = formal / (formal + informal + 1)
    value = max(0.0, min(1.0, (ratio - 0.6) / 0.4))
    return FeatureContribution(
        name="hedge_formality_skew",
        value=value,
        weight=0.10,
        detail=f"{formal} formal hedges, {informal} informal hedges (ratio={ratio:.2f})",
        examples=[],
    )


def all_features(text: str) -> list[FeatureContribution]:
    """Compute every feature in canonical order."""
    return [
        burstiness_deficit(text),
        punct_signature(text),
        llm_vocab_density(text),
        triple_list_rate(text),
        topic_sentence_perfection(text),
        hedge_formality_skew(text),
    ]


__all__ = [
    "FeatureContribution",
    "all_features",
    "burstiness_deficit",
    "hedge_formality_skew",
    "llm_vocab_density",
    "punct_signature",
    "topic_sentence_perfection",
    "triple_list_rate",
]
