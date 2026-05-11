"""_convert.py — new_docx_from_markdown / export_as_pdf: create docs from markdown."""
from __future__ import annotations

import re
import subprocess
import shutil
import tempfile
from pathlib import Path

from ._guard import _require_docx
from ._bookmarks import _build_reference_bookmarks, clean_citation_markup
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

    humanized_text = clean_citation_markup(humanized_text)

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


def export_as_pdf(humanized_text: str, output_path: Path) -> str:
    """Create a fully-linked DOCX then convert it to PDF.

    Tries LibreOffice headless first, then pandoc. Raises ``RuntimeError``
    if neither tool is on PATH. Returns the path of the produced PDF as a
    string.
    """
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tf:
        docx_path = Path(tf.name)

    try:
        new_docx_from_markdown(humanized_text, docx_path)

        if shutil.which("libreoffice"):
            subprocess.run(
                [
                    "libreoffice", "--headless", "--convert-to", "pdf",
                    "--outdir", str(output_path.parent), str(docx_path),
                ],
                check=True,
                timeout=120,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            lo_out = output_path.parent / (docx_path.stem + ".pdf")
            if lo_out.exists() and lo_out != output_path:
                lo_out.rename(output_path)
        elif shutil.which("pandoc"):
            subprocess.run(
                ["pandoc", str(docx_path), "-o", str(output_path)],
                check=True,
                timeout=120,
            )
        else:
            raise RuntimeError(
                "Neither LibreOffice nor pandoc is installed. "
                "Install one (e.g. 'sudo apt install libreoffice') to enable PDF export."
            )
    finally:
        docx_path.unlink(missing_ok=True)

    return str(output_path)
