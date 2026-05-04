"""Scrollable unified-diff pane.

Wraps :func:`reporting.diff.render_diff` and pushes the result into a
Textual :class:`RichLog` so the user can scroll. When the two strings are
identical the view shows a dim "no textual change." note instead.
"""
from __future__ import annotations

from rich.text import Text
from textual.widgets import RichLog

from ...reporting.diff import render_diff


class DiffView(RichLog):
    """RichLog pre-configured for displaying a unified diff."""

    DEFAULT_CSS = """
    DiffView {
        height: 1fr;
        border: round $primary;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("highlight", False)
        kwargs.setdefault("markup", True)
        kwargs.setdefault("wrap", False)
        kwargs.setdefault("auto_scroll", False)
        super().__init__(**kwargs)

    def show_diff(self, before: str, after: str) -> None:
        """Replace the pane's contents with the diff of ``before`` vs ``after``."""
        self.clear()
        if before == after:
            self.write(Text("no textual change.", style="dim"))
            return
        markup = render_diff(before, after)
        if not markup:
            self.write(Text("no textual change.", style="dim"))
            return
        for line in markup.splitlines():
            self.write(line)


__all__ = ["DiffView"]
