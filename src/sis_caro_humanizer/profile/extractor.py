from __future__ import annotations

import re
from collections import Counter
from datetime import date
from pathlib import Path

from ..text_utils import (
    coefficient_of_variation,
    iter_words,
    sentence_lengths,
    split_paragraphs,
    split_sentences,
    word_count,
)
from .schema import (
    BlupperProbabilities,
    HedgeMix,
    ParagraphShape,
    Profile,
    PunctTarget,
    SentenceShape,
    Vocabulary,
)

_FORMAL_HEDGES = {"may", "might", "could", "suggests", "indicates", "appears", "seems"}
_INFORMAL_HEDGES_PHRASES = [
    "seems like",
    "looks like",
    "hard to say",
    "one would think",
    "it is not clear",
    "kind of",
    "sort of",
]
_TRACKED_CONNECTORS = [
    "as such",
    "however",
    "moreover",
    "and so",
    "thus",
    "therefore",
    "furthermore",
    "additionally",
    "nevertheless",
]


def _read_one(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt", ".rst", ".text", ""}:
        return path.read_text(encoding="utf-8", errors="replace")
    raise ValueError(
        f"unsupported sample file type: {path.suffix} (use .md, .txt, or .rst)"
    )


def _count_phrase(text_lower: str, phrase: str) -> int:
    return len(re.findall(rf"\b{re.escape(phrase)}\b", text_lower))


def extract_profile(name: str, sample_paths: list[Path], dialect: str = "ghanaian") -> Profile:
    raw_blocks: list[str] = []
    for p in sample_paths:
        raw_blocks.append(_read_one(Path(p)))
    text = "\n\n".join(raw_blocks)
    text_lower = text.lower()

    sents = split_sentences(text)
    paras = split_paragraphs(text)
    s_lens = sentence_lengths(sents)
    n_words = word_count(text)

    if not s_lens or n_words == 0:
        raise ValueError("sample corpus is empty or unreadable")

    mean_w = sum(s_lens) / len(s_lens)
    sd_w = (sum((v - mean_w) ** 2 for v in s_lens) / max(1, len(s_lens) - 1)) ** 0.5
    pct_short = sum(1 for v in s_lens if v < 10) / len(s_lens)
    pct_long = sum(1 for v in s_lens if v > 35) / len(s_lens)

    per_1k = lambda c: round(c * 1000.0 / n_words, 2)

    em_count = text.count("—") + text.count("–")
    semi_count = text.count(";")
    colon_count = text.count(":")
    paren_count = text.count("(")
    comma_count = text.count(",")

    formal_hits = sum(text_lower.count(f" {h} ") for h in _FORMAL_HEDGES)
    informal_hits = sum(_count_phrase(text_lower, p) for p in _INFORMAL_HEDGES_PHRASES)
    total_hedges = formal_hits + informal_hits + 1
    formal_share = formal_hits / total_hedges
    informal_share = informal_hits / total_hedges

    connectors = {
        c: per_1k(_count_phrase(text_lower, c))
        for c in _TRACKED_CONNECTORS
        if _count_phrase(text_lower, c) > 0
    }

    p_lens = [word_count(p) for p in paras] or [1]
    para_cv = coefficient_of_variation(p_lens)

    word_counter = Counter(w.lower() for w in iter_words(text))
    must_use_candidates = [
        w for w, _ in word_counter.most_common(50) if len(w) > 3 and w.isalpha()
    ][:8]

    profile = Profile(
        profile_name=name,
        extracted_from=[Path(p).name for p in sample_paths],
        extracted_at=date.today(),
        word_count_basis=n_words,
        dialect=dialect,  # type: ignore[arg-type]
        sentence_shape=SentenceShape(
            mean_words=round(mean_w, 1),
            std_words=round(sd_w, 1),
            pct_short_lt10=round(pct_short, 3),
            pct_long_gt35=round(pct_long, 3),
            max_consecutive_similar=2,
        ),
        punctuation_per_1000w={
            "em_dash": PunctTarget(target=per_1k(em_count), hard_cap=0.0),
            "semicolon": PunctTarget(target=per_1k(semi_count), hard_cap=2.0),
            "colon": PunctTarget(target=per_1k(colon_count)),
            "parenthesis": PunctTarget(target=per_1k(paren_count)),
            "comma": PunctTarget(target=per_1k(comma_count)),
        },
        vocabulary=Vocabulary(
            must_use=must_use_candidates,
            never_use=[
                "delve",
                "tapestry",
                "leverage",
                "navigate",
                "multifaceted",
                "in conclusion",
                "to summarize",
                "it is worth noting",
            ],
            preferred_swaps={
                "delve": ["examine", "look at", "go into"],
                "leverage": ["use", "draw on"],
                "navigate": ["work through", "deal with"],
                "foster": ["build", "encourage"],
                "intricate": ["complicated", "layered"],
                "ensure": ["make sure", "see to it that"],
            },
            repetition_tolerance="high",
        ),
        connectors_per_1000w=connectors,
        blupper_probabilities=BlupperProbabilities(
            article_drop_ghanaian=0.12 if dialect == "ghanaian" else 0.0,
        ),
        hedge_mix=HedgeMix(
            formal_share=round(formal_share, 2),
            informal_share=round(informal_share, 2),
        ),
        paragraph_shape=ParagraphShape(
            length_cv_min=max(0.35, round(para_cv * 0.85, 2)),
        ),
    )
    return profile
