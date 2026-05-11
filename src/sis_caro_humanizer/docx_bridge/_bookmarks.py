"""_bookmarks.py — APA regex constants and reference bookmark injection (Pass 2)."""
from __future__ import annotations

import re

from ._guard import _require_docx  # noqa: F401  (available for callers that need it)

# ---------------------------------------------------------------------------
# Shared regex constants (also imported by _hyperlinks.py)
# ---------------------------------------------------------------------------

# Regex: first line of a typical APA reference (starts with capital, contains
# a 4-digit year in parentheses somewhere on the line).
_APA_LINE_RE = re.compile(r"^[A-Z][\w\-'].*\(\d{4}\)")

# Regex: extract last name (first word) and year from an APA line.
_APA_KEY_RE = re.compile(r"^([A-Za-z][\w\-']+).*\((\d{4})\)")

# Regex: citation parenthetical in prose, e.g. "(Smith, 2020)" or
# "(Smith & Doe, 2020a)".
_CITE_PAREN_RE = re.compile(
    r"\("
    r"(?P<key>[A-Z][\w\-']+(?:\s+et\s+al\.)?(?:\s*(?:,\s+|\s+(?:and|&)\s+)[A-Z][\w\-']+)*)"
    r"\s*,\s*(?P<year>\d{4}[a-z]?)"
    r"(?:,\s*p{1,2}\.\s*\d+(?:[–\-]\d+)?)?"
    r"\)"
)


# ---------------------------------------------------------------------------
# Markup-stripping pre-processor
# ---------------------------------------------------------------------------

# refs_store generates references with HTML anchor IDs, e.g.:
#   <a id="ref-smith2020"></a>Smith, J. (2020). …
_HTML_ANCHOR_RE = re.compile(r'<a\s+id="[^"]*"\s*></a>\s*')

# refs_store formats in-text citations as markdown links, e.g.:
#   Single:  ([Smith, 2020](#ref-smith2020))
#   Multi:   ([Smith, 2020](#ref-smith2020). [Jones, 2019](#ref-jones2019))
# Match individual [text](#anchor) links anywhere so both forms are handled.
_MD_CITE_LINK_RE = re.compile(r'\[([^\]]+)\]\(#[^)]+\)')


def clean_citation_markup(text: str) -> str:
    """Strip HTML anchor tags and markdown citation links from *text*.

    Must be called on humanized_text before all DOCX export passes so that
    the APA and citation regexes only see plain text.

    - ``<a id="ref-..."></a>`` anchors → removed
    - ``[Name, Year](#ref-...)`` markdown links → ``Name, Year`` (link stripped,
      text kept; outer parentheses from the surrounding prose are preserved)
    """
    text = _HTML_ANCHOR_RE.sub("", text)
    text = _MD_CITE_LINK_RE.sub(r"\1", text)
    return text


def _make_bookmark_id(line: str, existing: dict[str, str]) -> str:
    """Derive a ``ref_lastname_year`` bookmark id from an APA reference line.

    Handles collisions by appending ``_a``, ``_b``, … suffixes.
    """
    m = _APA_KEY_RE.match(line.strip())
    if not m:
        return ""
    last = m.group(1).lower()
    year = m.group(2)
    base = f"ref_{last}_{year}"
    if base not in existing.values():
        return base
    # Collision handling — try _a, _b, … _z suffixes.
    for c in "abcdefghijklmnopqrstuvwxyz":
        candidate = f"{base}_{c}"
        if candidate not in existing.values():
            return candidate
    return base  # give up; caller may overwrite


def _inject_bookmark(paragraph: object, bookmark_id: str, counter: int) -> None:
    """Wrap the first run of *paragraph* with a Word bookmark.

    The bookmark id attribute (``w:id``) must be a non-negative integer.
    We use *counter* (starting at 1000) as the numeric id.

    Parameters
    ----------
    paragraph:
        A ``python-docx`` ``Paragraph`` object.
    bookmark_id:
        The symbolic name for the bookmark (e.g. ``ref_smith_2020``).
    counter:
        Numeric id for this bookmark (must be unique within the document).
    """
    from docx.oxml.ns import qn as _qn  # type: ignore[import]
    from docx.oxml import OxmlElement as _OxmlElement  # type: ignore[import]

    bm_start = _OxmlElement("w:bookmarkStart")
    bm_start.set(_qn("w:id"), str(counter))
    bm_start.set(_qn("w:name"), bookmark_id)

    bm_end = _OxmlElement("w:bookmarkEnd")
    bm_end.set(_qn("w:id"), str(counter))

    runs = paragraph._element.findall(_qn("w:r"))  # type: ignore[attr-defined]
    if runs:
        runs[0].addprevious(bm_start)
        runs[-1].addnext(bm_end)
    else:
        # No runs yet — append at the tail of the paragraph element.
        paragraph._element.append(bm_start)  # type: ignore[attr-defined]
        paragraph._element.append(bm_end)  # type: ignore[attr-defined]


def _build_reference_bookmarks(doc: object, humanized_text: str) -> dict[str, str]:
    """Scan the ``## References`` section of *humanized_text* and inject Word
    bookmarks into the matching DOCX paragraphs.

    Returns a mapping ``{bookmark_id: normalized_para_text}`` for all bookmarks
    that were successfully injected (used in Pass 3).
    """
    # Extract reference lines from the humanized text.
    ref_lines: list[str] = []
    in_refs = False
    for raw_line in humanized_text.splitlines():
        line = raw_line.strip()
        if not in_refs:
            if line.startswith("## References"):
                in_refs = True
            continue
        # Stop at the next heading.
        if line.startswith("#"):
            break
        if line and not line.startswith("#"):
            ref_lines.append(line)

    # Build a mapping: normalised line → bookmark id.
    line_to_bm: dict[str, str] = {}
    for line in ref_lines:
        if not _APA_LINE_RE.match(line):
            continue
        bm_id = _make_bookmark_id(line, {v: v for v in line_to_bm.values()})
        if bm_id:
            line_to_bm[line] = bm_id

    if not line_to_bm:
        return {}

    # Inject bookmarks into matching DOCX paragraphs.
    bookmark_map: dict[str, str] = {}  # bookmark_id → para text
    counter = 1000
    for para in doc.paragraphs:  # type: ignore[attr-defined]
        para_text = para.text.strip()
        if para_text in line_to_bm:
            bm_id = line_to_bm[para_text]
            _inject_bookmark(para, bm_id, counter)
            bookmark_map[bm_id] = para_text
            counter += 1

    return bookmark_map
