"""docx_bridge.py — read and write .docx files for the humanizer pipeline.

Public API
----------
extract_text(path)  → str
    Return the full text of a .docx file, paragraphs separated by double
    newlines.

write_docx(original_path, humanized_text, output_path) → None
    Write a new .docx whose paragraph text is replaced by the humanized
    text (preserving the original paragraph styles).

Both functions raise ``ImportError`` with a helpful message when
``python-docx`` is not installed.
"""
from __future__ import annotations

from pathlib import Path


def _require_docx():
    """Import and return ``docx.Document``, raising ImportError if absent."""
    try:
        from docx import Document  # type: ignore[import]

        return Document
    except ImportError as exc:
        raise ImportError(
            "python-docx is required for .docx support: "
            "pip install 'python-docx>=1.1'"
        ) from exc


def extract_text(path: Path) -> str:
    """Return the full text of a .docx file, paragraphs separated by ``\\n\\n``."""
    Document = _require_docx()
    doc = Document(str(path))
    parts = [para.text for para in doc.paragraphs if para.text.strip()]
    return "\n\n".join(parts)


def write_docx(original_path: Path, humanized_text: str, output_path: Path) -> None:
    """Write a new .docx at *output_path* with paragraph text replaced by
    *humanized_text*.

    Strategy
    --------
    - Open *original_path* with python-docx.
    - Split *humanized_text* into paragraphs on double-newline.
    - Walk the original document's paragraphs in order.
    - For each original paragraph that has non-empty text:
        - Pop the next humanized paragraph; replace the run text while
          preserving the original paragraph's style.
        - If humanized paragraphs run out, keep the original text.
    - Save to *output_path*.
    """
    Document = _require_docx()
    doc = Document(str(original_path))

    humanized_paras = [p.strip() for p in humanized_text.split("\n\n") if p.strip()]
    h_iter = iter(humanized_paras)

    for para in doc.paragraphs:
        if not para.text.strip():
            continue
        replacement = next(h_iter, None)
        if replacement is None:
            break
        # Clear all runs, then set the text on the first run (preserving style).
        for run in para.runs:
            run.text = ""
        if para.runs:
            para.runs[0].text = replacement
        else:
            para.add_run(replacement)

    doc.save(str(output_path))


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


def diff_text_sections(original: str, revised: str) -> list[dict]:
    """Compare two texts paragraph-by-paragraph and return a diff report.

    Parameters
    ----------
    original:
        The original text (before lecturer changes).
    revised:
        The revised / accepted text (after ``accept_tracked_changes``).

    Returns
    -------
    list of dicts with keys:
      ``original`` (str) — original paragraph text (empty string if inserted)
      ``revised``  (str) — revised paragraph text (empty string if deleted)
      ``changed``  (bool)
      ``paragraph_idx`` (int) — 0-based index in the *revised* list
    """
    import difflib

    def _split(text: str) -> list[str]:
        return [p.strip() for p in text.split("\n\n") if p.strip()]

    orig_paras = _split(original)
    rev_paras = _split(revised)

    matcher = difflib.SequenceMatcher(None, orig_paras, rev_paras, autojunk=False)
    sections: list[dict] = []

    rev_idx = 0  # tracks position in the revised list

    for opcode, i1, i2, j1, j2 in matcher.get_opcodes():
        if opcode == "equal":
            for k, para in enumerate(rev_paras[j1:j2]):
                sections.append(
                    {
                        "original": para,
                        "revised": para,
                        "changed": False,
                        "paragraph_idx": j1 + k,
                    }
                )
        elif opcode == "replace":
            # Pair up as many orig ↔ revised as possible; extras are inserts/deletes.
            orig_chunk = orig_paras[i1:i2]
            rev_chunk = rev_paras[j1:j2]
            max_len = max(len(orig_chunk), len(rev_chunk))
            for k in range(max_len):
                orig_text = orig_chunk[k] if k < len(orig_chunk) else ""
                rev_text = rev_chunk[k] if k < len(rev_chunk) else ""
                # paragraph_idx in the revised list — use j1+k for revised side
                p_idx = j1 + k if k < len(rev_chunk) else j2 - 1
                sections.append(
                    {
                        "original": orig_text,
                        "revised": rev_text,
                        "changed": True,
                        "paragraph_idx": p_idx,
                    }
                )
        elif opcode == "delete":
            for k, para in enumerate(orig_paras[i1:i2]):
                sections.append(
                    {
                        "original": para,
                        "revised": "",
                        "changed": True,
                        "paragraph_idx": j1,  # insertion point in revised
                    }
                )
        elif opcode == "insert":
            for k, para in enumerate(rev_paras[j1:j2]):
                sections.append(
                    {
                        "original": "",
                        "revised": para,
                        "changed": True,
                        "paragraph_idx": j1 + k,
                    }
                )

    return sections


__all__ = [
    "extract_text",
    "write_docx",
    "accept_tracked_changes",
    "extract_word_comments",
    "diff_text_sections",
]
