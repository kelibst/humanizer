"""_tracking.py — accept_tracked_changes: resolve w:ins / w:del elements."""
from __future__ import annotations

from pathlib import Path

from ._guard import _require_docx


def accept_tracked_changes(path: Path) -> str:
    """Return the document text after accepting all tracked changes.

    - Text inside ``w:ins`` elements (insertions) is included.
    - Text inside ``w:del`` elements (deletions) is excluded entirely.
    - Normal run text is included unchanged.

    Paragraphs are joined with ``\\n\\n``.  Empty paragraphs are dropped.
    """
    Document = _require_docx()
    doc = Document(str(path))

    WNS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    paragraphs_text: list[str] = []
    for p_el in doc._element.findall(f".//{{{WNS}}}p"):
        parts: list[str] = []

        for child in p_el.iter():
            tag_local = child.tag.split("}")[-1] if "}" in child.tag else child.tag

            # Skip the text nodes that are inside w:del
            if tag_local == "del":
                # We skip the entire subtree by recording nothing; iter() visits
                # children too, but we only collect w:t text below, so we need
                # to mark deleted runs so their w:t nodes are ignored.
                # The cleanest approach: collect from direct w:r and w:ins children.
                pass

        # Re-walk collecting text correctly: normal runs and inserted runs only.
        for child in p_el:
            tag_local = child.tag.split("}")[-1] if "}" in child.tag else child.tag

            if tag_local == "del":
                # Skip deleted runs entirely.
                continue
            elif tag_local == "ins":
                # Accept insertions: include w:r/w:t inside.
                for t_el in child.findall(f".//{{{WNS}}}t"):
                    if t_el.text:
                        parts.append(t_el.text)
            elif tag_local == "r":
                # Normal run.
                for t_el in child.findall(f".//{{{WNS}}}t"):
                    if t_el.text:
                        parts.append(t_el.text)

        text = "".join(parts).strip()
        if text:
            paragraphs_text.append(text)

    return "\n\n".join(paragraphs_text)
