"""Tests for research.checklist (CONTRACT v1.3 §1.2 / §3.3)."""
from __future__ import annotations

from sis_caro_humanizer.research.checklist import analyse_sections


# ---------------------------------------------------------------------------
# Sample fixtures
# ---------------------------------------------------------------------------


INTRO_FULL = """\
# Title

## Introduction

Despite three decades of research, the problem is poorly understood.
However, this remains unclear in many low-resource settings. There is
little research that addresses this gap. This study aims to examine
the issue. The remainder of this chapter is organised as follows.
"""

INTRO_GAP = """\
# Title

## Introduction

This chapter introduces the topic. We discuss several themes and look
at the existing landscape carefully and thoroughly. Many things are
relevant to consider here, including history and context.
"""

METHODS_DOC = """\
# Title

## Methods

This study used a cross-sectional design. The sample comprised 124 patients
recruited via purposive sampling. Data were collected via semi-structured
interviews. Thematic analysis was conducted. Ethical approval was granted
by the institutional review board.
"""

ALIAS_DOC = """\
# Title

## Background

Despite years of work, the problem remains unclear. There is little
research that addresses this. The aim of this paper is to examine X.
"""

NO_MATCH_DOC = """\
# Title

## Acknowledgements

We thank the team for their support during fieldwork.
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_introduction_all_components_present():
    out = analyse_sections(INTRO_FULL)
    intro = next(s for s in out if s.heading == "Introduction")
    assert intro.type == "introduction"
    names = {c.name: c.present for c in intro.components}
    assert names["hook"] is True
    assert names["problem_statement"] is True
    assert names["gap"] is True
    assert names["aim_objectives"] is True
    assert names["structure"] is True
    assert intro.score == "5/5"
    assert intro.word_count > 30


def test_introduction_with_gap_missing_components():
    out = analyse_sections(INTRO_GAP)
    intro = next(s for s in out if s.heading == "Introduction")
    assert intro.type == "introduction"
    names = {c.name: c.present for c in intro.components}
    # No aim or structure here.
    assert names["aim_objectives"] is False
    assert names["structure"] is False
    # The score should be < 5.
    present, total = intro.score.split("/")
    assert int(present) < int(total)


def test_methods_archetype_resolves():
    out = analyse_sections(METHODS_DOC)
    methods = next(s for s in out if s.heading == "Methods")
    assert methods.type == "methods"
    names = {c.name: c.present for c in methods.components}
    assert names["design"] is True
    assert names["sample"] is True
    assert names["data_collection"] is True
    assert names["analysis"] is True
    assert names["ethics"] is True


def test_alias_resolution_background_is_introduction():
    out = analyse_sections(ALIAS_DOC)
    bg = next(s for s in out if s.heading == "Background")
    assert bg.type == "introduction"


def test_regex_or_keyword_fallback():
    """``problem_statement`` triggers via the keyword 'problem' when no regex hits."""
    text = """\
# Title

## Introduction

The problem is at the heart of every developing-country health system. We
address this here.
"""
    out = analyse_sections(text)
    intro = next(s for s in out if s.heading == "Introduction")
    by_name = {c.name: c for c in intro.components}
    # 'problem' keyword OR the regex 'problem (is|of)'; both should fire.
    assert by_name["problem_statement"].present is True
    assert "problem" in by_name["problem_statement"].evidence.lower()


def test_no_match_returns_unknown_type():
    out = analyse_sections(NO_MATCH_DOC)
    ack = next(s for s in out if s.heading == "Acknowledgements")
    assert ack.type == "unknown"
    assert ack.components == []
    assert ack.score == "0/0"


def test_evidence_includes_line_number():
    out = analyse_sections(INTRO_FULL)
    intro = next(s for s in out if s.heading == "Introduction")
    hook = next(c for c in intro.components if c.name == "hook")
    assert hook.evidence.startswith("L")
    assert "Despite three decades" in hook.evidence


def test_multiple_sections_in_one_doc():
    text = INTRO_FULL + "\n" + METHODS_DOC.split("# Title\n", 1)[1]
    out = analyse_sections(text)
    headings = [s.heading for s in out]
    assert "Introduction" in headings
    assert "Methods" in headings
