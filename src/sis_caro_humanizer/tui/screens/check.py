"""Check screen: score a file for AI-risk (TUI_LAYOUT.md §2.2).

Workflow:
* user types a path (or pastes text); ``Ctrl+S`` runs :func:`ai_risk_score`
* the gauge fills; the top three contributors render below as bar/detail rows
* ``Ctrl+W`` toggles the "why" detail panel

Reads the file synchronously (small) but runs scoring in a worker thread
via :func:`tui.runner_bridge.run_score_in_worker` so a giant chapter does
not freeze the UI.
"""
from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Static

from ...profile.loader import resolve_profile
from ...profile.schema import Profile
from ...scoring.risk import ScoreReport, ai_risk_score
from ..runner_bridge import ScoreFailed, ScoreFinished, run_score_in_worker
from ..widgets.score_gauge import ScoreGauge
from ..widgets.tab_aware_input import TabAwareInput


class CheckScreen(Screen):
    """Single-pane scoring screen."""

    BINDINGS = [
        Binding("ctrl+s", "score", "score"),
        Binding("ctrl+w", "toggle_why", "why"),
        Binding("ctrl+t", "open_transform", "→ transform"),
    ]

    DEFAULT_CSS = """
    CheckScreen {
        layout: vertical;
        padding: 1 2;
    }
    #check-input-row {
        height: 3;
    }
    #check-input {
        width: 1fr;
    }
    #check-status {
        color: $text-muted;
        height: 1;
    }
    #check-gauge-title, #check-why-title {
        text-style: bold;
        margin-top: 1;
    }
    #check-why {
        height: auto;
        border: round $primary;
        padding: 0 1;
    }
    #check-why.-hidden {
        display: none;
    }
    #check-gauge {
        height: 1;
    }
    """

    def __init__(self, *, profile: Profile | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._profile: Profile = profile or resolve_profile("default_ghanaian")
        self._last_text: str | None = None
        self._last_score: ScoreReport | None = None

    def compose(self) -> ComposeResult:
        yield Static("[bold]check[/bold]  —  score a document for AI-detector risk", id="check-title")
        with Horizontal(id="check-input-row"):
            yield TabAwareInput(
                placeholder="path to .md/.txt file (or paste text below)",
                id="check-input",
            )
            yield Button("score", id="check-run-btn", variant="primary")
        yield Static("Ctrl+S score · Ctrl+W why · Ctrl+T → transform", id="check-status")
        yield Static("score", id="check-gauge-title")
        yield ScoreGauge(id="check-gauge")
        yield Static("contributors", id="check-why-title")
        yield Static("(run a check to see the top contributors)", id="check-why")

    # -- actions -----------------------------------------------------------

    def action_score(self) -> None:
        self._kick_off_score()

    def action_toggle_why(self) -> None:
        why = self.query_one("#check-why", Static)
        if why.has_class("-hidden"):
            why.remove_class("-hidden")
        else:
            why.add_class("-hidden")

    def action_open_transform(self) -> None:
        path_value = self.query_one("#check-input", Input).value.strip()
        self.app.action_open_tab("t", initial_path=path_value)  # type: ignore[attr-defined]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "check-run-btn":
            self._kick_off_score()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "check-input":
            self._kick_off_score()

    # -- internal ---------------------------------------------------------

    def _kick_off_score(self) -> None:
        path_or_text = self.query_one("#check-input", Input).value.strip()
        if not path_or_text:
            self._set_status("type a path or paste text first", error=True)
            return
        text = self._read_input(path_or_text)
        if text is None:
            return
        self._last_text = text
        self._set_status("scoring…")
        # For very small inputs, score inline so tests get a synchronous
        # update; large inputs run on a worker thread.
        if len(text) < 2_000:
            try:
                report = ai_risk_score(text, self._profile)
            except Exception as exc:  # noqa: BLE001
                self._set_status(f"score failed: {exc}", error=True)
                return
            self._apply_score(report)
            return
        run_score_in_worker(self, text, self._profile)

    def _read_input(self, path_or_text: str) -> str | None:
        # If the value looks like a file path that exists, read it; otherwise
        # treat the value as inline text.
        candidate = Path(path_or_text)
        try:
            if candidate.exists() and candidate.is_file():
                return candidate.read_text(encoding="utf-8")
        except OSError as exc:
            self._set_status(f"could not read {candidate}: {exc}", error=True)
            return None
        return path_or_text

    def _set_status(self, message: str, *, error: bool = False) -> None:
        status = self.query_one("#check-status", Static)
        style = "red" if error else "dim"
        status.update(Text(message, style=style))

    def on_score_finished(self, message: ScoreFinished) -> None:
        self._apply_score(message.score)

    def on_score_failed(self, message: ScoreFailed) -> None:
        self._set_status(f"score failed: {message.error}", error=True)

    def _apply_score(self, report: ScoreReport) -> None:
        self._last_score = report
        gauge = self.query_one("#check-gauge", ScoreGauge)
        gauge.set_score(report.score, report.band)
        self._set_status(
            f"score: {report.score:.3f} ({report.band})  "
            f"weighted_sum={report.raw_weighted_sum:.3f}"
        )
        self._render_why(report)

    def _render_why(self, report: ScoreReport) -> None:
        why = self.query_one("#check-why", Static)
        components = sorted(
            report.components, key=lambda c: c.value * c.weight, reverse=True
        )[:5]
        out = Text()
        for c in components:
            bar_cells = int(round(c.value * 24))
            out.append(f"{c.name:<26}", style="bold")
            out.append("▓" * bar_cells, style="cyan")
            out.append("░" * (24 - bar_cells), style="dim")
            out.append(f"  {c.value:.2f}  ", style="bold cyan")
            out.append(c.detail or "", style="dim")
            if c.examples:
                out.append("   " + ", ".join(c.examples[:3]), style="italic dim")
            out.append("\n")
        why.update(out)


__all__ = ["CheckScreen"]
