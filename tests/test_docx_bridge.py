"""Tests for src/sis_caro_humanizer/docx_bridge.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from docx import Document

from sis_caro_humanizer.docx_bridge import extract_text, write_docx


def test_extract_text_roundtrip(tmp_path: Path) -> None:
    """extract_text should return both paragraphs, each present in output."""
    doc = Document()
    doc.add_paragraph("First paragraph here.")
    doc.add_paragraph("Second paragraph here.")
    docx_file = tmp_path / "sample.docx"
    doc.save(str(docx_file))

    result = extract_text(docx_file)

    assert "First paragraph here." in result
    assert "Second paragraph here." in result


def test_write_docx_replaces_text(tmp_path: Path) -> None:
    """write_docx should replace paragraph text with the humanized content."""
    doc = Document()
    doc.add_paragraph("Original first paragraph.")
    doc.add_paragraph("Original second paragraph.")
    original = tmp_path / "original.docx"
    doc.save(str(original))

    humanized = "Humanized first paragraph.\n\nHumanized second paragraph."
    out_path = tmp_path / "humanized.docx"
    write_docx(original, humanized, out_path)

    result_doc = Document(str(out_path))
    texts = [p.text for p in result_doc.paragraphs if p.text.strip()]
    assert texts[0] == "Humanized first paragraph."
    assert texts[1] == "Humanized second paragraph."


def test_extract_text_missing_dep(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """extract_text should raise ImportError when python-docx is not installed."""
    # Create a real .docx so the function reaches the import step.
    doc = Document()
    doc.add_paragraph("Some text.")
    docx_file = tmp_path / "test.docx"
    doc.save(str(docx_file))

    # Simulate python-docx being unavailable by setting sys.modules["docx"] = None.
    # We must also reload the bridge module so _require_docx() re-runs the import.
    import importlib

    import sis_caro_humanizer.docx_bridge as bridge_module

    monkeypatch.setitem(sys.modules, "docx", None)  # type: ignore[arg-type]
    # Reload so the cached import is cleared inside the module.
    monkeypatch.setattr(bridge_module, "_require_docx", lambda: (_ for _ in ()).throw(
        ImportError("python-docx is required for .docx support: pip install 'python-docx>=1.1'")
    ))

    with pytest.raises(ImportError, match="python-docx"):
        bridge_module.extract_text(docx_file)
