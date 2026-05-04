"""Protected-spans builder.

A *protected span* is a (start, end) half-open character range in the input
text that no deterministic transform may modify. The runner rebuilds spans
after every transform that changes the string length, so transforms can
treat the list as authoritative for the text they currently see.

Sources of protection (per CONTRACTS § 4):
    - markdown fenced code blocks: ``` ... ``` (any number of backticks >= 3)
    - markdown inline code: `...`
    - paired ASCII double quotes: "..."
    - paired ASCII single quotes: '...'  (only when clearly a quotation, i.e.
      not an apostrophe inside a word; we accept the trade-off of a slightly
      eager match)
    - curly double quotes: U+201C ... U+201D
    - curly single quotes: U+2018 ... U+2019
    - APA-style citation parentheticals: (Author, 2024), (Author et al., 2024),
      (Author & Other, 2024)
    - markdown table rows: any line beginning (after leading whitespace) with `|`
    - block quotes: any line beginning (after leading whitespace) with `>`
    - inline LaTeX-ish math: $...$ on a single line
    - the entire region from a "References" or "Bibliography" heading until
      the next markdown heading (or end of file). A heading is detected as
      either an ATX heading (`#`+) or a line whose entire text is exactly the
      keyword.

Spans are sorted by start and merged where they overlap or touch.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Span helpers
# ---------------------------------------------------------------------------

Span = tuple[int, int]


def _merge(spans: list[Span]) -> list[Span]:
    """Sort by start and merge overlapping/adjacent spans."""
    if not spans:
        return []
    spans = sorted(spans)
    merged: list[Span] = [spans[0]]
    for s, e in spans[1:]:
        ps, pe = merged[-1]
        if s <= pe:  # overlap or touch
            if e > pe:
                merged[-1] = (ps, e)
        else:
            merged.append((s, e))
    return merged


def is_protected(pos: int, spans: list[Span]) -> bool:
    """True if `pos` falls inside any of the protected spans."""
    # Linear scan; spans are short. Could binary-search later if it matters.
    for s, e in spans:
        if s <= pos < e:
            return True
        if s > pos:
            break
    return False


def overlaps_protected(start: int, end: int, spans: list[Span]) -> bool:
    """True if [start, end) overlaps any protected span."""
    for s, e in spans:
        if s >= end:
            break
        if e > start:
            return True
    return False


# ---------------------------------------------------------------------------
# Individual collectors
# ---------------------------------------------------------------------------

# Fenced code: opening fence of >=3 backticks at line start; matching closing
# fence of the same length on its own line. We approximate: greedy minimal
# match between two ``` runs.
_FENCED = re.compile(r"(?ms)^(?P<fence>`{3,})[^\n]*\n.*?^(?P=fence)\s*$")

# Inline code: backtick-delimited, single line. Forbid the double-backtick
# form colliding with fence by requiring a line-internal match.
_INLINE_CODE = re.compile(r"`[^`\n]+`")

# ASCII double-quoted strings (non-greedy, single line).
_ASCII_DQUOTE = re.compile(r'"[^"\n]{1,400}"')

# Curly double quotes.
_CURLY_DQUOTE = re.compile(r"“[^”\n]{1,400}”")

# Curly single quotes.
_CURLY_SQUOTE = re.compile(r"‘[^’\n]{1,400}’")

# Citation parentheticals: (Author, 2024) | (Author et al., 2024) |
# (Author & Other, 2024) | (Author and Other, 2024). Year required.
_CITATION = re.compile(
    r"\("
    r"[A-Z][A-Za-z'\-]+"                      # first author surname
    r"(?:\s+(?:et\s+al\.|and\s+[A-Z][A-Za-z'\-]+|&\s+[A-Z][A-Za-z'\-]+))?"
    r",\s*"
    r"(?:n\.d\.|\d{4}[a-z]?)"                 # year or n.d.
    r"(?:,\s*p{1,2}\.\s*\d+(?:[–\-]\d+)?)?"  # optional page
    r"\)"
)

# Inline math: $...$ on a single line; non-greedy. Avoid $$...$$ (block math)
# by forbidding $ next to opening/closing $.
_INLINE_MATH = re.compile(r"(?<!\$)\$[^$\n]{1,200}\$(?!\$)")

# Markdown table row: line that, after optional leading whitespace, starts
# with `|`.  We capture the whole line.
_TABLE_ROW = re.compile(r"(?m)^[ \t]*\|.*$")

# Markdown block quote: line beginning with `>`.
_BLOCKQUOTE = re.compile(r"(?m)^[ \t]*>.*$")

# References / Bibliography heading: ATX (# / ## etc.) or bare line equal to
# one of the keywords (case-insensitive, optional trailing punctuation).
_REFERENCES_HEADING = re.compile(
    r"(?im)^[ \t]*(?:#{1,6}[ \t]+)?(?:references|bibliography|works\s+cited)\s*:?\s*$"
)
# Any subsequent ATX heading that ends the references region.
_NEXT_HEADING = re.compile(r"(?m)^[ \t]*#{1,6}[ \t]+\S")


def _ascii_squote_spans(text: str) -> list[Span]:
    """Paired ASCII single quotes for short quotations.

    Heuristic: an apostrophe inside a word (e.g. don't, '90s) is NOT a quote.
    We only protect a `'...'` pair when both delimiters sit at word
    boundaries: opening `'` is preceded by start-of-string, whitespace, or
    `(`; closing `'` is followed by end-of-string, whitespace, or punctuation
    other than a letter. Skip if the contents look like a possessive or
    contraction (no inner space => probably not a quotation).
    """
    spans: list[Span] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if ch == "'":
            prev = text[i - 1] if i > 0 else " "
            if prev.isalnum():
                i += 1
                continue
            # Find a closing '.
            j = text.find("'", i + 1)
            if j == -1:
                break
            inner = text[i + 1:j]
            nxt = text[j + 1] if j + 1 < n else " "
            if (
                "\n" not in inner
                and " " in inner          # multi-word quotation
                and len(inner) <= 200
                and not nxt.isalnum()
            ):
                spans.append((i, j + 1))
                i = j + 1
                continue
        i += 1
    return spans


def _references_spans(text: str) -> list[Span]:
    """Span from a References/Bibliography heading to the next heading or EOF."""
    spans: list[Span] = []
    for m in _REFERENCES_HEADING.finditer(text):
        start = m.start()
        # Find next ATX heading after this one (strictly after the matched
        # heading line itself).
        search_from = m.end()
        next_h = _NEXT_HEADING.search(text, search_from)
        end = next_h.start() if next_h else len(text)
        spans.append((start, end))
    return spans


def _findall_spans(pattern: re.Pattern[str], text: str) -> list[Span]:
    return [(m.start(), m.end()) for m in pattern.finditer(text)]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_protected_spans(text: str) -> list[Span]:
    """Compute the merged, sorted list of protected spans for `text`."""
    if not text:
        return []
    spans: list[Span] = []
    # Order matters only for collection completeness; merge handles overlap.
    spans.extend(_findall_spans(_FENCED, text))
    spans.extend(_findall_spans(_INLINE_CODE, text))
    spans.extend(_findall_spans(_ASCII_DQUOTE, text))
    spans.extend(_findall_spans(_CURLY_DQUOTE, text))
    spans.extend(_findall_spans(_CURLY_SQUOTE, text))
    spans.extend(_findall_spans(_CITATION, text))
    spans.extend(_findall_spans(_INLINE_MATH, text))
    spans.extend(_findall_spans(_TABLE_ROW, text))
    spans.extend(_findall_spans(_BLOCKQUOTE, text))
    spans.extend(_ascii_squote_spans(text))
    spans.extend(_references_spans(text))
    return _merge(spans)


__all__ = [
    "Span",
    "build_protected_spans",
    "is_protected",
    "overlaps_protected",
]
