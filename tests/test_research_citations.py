"""Tests for research.citations (CONTRACT v1.3 §1.4)."""
from __future__ import annotations

from sis_caro_humanizer.research.citations import analyse_citations
from sis_caro_humanizer.research.refs_store import Reference


def _ref(rid: str, last: str, year: int, title: str = "T") -> Reference:
    return Reference(
        id=rid,
        authors=[f"{last}, J."],
        year=year,
        title=title,
        type="journal",
        raw_apa=f"{last}, J. ({year}). {title}.",
    )


# ---------------------------------------------------------------------------
# Orphans
# ---------------------------------------------------------------------------


def test_orphan_citation_no_matching_ref():
    text = "Recent work shows the trend (Smith, 2020). It is striking."
    refs: list[Reference] = []
    report = analyse_citations(text, refs)
    assert len(report.orphans) == 1
    o = report.orphans[0]
    assert "Smith" in o.key
    assert "2020" in o.key


def test_citation_matched_to_ref_is_not_orphan():
    text = "Recent work shows the trend (Smith, 2020). It is striking."
    refs = [_ref("smith_2020", "Smith", 2020)]
    report = analyse_citations(text, refs)
    assert report.orphans == []


# ---------------------------------------------------------------------------
# Missing
# ---------------------------------------------------------------------------


def test_missing_quantitative_claim_unsourced():
    text = "Approximately 64% of patients improved over the trial."
    report = analyse_citations(text, [])
    assert any("64%" in m.claim or "64" in m.claim for m in report.missing)


def test_missing_with_proximate_citation_is_ok():
    text = "Approximately 64% of patients improved (Smith, 2020) over the trial."
    refs = [_ref("smith_2020", "Smith", 2020)]
    report = analyse_citations(text, refs)
    assert report.missing == []


def test_missing_hedge_phrase_unsourced():
    text = "Studies show that uptake is poor in low-resource settings."
    report = analyse_citations(text, [])
    # At least one missing-citation flag for 'studies show'
    assert any("studies show" in m.claim.lower() for m in report.missing)


# ---------------------------------------------------------------------------
# Unused
# ---------------------------------------------------------------------------


def test_unused_reference_not_cited():
    text = "The introduction makes no reference to anyone in particular."
    refs = [_ref("smith_2020", "Smith", 2020)]
    report = analyse_citations(text, refs)
    assert len(report.unused) == 1
    assert report.unused[0].id == "smith_2020"


# ---------------------------------------------------------------------------
# Protected-span skip
# ---------------------------------------------------------------------------


def test_protected_span_skip_inside_code_fence():
    text = (
        "Outside the fence we make no claims.\n\n"
        "```\n"
        "Studies show 99% improvement here.\n"
        "```\n\n"
        "Back to prose."
    )
    report = analyse_citations(text, [])
    # No findings because the only claim sits inside a fenced code block.
    assert all("99%" not in m.claim and "Studies show" not in m.claim for m in report.missing)


def test_protected_span_skip_inside_references_section():
    text = (
        "Body without citations.\n\n"
        "## References\n\n"
        "- Smith, J. (2020). On things. *J. Things*, 1(1), 1-2.\n"
    )
    report = analyse_citations(text, [])
    # The "Smith, 2020" inside the References section should not be reported
    # as an orphan citation.
    assert report.orphans == []


# ---------------------------------------------------------------------------
# References-section parsing (via parse_apa_block)
# ---------------------------------------------------------------------------


def test_references_section_orphan_when_not_in_store():
    text = "We follow (Doe, 2019) carefully here."
    refs = [_ref("smith_2020", "Smith", 2020)]  # Doe missing
    report = analyse_citations(text, refs)
    assert any("Doe" in o.key for o in report.orphans)
    assert any(r.id == "smith_2020" for r in report.unused)


def test_et_al_form_recognised():
    text = "Recent work (Smith et al., 2020) shows the trend."
    refs = [_ref("smith_2020", "Smith", 2020)]
    report = analyse_citations(text, refs)
    assert report.orphans == []
