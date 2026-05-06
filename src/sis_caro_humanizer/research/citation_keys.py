"""Orphan in-text citation key parser (CONTRACT v1.5 §1).

Extracted from ``refs_store.py`` (Wave 4 refactor). The public surface is
``parse_orphan_key``.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

_ORPHAN_RE = re.compile(
    r"""
    ^\(                             # opening paren
    (?P<names>                      # one or more author name chunks
        [A-Z][A-Za-z'\-]+          # first last-name (capital start)
        (?:                         # optional additional names
            (?:\s*&\s*|\s+and\s+)  # separator: & or and
            [A-Z][A-Za-z'\-]+      # next last-name
        )*
        (?:\s+et\s+al\.?)?         # optional "et al."
    )
    ,\s*
    (?P<year>\d{4})                 # 4-digit year
    (?:,\s*[^)]+)?                  # optional page/paragraph suffix: ", p. 42"
    \)$                             # closing paren
    """,
    re.VERBOSE | re.IGNORECASE,
)

_NAME_SPLIT_RE = re.compile(r"\s*(?:&|and)\s*", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def parse_orphan_key(key: str) -> tuple[list[str], int]:
    """Parse an in-text citation key such as "(Smith et al., 2020)".

    Accepted forms:
    - "(Smith, 2020)"
    - "(Smith & Doe, 2020)"
    - "(Smith and Doe, 2020)"
    - "(Smith et al., 2020)"
    - "(Smith, 2020, p. 42)"    page/paragraph suffix is stripped

    Returns:
        (last_names, year) — last_names is a list of last-name strings,
        year is the 4-digit integer.

    Raises:
        ValueError — if *key* does not match the expected pattern.
    """
    key = (key or "").strip()
    m = _ORPHAN_RE.match(key)
    if not m:
        raise ValueError(f"Cannot parse orphan citation key: {key!r}")

    year = int(m.group("year"))
    names_raw = m.group("names").strip()

    # Strip trailing "et al." variant
    names_raw = re.sub(r"\s+et\s+al\.?$", "", names_raw, flags=re.IGNORECASE).strip()

    # Split on & / and
    parts = _NAME_SPLIT_RE.split(names_raw)
    last_names = [p.strip() for p in parts if p.strip()]
    if not last_names:
        raise ValueError(f"No author names found in: {key!r}")

    return last_names, year


__all__ = ["parse_orphan_key"]
