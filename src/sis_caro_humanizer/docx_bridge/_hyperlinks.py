"""_hyperlinks.py — internal hyperlink injection for citation parentheticals (Pass 3)."""
from __future__ import annotations

import re

from ._bookmarks import _APA_LINE_RE, _CITE_PAREN_RE


def _add_internal_hyperlink(paragraph: object, anchor: str, match_text: str) -> None:
    """Replace the portion of *paragraph*'s run text that equals *match_text*
    with a ``w:hyperlink`` element pointing at *anchor*.

    Because paragraph runs may be split arbitrarily by python-docx we use a
    destructive-rebuild strategy:

    1. Find the full paragraph text and locate *match_text* within it.
    2. Clear all runs.
    3. Re-add three synthetic runs: prefix text, hyperlink run, suffix text.
    """
    from docx.oxml.ns import qn as _qn  # type: ignore[import]
    from docx.oxml import OxmlElement as _OxmlElement  # type: ignore[import]

    full_text = paragraph.text  # type: ignore[attr-defined]
    idx = full_text.find(match_text)
    if idx == -1:
        return

    # Capture style from first run (if any) for font preservation.
    old_runs = paragraph.runs  # type: ignore[attr-defined]
    rPr_xml: str | None = None
    if old_runs:
        rpr_el = old_runs[0]._element.find(_qn("w:rPr"))
        if rpr_el is not None:
            import xml.etree.ElementTree as _ET
            rPr_xml = _ET.tostring(rpr_el, encoding="unicode")

    # Clear all existing runs from the paragraph element.
    p_el = paragraph._element  # type: ignore[attr-defined]
    for r_el in list(p_el.findall(_qn("w:r"))):
        p_el.remove(r_el)
    for hl_el in list(p_el.findall(_qn("w:hyperlink"))):
        p_el.remove(hl_el)

    def _make_run(text: str) -> object:
        r = _OxmlElement("w:r")
        if rPr_xml:
            import xml.etree.ElementTree as _ET
            rpr_copy = _ET.fromstring(rPr_xml)
            r.append(rpr_copy)
        t = _OxmlElement("w:t")
        t.text = text
        if text and (text[0] == " " or text[-1] == " "):
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        r.append(t)
        return r

    prefix = full_text[:idx]
    suffix = full_text[idx + len(match_text):]

    if prefix:
        p_el.append(_make_run(prefix))

    # Build the hyperlink element.
    hyperlink = _OxmlElement("w:hyperlink")
    hyperlink.set(_qn("w:anchor"), anchor)
    link_run = _OxmlElement("w:r")
    # Always apply the built-in "Hyperlink" character style so Word renders
    # the link as blue underlined text rather than plain text.
    rpr = _OxmlElement("w:rPr")
    r_style = _OxmlElement("w:rStyle")
    r_style.set(_qn("w:val"), "Hyperlink")
    rpr.append(r_style)
    link_run.append(rpr)
    link_t = _OxmlElement("w:t")
    link_t.text = match_text
    if match_text and (match_text[0] == " " or match_text[-1] == " "):
        link_t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    link_run.append(link_t)
    hyperlink.append(link_run)
    p_el.append(hyperlink)

    if suffix:
        p_el.append(_make_run(suffix))


def _cite_anchor(cite_key: str, cite_year: str) -> str:
    """Derive the bookmark id from a citation key and year string."""
    # Strip trailing letter from year (2020a → 2020).
    year_digits = re.match(r"(\d{4})", cite_year)
    year = year_digits.group(1) if year_digits else cite_year
    # First author last name.
    key_clean = re.sub(r"\s*&\s*", " ", cite_key)
    key_clean = re.sub(r"\s+and\s+", " ", key_clean, flags=re.IGNORECASE)
    key_clean = re.sub(r"\s+et\s+al\.?", "", key_clean, flags=re.IGNORECASE)
    m = re.match(r"[A-Za-z][\w\-']+", key_clean)
    if not m:
        return ""
    last = m.group(0).lower()
    return f"ref_{last}_{year}"


def _embed_citation_hyperlinks(doc: object, bookmark_map: dict[str, str]) -> None:
    """Scan prose paragraphs and convert citation parentheticals to hyperlinks.

    Only paragraphs whose text does NOT look like a reference entry are
    processed (we skip lines that themselves are APA references).
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

        # Find all citation parentheticals in this paragraph, left-to-right.
        matches = list(_CITE_PAREN_RE.finditer(para_text))
        if not matches:
            continue

        # Process citations left-to-right.  After each rebuild the para text
        # changes, so we re-scan from scratch.  We track which anchors we have
        # already linked so we don't loop infinitely.
        linked: set[str] = set()
        for _ in range(len(matches)):
            current_text = para.text
            m = _CITE_PAREN_RE.search(current_text)
            if not m:
                break
            anchor = _cite_anchor(m.group("key"), m.group("year"))
            match_text = m.group(0)
            if anchor not in bookmark_map or anchor in linked:
                # Try the next citation if this one cannot be linked.
                # Since we are scanning left-to-right and only skip unresolvable
                # ones, we must stop here to avoid an infinite loop.
                break
            _add_internal_hyperlink(para, anchor, match_text)
            linked.add(anchor)
