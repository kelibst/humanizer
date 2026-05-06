"""DOI validation and CrossRef lookup for humanizer v1.5.

CONTRACT v1.5 §1, §3.1.

Public API:
    validate_doi(doi)              -> bool
    lookup_doi(doi)                -> dict   (CrossRef response normalised)
    doi_to_reference(doi)          -> Reference
    DoiNotFound                    (exception)
    DoiLookupError                 (exception)
"""
from __future__ import annotations

import re
from typing import Any

import httpx

from .refs_store import Reference

# CrossRef polite-pool user-agent (CONTRACT v1.5 §1)
_UA = "humanizer/1.5 (mailto:user@humanizer.local)"
_TIMEOUT = 10.0  # seconds

# Minimal DOI regex: 10.nnnn/anything
_DOI_RE = re.compile(r"^10\.\d{4,}/\S+$")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DoiNotFound(Exception):
    """The DOI was not found in CrossRef (HTTP 404 or empty response)."""


class DoiLookupError(Exception):
    """CrossRef was unreachable or returned an unexpected error."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def validate_doi(doi: str) -> bool:
    """Return True if *doi* has a plausible DOI syntax (10.nnnn/…)."""
    return bool(_DOI_RE.match((doi or "").strip()))


def _format_author(author: dict[str, Any]) -> str:
    """Format a CrossRef author dict to APA 'Last, F.' form."""
    family = (author.get("family") or "").strip()
    given = (author.get("given") or "").strip()
    if not family:
        # Institutional / literal
        return (author.get("name") or "Unknown").strip()
    if given:
        initials = ".".join(p[0] for p in given.split() if p) + "."
        return f"{family}, {initials}"
    return family


def _extract_year(message: dict[str, Any]) -> int | None:
    """Pull the publication year from a CrossRef message dict."""
    # Prefer published.date-parts[0][0]
    for key in ("published", "published-print", "published-online", "issued"):
        dp = (message.get(key) or {}).get("date-parts")
        if isinstance(dp, list) and dp and isinstance(dp[0], list) and dp[0]:
            try:
                return int(dp[0][0])
            except (TypeError, ValueError):
                continue
    # Fallback: created or deposited
    for key in ("created", "deposited"):
        dp = (message.get(key) or {}).get("date-parts")
        if isinstance(dp, list) and dp and isinstance(dp[0], list) and dp[0]:
            try:
                return int(dp[0][0])
            except (TypeError, ValueError):
                continue
    return None


def _extract_venue(message: dict[str, Any]) -> str | None:
    """Return the best venue string from a CrossRef message."""
    for key in ("container-title", "publisher"):
        val = message.get(key)
        if isinstance(val, list) and val:
            return str(val[0]).strip() or None
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


_TYPE_MAP: dict[str, str] = {
    "journal-article": "journal",
    "article": "journal",
    "book": "book",
    "book-chapter": "chapter",
    "book-section": "chapter",
    "proceedings-article": "journal",
    "conference-paper": "journal",
    "dataset": "web",
    "report": "web",
    "dissertation": "web",
    "posted-content": "web",
    "monograph": "book",
    "reference-entry": "web",
}


def _crossref_type(message: dict[str, Any]) -> str:
    raw = (message.get("type") or "").lower()
    return _TYPE_MAP.get(raw, "web")


def _build_raw_apa(authors: list[str], year: int | None, title: str, venue: str | None, doi: str) -> str:
    """Synthesise a minimal APA-7 citation string."""
    if len(authors) > 2:
        author_str = f"{authors[0]}, & {authors[1]}, et al."
    elif len(authors) == 2:
        author_str = f"{authors[0]}, & {authors[1]}"
    elif authors:
        author_str = authors[0]
    else:
        author_str = "Unknown"
    year_str = str(year) if year else "n.d."
    line = f"{author_str} ({year_str}). {title}."
    if venue:
        line += f" {venue}."
    line += f" https://doi.org/{doi}"
    return line


# ---------------------------------------------------------------------------
# Core lookup
# ---------------------------------------------------------------------------


def lookup_doi(doi: str) -> dict[str, Any]:
    """Query CrossRef for *doi* and return a normalised dict.

    Returns a dict matching the CONTRACT §3.1 response shape::

        {
            "authors": ["Smith, J.", "Doe, A."],
            "year": 2020,
            "title": "...",
            "venue": "Journal of X",
            "doi": "10.xxxxx/...",
            "type": "journal",
            "raw_apa": "..."
        }

    Raises:
        DoiNotFound   — HTTP 404 or empty result set.
        DoiLookupError — network error, non-200/404 status, malformed JSON.
    """
    doi = (doi or "").strip()
    url = f"https://api.crossref.org/works/{doi}"
    try:
        resp = httpx.get(url, headers={"User-Agent": _UA}, timeout=_TIMEOUT, follow_redirects=True)
    except httpx.TimeoutException as exc:
        raise DoiLookupError(f"CrossRef request timed out: {exc}") from exc
    except httpx.RequestError as exc:
        raise DoiLookupError(f"CrossRef unreachable: {exc}") from exc

    if resp.status_code == 404:
        raise DoiNotFound(f"DOI {doi!r} not found in CrossRef")
    if resp.status_code != 200:
        raise DoiLookupError(f"CrossRef returned HTTP {resp.status_code}")

    try:
        data = resp.json()
    except Exception as exc:
        raise DoiLookupError(f"CrossRef returned non-JSON response: {exc}") from exc

    message = data.get("message") or {}
    if not message:
        raise DoiNotFound(f"DOI {doi!r} not found (empty CrossRef message)")

    # Authors
    raw_authors = message.get("author") or []
    authors = [_format_author(a) for a in raw_authors]
    if not authors:
        authors = ["Unknown"]

    year = _extract_year(message)
    titles = message.get("title") or []
    title = str(titles[0]).strip() if titles else "[TITLE UNKNOWN]"
    venue = _extract_venue(message)
    ref_type = _crossref_type(message)
    raw_apa = _build_raw_apa(authors, year, title, venue, doi)

    return {
        "authors": authors,
        "year": year,
        "title": title,
        "venue": venue,
        "doi": doi,
        "type": ref_type,
        "raw_apa": raw_apa,
    }


def doi_to_reference(doi: str) -> Reference:
    """Look up *doi* and return a :class:`~refs_store.Reference`.

    The returned Reference has a derived id; callers can call ``derive_id``
    again after upsert to assign a collision-free id.

    Raises :class:`DoiNotFound` or :class:`DoiLookupError` on failure.
    """
    from .refs_store import derive_id as _derive_id

    data = lookup_doi(doi)
    year = data["year"] if data["year"] is not None else 2000
    # Build a temporary id to satisfy the Pydantic min_length constraint.
    tmp = Reference(
        id="tmp",
        authors=data["authors"],
        year=year,
        title=data["title"],
        venue=data["venue"],
        doi=data["doi"],
        url=f"https://doi.org/{doi}",
        type=data["type"],  # type: ignore[arg-type]
        raw_apa=data["raw_apa"],
    )
    real_id = _derive_id(tmp.model_copy(update={"id": "tmp"}), existing=[])
    return tmp.model_copy(update={"id": real_id})


__all__ = [
    "DoiLookupError",
    "DoiNotFound",
    "doi_to_reference",
    "lookup_doi",
    "validate_doi",
]
