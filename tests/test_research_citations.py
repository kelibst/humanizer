"""Tests for research.citations (CONTRACT v1.3 §1.4)."""
from __future__ import annotations

from sis_caro_humanizer.research.citations import analyse_citations, flat_to_paragraph_offset
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


# ---------------------------------------------------------------------------
# flat_to_paragraph_offset (B2 utility)
# ---------------------------------------------------------------------------


def test_flat_to_paragraph_offset_basic():
    """Given a known list of paragraphs, character offsets should map
    correctly to (paragraph_idx, char_in_paragraph).

    Flat text layout for ["Hello world", "Second para", "Third"]:
      "Hello world\\n\\nSecond para\\n\\nThird"
       ^0         ^10 ^11^12^13      ^24^25^26
    Offsets 11-12 are the \\n\\n separator between para 0 and para 1.
    Offsets 24-25 are the \\n\\n separator between para 1 and para 2.
    """
    paragraphs = ["Hello world", "Second para", "Third"]
    #              0..10          13..23          26..30

    # Start of first paragraph.
    assert flat_to_paragraph_offset(paragraphs, 0) == (0, 0)
    # Last char of first paragraph ("d" in "world"), offset 10.
    assert flat_to_paragraph_offset(paragraphs, 10) == (0, 10)
    # Start of second paragraph: offset 13 (11 + 2 sep = 13).
    assert flat_to_paragraph_offset(paragraphs, 13) == (1, 0)
    # Within second paragraph: offset 18 → char 5 of "Second para".
    assert flat_to_paragraph_offset(paragraphs, 18) == (1, 5)
    # Start of third paragraph.
    third_start = len("Hello world") + 2 + len("Second para") + 2  # = 26
    assert flat_to_paragraph_offset(paragraphs, third_start) == (2, 0)
    # Last char of third paragraph ("d" in "Third"), offset 30.
    assert flat_to_paragraph_offset(paragraphs, third_start + 4) == (2, 4)


def test_flat_to_paragraph_offset_out_of_range():
    """Offsets outside the flat text should return (-1, -1)."""
    paragraphs = ["Short"]
    # "Short" is 5 chars, flat length is 5.
    assert flat_to_paragraph_offset(paragraphs, -1) == (-1, -1)
    assert flat_to_paragraph_offset(paragraphs, 100) == (-1, -1)
    assert flat_to_paragraph_offset([], 0) == (-1, -1)
