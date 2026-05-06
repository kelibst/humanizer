"""_guard.py — import guard for python-docx."""
from __future__ import annotations


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
