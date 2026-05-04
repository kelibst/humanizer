"""Scrollable log pane for pipeline notes and per-transform tallies.

Used in the Transform screen below the diff. Receives lines via
:meth:`append_event` (translated from ``StageEvent`` tuples) or
:meth:`append_note` (free-form messages from ``PipelineResult.notes``).
"""
from __future__ import annotations

from typing import Iterable

from rich.text import Text
from textual.widgets import RichLog


class LogPane(RichLog):
    """RichLog tail of pipeline events / notes."""

    DEFAULT_CSS = """
    LogPane {
        height: 8;
        border: round $accent;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("highlight", False)
        kwargs.setdefault("markup", True)
        kwargs.setdefault("wrap", True)
        kwargs.setdefault("auto_scroll", True)
        super().__init__(**kwargs)

    def reset(self) -> None:
        self.clear()

    def append_note(self, note: str, *, style: str = "yellow") -> None:
        msg = Text()
        msg.append("note ", style="bold yellow")
        msg.append(note, style=style)
        self.write(msg)

    def append_event(self, event: tuple) -> None:
        """Translate a :data:`pipeline.runner.StageEvent` into a log line."""
        if not event:
            return
        kind = event[0]
        if kind == "stage_start" and len(event) >= 2:
            line = Text()
            line.append("→ ", style="bold cyan")
            line.append(f"{event[1]} started", style="cyan")
            self.write(line)
        elif kind == "stage_done" and len(event) >= 3:
            line = Text()
            line.append("✓ ", style="bold green")
            line.append(f"{event[1]} done ", style="green")
            line.append(f"({event[2] * 1000:.1f} ms)", style="dim")
            self.write(line)
        elif kind == "stage_skipped" and len(event) >= 3:
            line = Text()
            line.append("✗ ", style="bold red")
            line.append(f"{event[1]} skipped: ", style="red")
            line.append(str(event[2]), style="dim")
            self.write(line)
        elif kind == "determ_step" and len(event) >= 3:
            line = Text()
            line.append("  • ", style="bold magenta")
            line.append(f"{event[1]}: ", style="magenta")
            line.append(f"{event[2]} edit(s)", style="dim")
            self.write(line)

    def append_notes(self, notes: Iterable[str]) -> None:
        for n in notes:
            self.append_note(n)


__all__ = ["LogPane"]
