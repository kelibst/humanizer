"""Smoke tests for the AI-risk scorer."""
from __future__ import annotations

from sis_caro_humanizer.scoring import ai_risk_score
from sis_caro_humanizer.scoring.features import all_features


LLM_FLAVORED = (
    "In the modern era, organisations must delve into multifaceted, intricate, and "
    "nuanced challenges — they must leverage cutting-edge tools, foster comprehensive "
    "alignment, and underscore robust, holistic strategies. This raises a pivotal "
    "concern; namely, that paradigm shifts are unprecedented in scope. Furthermore, "
    "such groundbreaking endeavours illuminate the seamless tapestry of synergy. "
    "Moreover, leaders may navigate this realm with profound clarity. The data, the "
    "models, and the policies all align — they encompass diverse considerations.\n\n"
    "Additionally, the analysis underscores a transformative paradigm. It elucidates "
    "the intersection of theory, practice, and policy in the modern landscape. The "
    "researchers may consider that such streamlined approaches could revolutionize "
    "the field; they might further illuminate quintessential dynamics. Notwithstanding "
    "limitations, the work appears to articulate a profoundly indispensable beacon."
)


HUMAN_HANDWRITTEN = (
    "Bystander CPR rates are low at the hospital. We saw this in the death "
    "register. Twelve patients arrived dead. Of those, only two had any sign of "
    "compression marks on the chest, and the family of one was not even sure who "
    "tried. Looking at the data above, it seems like the chain of survival breaks "
    "very early. As such, training matters.\n\n"
    "Our nurse-in-charge said the same thing during the bereavement interview. She "
    "kept repeating it: people freeze, they freeze and then they call. By the time "
    "the call goes through, the person is gone. One would think the ambulance "
    "would arrive, but in this district that is hard to say with certainty.\n\n"
    "And the families know. They know because they have seen it happen before. "
    "Bystander CPR is not common here. We have to start somewhere."
)


def test_components_in_unit_range() -> None:
    for txt in (LLM_FLAVORED, HUMAN_HANDWRITTEN):
        comps = all_features(txt)
        # v1.4 added a 7th feature (perplexity).
        assert len(comps) == 7
        for c in comps:
            assert 0.0 <= c.value <= 1.0, f"{c.name} out of range: {c.value}"


def test_llm_paragraph_scores_high() -> None:
    """v1.4: with the perplexity feature disabled in the test suite (see
    conftest.py / HUMANIZE_DISABLE_PERPLEXITY), the heuristic stack alone
    still pushes the LLM-flavoured paragraph above the LOW band. Live
    runs with the perplexity feature on routinely score > 0.7."""
    rep = ai_risk_score(LLM_FLAVORED)
    assert rep.score > 0.4, f"expected > 0.4, got {rep.score:.3f}"
    assert rep.band in ("medium", "high")


def test_human_paragraph_scores_low() -> None:
    rep = ai_risk_score(HUMAN_HANDWRITTEN)
    assert rep.score < 0.4, f"expected < 0.4, got {rep.score:.3f}"
    assert rep.band == "low"


def test_brief_one_liner_short_circuit() -> None:
    rep = ai_risk_score("Hello world.")
    # Should not crash and should return a band.
    assert rep.band in ("low", "medium", "high")


def test_score_report_shape() -> None:
    rep = ai_risk_score(LLM_FLAVORED)
    names = {c.name for c in rep.components}
    assert names == {
        "burstiness_deficit",
        "punct_signature",
        "llm_vocab_density",
        "triple_list_rate",
        "topic_sentence_perfection",
        "hedge_formality_skew",
        "perplexity",
    }
    # v1.4 weights sum to 1.0 (was 0.85 in v1.3 with 6 features).
    weights = sum(c.weight for c in rep.components)
    assert abs(weights - 1.0) < 1e-6
