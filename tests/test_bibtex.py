"""Tests for research.bibtex (CONTRACT v1.5 §1, §10).

Parser is regex-based only. Tests include round-trip and LaTeX escaping.
"""
from __future__ import annotations

import pytest

from sis_caro_humanizer.research.bibtex import (
    parse_bibtex,
    reference_to_bibtex,
    references_to_bibtex,
    _latex_escape,
    _bibtex_author_to_apa,
)
from sis_caro_humanizer.research.refs_store import Reference


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _ref(**kwargs) -> Reference:
    defaults = {
        "id": "test_2020",
        "authors": ["Smith, J."],
        "year": 2020,
        "title": "A Title",
        "type": "journal",
        "raw_apa": "Smith, J. (2020). A Title.",
    }
    defaults.update(kwargs)
    return Reference(**defaults)


# ---------------------------------------------------------------------------
# parse_bibtex
# ---------------------------------------------------------------------------


def test_parse_article_basic():
    text = """@article{smith20,
  author = {Smith, John and Doe, Alice},
  title = {A Test Paper},
  journal = {Journal of Tests},
  year = {2020},
}"""
    refs = parse_bibtex(text)
    assert len(refs) == 1
    r = refs[0]
    assert r.authors == ["Smith, J.", "Doe, A."]
    assert r.year == 2020
    assert r.title == "A Test Paper"
    assert r.venue == "Journal of Tests"
    assert r.type == "journal"


def test_parse_book_type():
    text = """@book{jones2019,
  author = {Jones, Bob},
  title = {The Big Book},
  publisher = {Academic Press},
  year = {2019},
}"""
    refs = parse_bibtex(text)
    assert refs[0].type == "book"
    assert refs[0].venue == "Academic Press"


def test_parse_incollection_is_chapter():
    text = """@incollection{lee2018,
  author = {Lee, Carol},
  title = {A Chapter},
  booktitle = {Some Edited Volume},
  year = {2018},
}"""
    refs = parse_bibtex(text)
    assert refs[0].type == "chapter"
    assert refs[0].venue == "Some Edited Volume"


def test_parse_multiple_entries():
    text = """@article{a2020,
  author = {Alpha, A.},
  title = {First},
  journal = {J1},
  year = {2020},
}

@article{b2021,
  author = {Beta, B.},
  title = {Second},
  journal = {J2},
  year = {2021},
}"""
    refs = parse_bibtex(text)
    assert len(refs) == 2


def test_parse_skips_missing_author():
    text = """@article{noauthor,
  title = {No Author Here},
  journal = {J},
  year = {2020},
}"""
    refs = parse_bibtex(text)
    assert len(refs) == 0


def test_parse_skips_missing_year():
    text = """@article{noyear,
  author = {Noyear, N.},
  title = {No Year},
  journal = {J},
}"""
    refs = parse_bibtex(text)
    assert len(refs) == 0


# ---------------------------------------------------------------------------
# reference_to_bibtex — round-trip
# ---------------------------------------------------------------------------


def test_round_trip_article():
    ref = _ref(
        id="smith_2020",
        authors=["Smith, J.", "Doe, A."],
        year=2020,
        title="A Paper",
        venue="BMJ",
        type="journal",
        raw_apa="Smith, J., & Doe, A. (2020). A Paper. BMJ.",
    )
    bib = reference_to_bibtex(ref)
    assert "@article{smith_2020," in bib
    assert "A Paper" in bib
    assert "2020" in bib
    # Round-trip: parse back
    refs2 = parse_bibtex(bib)
    assert len(refs2) == 1
    assert refs2[0].title == "A Paper"
    assert refs2[0].year == 2020


# ---------------------------------------------------------------------------
# LaTeX escaping
# ---------------------------------------------------------------------------


def test_latex_escape_ampersand():
    result = _latex_escape("Smith & Doe")
    assert "\\&" in result


def test_latex_escape_already_escaped_is_unchanged():
    s = "Smith \\& Doe"
    assert _latex_escape(s) == s  # already has backslash — skipped


# ---------------------------------------------------------------------------
# references_to_bibtex (bulk)
# ---------------------------------------------------------------------------


def test_references_to_bibtex_sorted():
    refs = [
        _ref(id="z_2020", authors=["Zeta, Z."], title="Last"),
        _ref(id="a_2020", authors=["Alpha, A."], title="First"),
    ]
    bulk = references_to_bibtex(refs)
    # "a_2020" should come before "z_2020"
    assert bulk.index("a_2020") < bulk.index("z_2020")
