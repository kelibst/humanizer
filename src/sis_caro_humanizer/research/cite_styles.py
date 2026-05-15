"""Citation style formatters — MLA 9 and Chicago 17 (Author-Date).

These formatters convert a ``Reference`` record (which stores an APA-7
``raw_apa`` string internally) to the requested style.  Output is a plain
string; callers embed it in a markdown bullet.

Design decision: rather than parsing ``raw_apa`` (fragile), we build the
output directly from the structured fields (authors, year, title, venue,
doi, url, type) and fall back to ``raw_apa`` only when a structured field
is absent.

Supported styles
----------------
* ``apa``     — APA 7th edition (identity transform: returns ``raw_apa``).
* ``mla``     — MLA 9th edition.
* ``chicago`` — Chicago 17 Author-Date.

Usage
-----
::

    from sis_caro_humanizer.research.cite_styles import format_reference
    formatted = format_reference(ref, style="mla")
"""
from __future__ import annotations

import re
from typing import Literal

from .refs_store import Reference

CiteStyle = Literal["apa", "mla", "chicago"]
SUPPORTED_STYLES: tuple[CiteStyle, ...] = ("apa", "mla", "chicago")


# ---------------------------------------------------------------------------
# Author name helpers
# ---------------------------------------------------------------------------

def _last_first(author: str) -> str:
    """Normalise ``"Smith, J."`` / ``"John Smith"`` → ``"Smith, J."``."""
    author = author.strip().rstrip(",.")
    if "," in author:
        return author  # already "Last, First"
    parts = author.split()
    if len(parts) == 1:
        return author
    last = parts[-1]
    first = " ".join(parts[:-1])
    return f"{last}, {first}"


def _first_last(author: str) -> str:
    """Normalise any form → ``"J. Smith"``."""
    author = author.strip().rstrip(",.")
    if "," in author:
        parts = author.split(",", 1)
        last = parts[0].strip()
        first = parts[1].strip() if len(parts) > 1 else ""
        return f"{first} {last}".strip()
    return author


def _mla_authors(authors: list[str]) -> str:
    """MLA author string: First author inverted; subsequent normal."""
    if not authors:
        return ""
    if len(authors) == 1:
        return _last_first(authors[0]) + "."
    if len(authors) > 2:
        return _last_first(authors[0]) + ", et al."
    return _last_first(authors[0]) + ", and " + _first_last(authors[1]) + "."


def _chicago_authors(authors: list[str]) -> str:
    """Chicago Author-Date: First author inverted; rest normal; Oxford comma."""
    if not authors:
        return ""
    if len(authors) == 1:
        return _last_first(authors[0])
    if len(authors) > 3:
        return _last_first(authors[0]) + " et al."
    parts = [_last_first(authors[0])] + [_first_last(a) for a in authors[1:]]
    if len(parts) == 2:
        return parts[0] + " and " + parts[1]
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


# ---------------------------------------------------------------------------
# Style formatters
# ---------------------------------------------------------------------------

def _doi_url(ref: Reference) -> str:
    if ref.doi:
        return f"https://doi.org/{ref.doi}"
    return ref.url or ""


def _fmt_mla(ref: Reference) -> str:
    """MLA 9 format.

    Journal : Author(s). "Title." *Venue*, vol. —, no. —, Year, pp. —.
    Book    : Author(s). *Title*. Publisher, Year.
    Chapter : Author(s). "Chapter Title." *Book Title*, edited by —, Publisher, Year.
    Web     : Author(s). "Title." *Site Name*, Year, URL.
    """
    authors = _mla_authors(ref.authors)
    title = ref.title.rstrip(".")
    venue = (ref.venue or "").strip()
    year = str(ref.year)
    link = _doi_url(ref)

    if ref.type == "journal":
        s = f'{authors} "{title}." *{venue}*, {year}.'
    elif ref.type == "book":
        s = f'{authors} *{title}*. {venue + ", " if venue else ""}{year}.'
    elif ref.type == "chapter":
        s = f'{authors} "{title}." *{venue}*, {year}.'
    else:  # web
        s = f'{authors} "{title}." *{venue or ""}*, {year}.'

    if link:
        s = s.rstrip(".") + f". {link}."
    return s.strip()


def _fmt_chicago(ref: Reference) -> str:
    """Chicago 17 Author-Date format.

    Journal : Last, First, and First Last. Year. "Title." *Venue* vol (issue): pp.
    Book    : Last, First. Year. *Title*. City: Publisher.
    Chapter : Last, First. Year. "Chapter Title." In *Book*, edited by —, pp. City: Publisher.
    Web     : Last, First. Year. "Title." *Site*. Accessed Month DD, YYYY. URL.
    """
    authors = _chicago_authors(ref.authors)
    title = ref.title.rstrip(".")
    venue = (ref.venue or "").strip()
    year = str(ref.year)
    link = _doi_url(ref)

    if ref.type == "journal":
        s = f'{authors}. {year}. "{title}." *{venue}*.'
    elif ref.type == "book":
        s = f'{authors}. {year}. *{title}*. {venue + "." if venue else ""}'
    elif ref.type == "chapter":
        s = f'{authors}. {year}. "{title}." In *{venue}*.'
    else:  # web
        s = f'{authors}. {year}. "{title}." *{venue or ""}*.'

    if link:
        s = s.rstrip(".") + f" {link}."
    return s.strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def format_reference(ref: Reference, *, style: CiteStyle = "apa") -> str:
    """Format ``ref`` in the requested citation style.

    Falls back to ``ref.raw_apa`` for ``"apa"`` (the canonical stored form).

    Parameters
    ----------
    ref:
        The reference record to format.
    style:
        One of ``"apa"``, ``"mla"``, or ``"chicago"``.

    Returns
    -------
    A plain text citation string suitable for embedding in a markdown bullet.

    Raises
    ------
    ValueError
        When ``style`` is not one of the supported styles.
    """
    if style not in SUPPORTED_STYLES:
        raise ValueError(
            f"Unsupported citation style {style!r}. "
            f"Choose one of: {', '.join(SUPPORTED_STYLES)}"
        )
    if style == "apa":
        return ref.raw_apa.strip()
    if style == "mla":
        return _fmt_mla(ref)
    if style == "chicago":
        return _fmt_chicago(ref)
    raise AssertionError("unreachable")  # pragma: no cover


def regenerate_block(
    refs: list[Reference],
    *,
    style: CiteStyle = "apa",
) -> str:
    """Render ``refs`` as a markdown bullet list in the requested style.

    Sorted alphabetically by first-author last name, then year.
    Returns the raw bullet text (no ``## References`` heading).
    """
    def _sort_key(r: Reference) -> tuple[str, int]:
        last = r.authors[0].split(",")[0].strip().lower() if r.authors else ""
        return (last, r.year)

    sorted_refs = sorted(refs, key=_sort_key)
    lines = []
    for r in sorted_refs:
        lines.append(f"- {format_reference(r, style=style)}")
    return "\n".join(lines)


__all__ = [
    "CiteStyle",
    "SUPPORTED_STYLES",
    "format_reference",
    "regenerate_block",
]
