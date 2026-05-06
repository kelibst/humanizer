"""ID derivation helpers for Reference records (CONTRACT §1.6).

Extracted from ``refs_store.py`` (Wave 4 refactor). The public surface is
``derive_id``; ``_last_name_from_author`` and ``_suffix_chars`` are internal
helpers also re-exported from ``refs_store`` for backward compatibility.
"""
from __future__ import annotations

import re
import string
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from .refs_store import Reference

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

_AUTHOR_LASTNAME_RE = re.compile(r"^([\w\-']+)")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _last_name_from_author(author: str) -> str:
    """Extract a last name from an author string.

    Accepts ``"Smith, J."`` (APA last-first), ``"J. Smith"``, or plain
    ``"Smith"``. Falls back to the leading alphanumeric token.
    """
    a = (author or "").strip()
    if not a:
        return "anon"
    if "," in a:
        # APA last-first
        last = a.split(",", 1)[0].strip()
    else:
        # "J. Smith" / "John Smith" / "Smith"
        parts = a.split()
        last = parts[-1] if parts else a
    m = _AUTHOR_LASTNAME_RE.match(last)
    if not m:
        return re.sub(r"\W+", "", last).lower() or "anon"
    return m.group(1).lower().replace("'", "")


def _suffix_chars() -> Iterable[str]:
    """Yield "", "a", "b", "c", ..., "z", "aa", "ab", ..."""
    yield ""
    letters = string.ascii_lowercase
    for c in letters:
        yield c
    for c1 in letters:
        for c2 in letters:
            yield c1 + c2


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def derive_id(ref: "Reference", existing: "Iterable[Reference] | None" = None) -> str:
    """Derive ``lastauthor_year[a|b|c…]`` ensuring no collision with ``existing``.

    Uses the first author. ``existing`` is filtered to skip a record that
    matches the input on ``authors``+``year``+``title`` (so calling
    ``derive_id`` for an in-place upsert keeps the same id).
    """
    last = _last_name_from_author(ref.authors[0]) if ref.authors else "anon"
    base = f"{last}_{ref.year}"
    existing = list(existing or [])
    same_as_input: set[str] = set()
    for r in existing:
        if r.year == ref.year and r.title == ref.title and r.authors == ref.authors:
            same_as_input.add(r.id)
    taken = {r.id for r in existing} - same_as_input
    for suffix in _suffix_chars():
        candidate = base + suffix
        if candidate not in taken:
            return candidate
    # Astronomically unlikely; fall back to a numeric suffix.
    i = 1
    while True:
        candidate = f"{base}_{i}"
        if candidate not in taken:
            return candidate
        i += 1


__all__ = ["derive_id", "_last_name_from_author", "_suffix_chars"]
