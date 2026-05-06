"""docx_bridge — read and write .docx files for the humanizer pipeline.

Public API
----------
extract_text(path)  → str
    Return the full text of a .docx file, paragraphs separated by double
    newlines.

write_docx(original_path, humanized_text, output_path) → None
    Write a new .docx whose paragraph text is replaced by the humanized
    text (preserving the original paragraph styles).  After the replacement
    pass, two additional passes add Word bookmarks on reference entries and
    internal hyperlinks on citation parentheticals in prose.

Both functions raise ``ImportError`` with a helpful message when
``python-docx`` is not installed.
"""
from __future__ import annotations

from ._guard import _require_docx
from ._core import extract_text, write_docx
from ._convert import new_docx_from_markdown
from ._tracking import accept_tracked_changes
from ._comments import extract_word_comments
from ._diff import diff_text_sections

# Private helpers re-exported for tests (preserved from the original module).
from ._bookmarks import _make_bookmark_id, _inject_bookmark
from ._hyperlinks import _add_internal_hyperlink

__all__ = [
    "extract_text",
    "write_docx",
    "new_docx_from_markdown",
    "accept_tracked_changes",
    "extract_word_comments",
    "diff_text_sections",
    # B1 helpers (exported for tests)
    "_require_docx",
    "_make_bookmark_id",
    "_inject_bookmark",
    "_add_internal_hyperlink",
]
