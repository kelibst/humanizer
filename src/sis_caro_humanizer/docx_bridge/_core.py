"""_core.py — extract_text and write_docx: the primary read/write operations."""
from __future__ import annotations

import sys
from pathlib import Path

from ._bookmarks import _build_reference_bookmarks
from ._hyperlinks import _embed_citation_hyperlinks


def _get_require_docx():
    """Look up _require_docx from the parent package so monkeypatches apply."""
    pkg = sys.modules.get(__package__)  # sis_caro_humanizer.docx_bridge
    if pkg is not None and hasattr(pkg, "_require_docx"):
        return pkg._require_docx
    from ._guard import _require_docx
    return _require_docx


def extract_text(path: Path) -> str:
    """Return the full text of a .docx file, paragraphs separated by ``\\n\\n``."""
    Document = _get_require_docx()()
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
    - Pass 2: inject ``w:bookmarkStart`` / ``w:bookmarkEnd`` around each
      reference-list paragraph that matches an APA entry from the
      ``## References`` section of *humanized_text*.
    - Pass 3: convert citation parentheticals in prose paragraphs into
      Word internal hyperlinks (``w:hyperlink`` with ``w:anchor``) pointing
      at the bookmarks created in Pass 2.
    - Save to *output_path*.
    """
    Document = _get_require_docx()()
    doc = Document(str(original_path))

    # Skip markdown headings (lines starting with '#') when mapping humanized
    # text back onto DOCX paragraph slots.  Headings exist in markdown but have
    # no direct DOCX paragraph equivalent here; treating them as content would
    # consume an original paragraph slot and offset the rest of the mapping.
    humanized_paras = [
        p.strip()
        for p in humanized_text.split("\n\n")
        if p.strip() and not p.strip().startswith("#")
    ]
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

    # Pass 2 — Reference bookmarks
    bookmark_map = _build_reference_bookmarks(doc, humanized_text)

    # Pass 3 — Citation hyperlinks in prose
    _embed_citation_hyperlinks(doc, bookmark_map)

    doc.save(str(output_path))
