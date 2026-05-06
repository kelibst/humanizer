"""_convert.py — new_docx_from_markdown: create a .docx from markdown text."""
from __future__ import annotations

import re
from pathlib import Path

from ._guard import _require_docx
from ._bookmarks import _build_reference_bookmarks
from ._hyperlinks import _embed_citation_hyperlinks


def _add_runs_with_formatting(para: object, text: str) -> None:
    """Append runs to *para* honouring ``**bold**`` and ``*italic*`` markers."""
    segments = re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", text)
    for seg in segments:
        if not seg:
            continue
        if seg.startswith("**") and seg.endswith("**"):
            run = para.add_run(seg[2:-2])  # type: ignore[attr-defined]
            run.bold = True
        elif seg.startswith("*") and seg.endswith("*"):
            run = para.add_run(seg[1:-1])  # type: ignore[attr-defined]
            run.italic = True
        else:
            para.add_run(seg)  # type: ignore[attr-defined]


def new_docx_from_markdown(humanized_text: str, output_path: Path) -> None:
    """Create a new .docx from *humanized_text* (markdown) without needing an
    original Word template.

    - ``# Heading`` lines → Heading 1; ``##`` → Heading 2; ``###`` → Heading 3.
    - Blank-line-separated blocks → Normal paragraphs (bold/italic preserved).
    - Pass 2 & 3: citation bookmarks and hyperlinks (same as ``write_docx``).
    """
    Document = _require_docx()
    doc = Document()

    for block in humanized_text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        heading_m = re.match(r"^(#{1,6})\s+(.*)", block)
        if heading_m:
            level = min(len(heading_m.group(1)), 9)
            doc.add_heading(heading_m.group(2).strip(), level=level)
        else:
            para = doc.add_paragraph()
            _add_runs_with_formatting(para, block)

    bookmark_map = _build_reference_bookmarks(doc, humanized_text)
    _embed_citation_hyperlinks(doc, bookmark_map)
    doc.save(str(output_path))
