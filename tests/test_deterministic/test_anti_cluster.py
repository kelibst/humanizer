"""Anti-cluster (sentence-length) transform tests."""
from __future__ import annotations

import random

from sis_caro_humanizer.pipeline.stage3_deterministic import anti_cluster
from sis_caro_humanizer.pipeline.stage3_deterministic.protected import (
    build_protected_spans,
)
from sis_caro_humanizer.profile.schema import Profile


def _run(text: str, seed: int = 0):
    p = Profile(profile_name="t")
    rng = random.Random(seed)
    spans = build_protected_spans(text)
    return anti_cluster.apply(text, p, rng, spans)


def test_three_similar_sentences_get_split_or_merged() -> None:
    # Three sentences, ~14 words each, tightly clustered.
    text = (
        "The results showed clearly that bystander CPR was rare in this study, "
        "and that finding was striking. "
        "The data showed clearly that the chain of survival broke very early "
        "in our cohort, but recovery was possible. "
        "The report showed clearly that training gaps were widespread across "
        "the district, and most providers agreed."
    )
    out, logs = _run(text)
    assert out != text, "expected the cluster to be broken"
    assert any(l.transform.startswith("anti_cluster") for l in logs)


def test_short_paragraph_untouched() -> None:
    text = "Only two sentences here. They are short."
    out, logs = _run(text)
    assert out == text
    assert logs == []


def test_varied_lengths_untouched() -> None:
    text = (
        "Short. "
        "A medium-length sentence with some content here, just to fill it. "
        "An exceptionally long sentence that goes on and on, weaving through "
        "subordinate clauses and tangents and parentheticals before finally "
        "settling on a conclusion."
    )
    out, logs = _run(text)
    # Lengths are 1, 11, 25 — span > 5, so no cluster.
    assert out == text
    assert logs == []
