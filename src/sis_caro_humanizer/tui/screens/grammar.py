"""Grammar screen (TUI_LAYOUT.md §2.4).

Pure read-only viewer for the existing grammar pass. Suppressed issues are
listed alongside active ones, marked ``supp.`` so the user sees what the
profile silenced. Heavy lifting (LanguageTool / Vale subprocesses) lives in
the existing :mod:`grammar.runner`; this screen runs it on a worker thread.
"""
from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, DataTable, Input, Static

from ...grammar.types import GrammarReport
from ...profile.loader import resolve_profile
from ...profile.schema import Profile
from ..widgets.tab_aware_input import TabAwareInput


class GrammarFinished(Message):
    def __init__(self, report: GrammarReport) -> None:
        super().__init__()
        self.report = report


class GrammarFailed(Message):
    def __init__(self, error: BaseException) -> None:
        super().__init__()
        self.error = error


class GrammarScreen(Screen):
    """Run and display grammar issues."""

    BINDINGS = [Binding("ctrl+s", "run", "run")]

    DEFAULT_CSS = """
    GrammarScreen {
        layout: vertical;
        padding: 1 2;
    }
    #g-input-row { height: 3; }
    #g-input { width: 1fr; }
    #g-status { color: $text-muted; height: 1; }
    #g-tools { color: $text-muted; height: 1; }
    #g-table { height: 1fr; }
    """

    def __init__(self, *, profile: Profile | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._profile: Profile = profile or resolve_profile("default_ghanaian")

    def compose(self) -> ComposeResult:
        yield Static("[bold]grammar[/bold]  —  LanguageTool · Vale · proselint", id="g-title")
        with Horizontal(id="g-input-row"):
            yield TabAwareInput(placeholder="path to .md/.txt file", id="g-input")
            yield Button("run", id="g-run-btn", variant="primary")
        yield Static("Ctrl+S run", id="g-status")
        yield Static("(tools status will appear after a run)", id="g-tools")
        table: DataTable = DataTable(id="g-table", zebra_stripes=True)
        table.add_columns("level", "tool", "rule", "offset", "status", "message")
        yield table

    # -- actions -----------------------------------------------------------

    def action_run(self) -> None:
        self._kick_off()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "g-run-btn":
            self._kick_off()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "g-input":
            self._kick_off()

    def _kick_off(self) -> None:
        path_or_text = self.query_one("#g-input", Input).value.strip()
        if not path_or_text:
            self._set_status("type a path or paste text first", error=True)
            return
        text = self._read_input(path_or_text)
        if text is None:
            return
        self._set_status("running grammar tools…")
        app = self.app
        target = self
        profile = self._profile

        def _do_work() -> GrammarReport:
            try:
                from ...grammar.runner import run_grammar
                report = run_grammar(text, profile)
            except Exception as exc:  # noqa: BLE001
                app.call_from_thread(target.post_message, GrammarFailed(exc))
                raise
            app.call_from_thread(target.post_message, GrammarFinished(report))
            return report

        app.run_worker(_do_work, name="humanizer-grammar", thread=True, exclusive=True, group="grammar")

    def _read_input(self, path_or_text: str) -> str | None:
        candidate = Path(path_or_text)
        try:
            if candidate.exists() and candidate.is_file():
                return candidate.read_text(encoding="utf-8")
        except OSError as exc:
            self._set_status(f"could not read {candidate}: {exc}", error=True)
            return None
        return path_or_text

    def _set_status(self, message: str, *, error: bool = False) -> None:
        self.query_one("#g-status", Static).update(
            Text(message, style="red" if error else "dim")
        )

    # -- messages ----------------------------------------------------------

    def on_grammar_finished(self, message: GrammarFinished) -> None:
        self._render_report(message.report)

    def on_grammar_failed(self, message: GrammarFailed) -> None:
        self._set_status(f"grammar failed: {message.error}", error=True)

    def _render_report(self, report: GrammarReport) -> None:
        tools_line = " ".join(
            f"{name}:{status}" for name, status in report.tool_status.items()
        )
        self.query_one("#g-tools", Static).update(Text(tools_line, style="dim"))

        table = self.query_one("#g-table", DataTable)
        table.clear()
        active = sum(1 for i in report.issues if not i.suppressed)
        suppressed = sum(1 for i in report.issues if i.suppressed)
        for issue in report.issues[:200]:
            level = "supp." if issue.suppressed else "on"
            table.add_row(
                level,
                issue.tool,
                issue.rule_id or "-",
                str(issue.offset),
                "supp." if issue.suppressed else "active",
                issue.message,
            )
        self._set_status(f"{active} active · {suppressed} suppressed")


__all__ = ["GrammarScreen", "GrammarFinished", "GrammarFailed"]
