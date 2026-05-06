"""_comments.py — extract_word_comments: read reviewer comments from a .docx."""
from __future__ import annotations

from pathlib import Path

from ._guard import _require_docx


def extract_word_comments(path: Path) -> list[dict]:
    """Extract reviewer comments from a .docx file.

    Returns a list of dicts with keys:
      ``id``, ``author``, ``date``, ``text``, ``paragraph_idx``

    ``paragraph_idx`` is the approximate index (0-based) of the paragraph in
    the main body that anchors the comment.  When no anchor is found it is -1.

    Returns ``[]`` when the document has no comments part.
    """
    Document = _require_docx()
    doc = Document(str(path))

    WNS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    REL_COMMENTS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"

    # Locate the comments part via the relationship table.
    try:
        comments_part = doc.part.part_related_by(REL_COMMENTS)
    except KeyError:
        return []

    comments_el = comments_part._element
    results: list[dict] = []

    # Build a map from comment-id → paragraph index using the main body.
    # Walk all w:p elements in document order and note which carry a
    # w:commentReference with each id.
    body_paragraphs = doc._element.findall(f".//{{{WNS}}}p")
    id_to_para_idx: dict[str, int] = {}
    for para_idx, p_el in enumerate(body_paragraphs):
        for ref_el in p_el.findall(f".//{{{WNS}}}commentReference"):
            ref_id = ref_el.get(f"{{{WNS}}}id")
            if ref_id is not None and ref_id not in id_to_para_idx:
                id_to_para_idx[ref_id] = para_idx

    # Parse each w:comment element.
    for comment_el in comments_el.findall(f".//{{{WNS}}}comment"):
        c_id = comment_el.get(f"{{{WNS}}}id", "")
        author = comment_el.get(f"{{{WNS}}}author", "")
        date = comment_el.get(f"{{{WNS}}}date", "")
        # Join all w:t text nodes inside the comment.
        text_parts = [
            t.text for t in comment_el.findall(f".//{{{WNS}}}t") if t.text
        ]
        text = "".join(text_parts)
        para_idx = id_to_para_idx.get(c_id, -1)
        results.append(
            {
                "id": c_id,
                "author": author,
                "date": date,
                "text": text,
                "paragraph_idx": para_idx,
            }
        )

    return results
