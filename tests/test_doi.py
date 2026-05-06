"""Tests for research.doi (CONTRACT v1.5 §1, §3.1).

All HTTP calls are mocked via unittest.mock.patch so no network access is needed.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from sis_caro_humanizer.research.doi import (
    DoiLookupError,
    DoiNotFound,
    lookup_doi,
    validate_doi,
    doi_to_reference,
    _format_author,
)


# ---------------------------------------------------------------------------
# validate_doi
# ---------------------------------------------------------------------------


def test_validate_doi_valid():
    assert validate_doi("10.1000/xyz123") is True


def test_validate_doi_no_prefix():
    assert validate_doi("1.1000/xyz") is False


def test_validate_doi_empty():
    assert validate_doi("") is False


# ---------------------------------------------------------------------------
# _format_author
# ---------------------------------------------------------------------------


def test_format_author_family_given():
    assert _format_author({"family": "Smith", "given": "John"}) == "Smith, J."


def test_format_author_family_only():
    assert _format_author({"family": "Smith"}) == "Smith"


def test_format_author_institutional():
    assert _format_author({"name": "World Health Organization"}) == "World Health Organization"


# ---------------------------------------------------------------------------
# lookup_doi — happy path
# ---------------------------------------------------------------------------


def _make_resp(status: int, body: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = body
    return resp


def test_lookup_doi_happy_path():
    body = {
        "message": {
            "type": "journal-article",
            "author": [{"family": "Smith", "given": "John"}, {"family": "Doe", "given": "Alice"}],
            "title": ["A Test Article"],
            "container-title": ["Journal of Tests"],
            "published": {"date-parts": [[2020, 1, 15]]},
            "DOI": "10.1000/xyz",
        }
    }
    with patch("httpx.get", return_value=_make_resp(200, body)):
        result = lookup_doi("10.1000/xyz")

    assert result["authors"] == ["Smith, J.", "Doe, A."]
    assert result["year"] == 2020
    assert result["title"] == "A Test Article"
    assert result["venue"] == "Journal of Tests"
    assert result["type"] == "journal"
    assert result["doi"] == "10.1000/xyz"
    assert "Smith" in result["raw_apa"]


# ---------------------------------------------------------------------------
# lookup_doi — error cases
# ---------------------------------------------------------------------------


def test_lookup_doi_404_raises_not_found():
    with patch("httpx.get", return_value=_make_resp(404, {})):
        with pytest.raises(DoiNotFound):
            lookup_doi("10.9999/missing")


def test_lookup_doi_500_raises_lookup_error():
    with patch("httpx.get", return_value=_make_resp(500, {})):
        with pytest.raises(DoiLookupError):
            lookup_doi("10.1000/xyz")


def test_lookup_doi_network_error():
    import httpx as _httpx

    with patch("httpx.get", side_effect=_httpx.RequestError("connection refused")):
        with pytest.raises(DoiLookupError, match="unreachable"):
            lookup_doi("10.1000/xyz")


def test_lookup_doi_timeout():
    import httpx as _httpx

    with patch("httpx.get", side_effect=_httpx.TimeoutException("timed out")):
        with pytest.raises(DoiLookupError, match="timed out"):
            lookup_doi("10.1000/xyz")


# ---------------------------------------------------------------------------
# doi_to_reference
# ---------------------------------------------------------------------------


def test_doi_to_reference_returns_reference():
    body = {
        "message": {
            "type": "journal-article",
            "author": [{"family": "Jones", "given": "B."}],
            "title": ["Some Study"],
            "container-title": ["BMJ"],
            "published": {"date-parts": [[2021]]},
            "DOI": "10.1234/test",
        }
    }
    with patch("httpx.get", return_value=_make_resp(200, body)):
        from sis_caro_humanizer.research.refs_store import Reference
        ref = doi_to_reference("10.1234/test")

    assert isinstance(ref, Reference)
    assert ref.year == 2021
    assert ref.authors == ["Jones, B."]
    assert ref.doi == "10.1234/test"
