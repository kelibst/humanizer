"""_hyperlinks.py — internal hyperlink injection for citation parentheticals (Pass 3)."""
from __future__ import annotations

import re

from ._bookmarks import _APA_LINE_RE, _CITE_PAREN_RE

# ---------------------------------------------------------------------------
# Additional patterns
# ---------------------------------------------------------------------------

# Bare citation: Name, Year — used ONLY inside parenthetical groups to resolve
# multi-citation constructs like "(B & A, 2022. C & F, 2019)".
_CITE_BARE_RE = re.compile(
    r"(?P<key>[A-Z][\w\-']+(?:\s+et\s+al\.)?(?:\s*(?:,\s+|\s+(?:and|&)\s+)[A-Z][\w\-']+)*)"
    r"\s*,\s*"
    r"(?P<year>\d{4}[a-z]?)"
    r"(?:,\s*p{1,2}\.\s*\d+(?:[–\-]\d+)?)?"
)

# Any parenthetical group that is long enough to contain a citation.
_PAREN_GROUP_RE = re.compile(r"\([^)\n]{4,}\)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cite_anchor(cite_key: str, cite_year: str) -> str:
    """Derive the bookmark id from a citation key and year string."""
    year_digits = re.match(r"(\d{4})", cite_year)
    year = year_digits.group(1) if year_digits else cite_year
    key_clean = re.sub(r"\s*&\s*", " ", cite_key)
    key_clean = re.sub(r"\s+and\s+", " ", key_clean, flags=re.IGNORECASE)
    key_clean = re.sub(r"\s+et\s+al\.?", "", key_clean, flags=re.IGNORECASE)
    m = re.match(r"[A-Za-z][\w\-']+", key_clean)
    if not m:
        return ""
    last = m.group(0).lower()
    return f"ref_{last}_{year}"


def _collect_citation_links(
    para_text: str,
    bookmark_map: dict[str, str],
) -> list[tuple[int, int, str]]:
    """Return ``(start, end, anchor)`` tuples for every linkable citation in
    *para_text*, sorted by start offset.

    Primary scan: ``_CITE_PAREN_RE`` matches standalone ``(Name, Year)``.
    Secondary scan: ``_CITE_BARE_RE`` within parenthetical groups that were
    not fully consumed by a primary match — handles multi-citation constructs
    like ``(B & A, 2022. C & F, 2019)`` after markdown cleaning.
    """
    found: dict[int, tuple[int, int, str]] = {}

    # Primary — standalone (Name, Year)
    for m in _CITE_PAREN_RE.finditer(para_text):
        anchor = _cite_anchor(m.group("key"), m.group("year"))
        if anchor in bookmark_map:
            found[m.start()] = (m.start(), m.end(), anchor)

    # Secondary — individual citations within parenthetical groups
    for pg in _PAREN_GROUP_RE.finditer(para_text):
        gs, ge = pg.start(), pg.end()
        # Skip if a primary match already covers this entire group.
        if any(s <= gs and e >= ge for s, e, _ in found.values()):
            continue
        # Scan inside the group (pos 1..len-1 to skip the outer parens).
        group_text = pg.group()
        for bm in _CITE_BARE_RE.finditer(group_text, 1, len(group_text) - 1):
            anchor = _cite_anchor(bm.group("key"), bm.group("year"))
            if anchor not in bookmark_map:
                continue
            abs_start = gs + bm.start()
            abs_end = gs + bm.end()
            if abs_start not in found:
                found[abs_start] = (abs_start, abs_end, anchor)

    return sorted(found.values(), key=lambda x: x[0])


def _rebuild_paragraph_with_hyperlinks(
    paragraph: object,
    full_text: str,
    links: list[tuple[int, int, str]],
) -> None:
    """Rebuild *paragraph* inserting ``w:hyperlink`` elements at the given
    spans.  All existing runs and hyperlinks are removed first; the full
    paragraph text is then re-emitted as a sequence of plain runs and hyperlink
    runs according to *links*.

    Parameters
    ----------
    paragraph:
        A python-docx ``Paragraph`` object.
    full_text:
        The paragraph's plain text (captured *before* this call).
    links:
        Sorted ``(start, end, anchor)`` tuples — one per citation to link.
    """
    from docx.oxml.ns import qn as _qn
    from docx.oxml import OxmlElement as _OxmlElement

    p_el = paragraph._element  # type: ignore[attr-defined]

    # Capture run formatting from the first run for style preservation.
    old_runs = paragraph.runs  # type: ignore[attr-defined]
    rPr_xml: str | None = None
    if old_runs:
        rpr_el = old_runs[0]._element.find(_qn("w:rPr"))
        if rpr_el is not None:
            import xml.etree.ElementTree as _ET
            rPr_xml = _ET.tostring(rpr_el, encoding="unicode")

    # Clear the paragraph of all existing runs and hyperlinks.
    for el in list(p_el.findall(_qn("w:r"))):
        p_el.remove(el)
    for el in list(p_el.findall(_qn("w:hyperlink"))):
        p_el.remove(el)

    def _make_run(text: str) -> object:
        r = _OxmlElement("w:r")
        if rPr_xml:
            import xml.etree.ElementTree as _ET
            r.append(_ET.fromstring(rPr_xml))
        t = _OxmlElement("w:t")
        t.text = text
        if text and (text[0] == " " or text[-1] == " "):
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        r.append(t)
        return r

    def _make_hyperlink(text: str, anchor: str) -> object:
        hl = _OxmlElement("w:hyperlink")
        hl.set(_qn("w:anchor"), anchor)
        hl.set(_qn("w:history"), "1")
        r = _OxmlElement("w:r")
        rpr = _OxmlElement("w:rPr")
        # Use the built-in Hyperlink character style where defined, plus
        # explicit colour and underline as a fallback for documents that do
        # not have that style (common with user-supplied .docx templates).
        rs = _OxmlElement("w:rStyle")
        rs.set(_qn("w:val"), "Hyperlink")
        rpr.append(rs)
        color_el = _OxmlElement("w:color")
        color_el.set(_qn("w:val"), "0563C1")
        rpr.append(color_el)
        u_el = _OxmlElement("w:u")
        u_el.set(_qn("w:val"), "single")
        rpr.append(u_el)
        r.append(rpr)
        t = _OxmlElement("w:t")
        t.text = text
        if text and (text[0] == " " or text[-1] == " "):
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        r.append(t)
        hl.append(r)
        return hl

    # Emit segments: plain text between links, then hyperlink at each link span.
    cursor = 0
    for start, end, anchor in links:
        if cursor < start:
            p_el.append(_make_run(full_text[cursor:start]))
        p_el.append(_make_hyperlink(full_text[start:end], anchor))
        cursor = end
    if cursor < len(full_text):
        p_el.append(_make_run(full_text[cursor:]))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _embed_citation_hyperlinks(doc: object, bookmark_map: dict[str, str]) -> None:
    """Scan prose paragraphs and convert citation parentheticals to hyperlinks.

    Handles both standalone ``(Name, Year)`` citations and individual citations
    within multi-citation groups such as ``(B & A, 2022. C & F, 2019)``.
    All hyperlinks for a paragraph are injected in a single rebuild pass, so
    multiple citations per paragraph are all preserved.
    """
    if not bookmark_map:
        return

    for para in doc.paragraphs:  # type: ignore[attr-defined]
        para_text = para.text
        if not para_text.strip():
            continue
        # Skip reference-list paragraphs.
        if _APA_LINE_RE.match(para_text.strip()):
            continue

        links = _collect_citation_links(para_text, bookmark_map)
        if not links:
            continue

        _rebuild_paragraph_with_hyperlinks(para, para_text, links)
