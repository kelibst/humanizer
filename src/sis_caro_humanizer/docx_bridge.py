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


__all__ = ["extract_text", "write_docx"]
