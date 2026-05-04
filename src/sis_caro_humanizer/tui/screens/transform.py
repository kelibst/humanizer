"""Transform screen: full pipeline runner (TUI_LAYOUT.md §2.3).

User flow:
* type or paste a path / text
* tick the stages to run (defaults: prescan, determ, postscan — fast path)
* press ``Ctrl+S`` (or the Run button) to kick off the worker
* the stage strip animates as ``StageEvent``s flow in; when the worker
  finishes, the diff pane renders before/after and the score gauge reflects
  the post score.
"""
from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Input, Static

from ...pipeline.runner import ALL_STAGES, PipelineResult
from ...profile.loader import resolve_profile
from ...profile.schema import Profile
from ..runner_bridge import (
    PipelineEvent,
    PipelineFailed,
    PipelineFinished,
    TransformRequest,
    run_pipeline_in_worker,
)
from ..widgets.diff_view import DiffView
from ..widgets.log_pane import LogPane
from ..widgets.score_gauge import ScoreGauge
from ..widgets.stage_pipeline import STAGE_ORDER, StagePipeline
from ..widgets.tab_aware_input import TabAwareInput

# Default stage selection — fast path that does not require Ollama.
DEFAULT_STAGES: tuple[str, ...] = ("prescan", "determ", "postscan")


class TransformScreen(Screen):
    """Pipeline-runner screen with stage strip, diff, and post-score gauge."""

    BINDINGS = [
        Binding("ctrl+s", "run", "run"),
        Binding("ctrl+d", "toggle_diff", "diff"),
    ]

    DEFAULT_CSS = """
    TransformScreen {
        layout: vertical;
        padding: 1 2;
    }
    #t-input-row {
        height: 3;
    }
    #t-input {
        width: 1fr;
    }
    #t-stages-row {
        height: 3;
    }
    #t-seed-row {
        height: 3;
    }
    #t-status {
        color: $text-muted;
        height: 1;
    }
    #t-pipeline {
        margin-top: 1;
    }
    #t-diff {
        height: 1fr;
        margin-top: 1;
    }
    #t-log {
        height: 6;
    }
    #t-postscore-row {
        height: 3;
    }
    #t-stages-row Checkbox {
        margin-right: 1;
    }
    """

    def __init__(
        self,
        *,
        profile: Profile | None = None,
        initial_path: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._profile: Profile = profile or resolve_profile("default_ghanaian")
        self._initial_path = initial_path or ""
        self._last_input: str | None = None
        self._last_result: PipelineResult | None = None

    def compose(self) -> ComposeResult:
        yield Static("[bold]transform[/bold]  —  rewrite a document", id="t-title")

        with Horizontal(id="t-input-row"):
            yield TabAwareInput(
                value=self._initial_path,
                placeholder="path to a .md/.txt file (or paste text)",
                id="t-input",
            )
            yield Button("run", id="t-run-btn", variant="primary")

        with Horizontal(id="t-stages-row"):
            for stage in ALL_STAGES:
                yield Checkbox(
                    stage,
                    value=stage in DEFAULT_STAGES,
                    id=f"t-stage-{stage}",
                )

        with Horizontal(id="t-seed-row"):
            yield TabAwareInput(value="1337", placeholder="seed", id="t-seed")

        yield Static("Ctrl+S run · Ctrl+D toggle diff", id="t-status")
        yield StagePipeline(id="t-pipeline")
        yield DiffView(id="t-diff")
        yield LogPane(id="t-log")

        with Horizontal(id="t-postscore-row"):
            yield Static("post score:", id="t-postscore-label")
            yield ScoreGauge(id="t-postscore-gauge")

    # -- actions -----------------------------------------------------------

    def action_run(self) -> None:
        self._kick_off_run()

    def action_toggle_diff(self) -> None:
        diff = self.query_one("#t-diff", DiffView)
        if diff.has_class("-hidden"):
            diff.remove_class("-hidden")
        else:
            diff.add_class("-hidden")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "t-run-btn":
            self._kick_off_run()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "t-input":
            self._kick_off_run()

    # -- internals ---------------------------------------------------------

    def _selected_stages(self) -> tuple[str, ...]:
        out: list[str] = []
        for stage in ALL_STAGES:
            cb = self.query_one(f"#t-stage-{stage}", Checkbox)
            if cb.value:
                out.append(stage)
        return tuple(out) or DEFAULT_STAGES

    def _read_seed(self) -> int | None:
        raw = self.query_one("#t-seed", Input).value.strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def _kick_off_run(self) -> None:
        path_or_text = self.query_one("#t-input", Input).value.strip()
        if not path_or_text:
            self._set_status("type a path or paste text first", error=True)
            return
        text = self._read_input(path_or_text)
        if text is None:
            return
        self._last_input = text

        # Reset UI for a new run.
        self.query_one("#t-pipeline", StagePipeline).reset()
        self.query_one("#t-log", LogPane).reset()
        self.query_one("#t-diff", DiffView).clear()
        gauge = self.query_one("#t-postscore-gauge", ScoreGauge)
        gauge.set_score(0.0, "low")

        request = TransformRequest(
            text=text,
            profile=self._profile,
            stages=self._selected_stages(),
            seed=self._read_seed(),
        )
        self._set_status("running…")
        run_pipeline_in_worker(self, request)

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
        status = self.query_one("#t-status", Static)
        style = "red" if error else "dim"
        status.update(Text(message, style=style))

    # -- pipeline messages -------------------------------------------------

    def on_pipeline_event(self, message: PipelineEvent) -> None:
        self.query_one("#t-pipeline", StagePipeline).apply_event(message.event)
        self.query_one("#t-log", LogPane).append_event(message.event)

    def on_pipeline_finished(self, message: PipelineFinished) -> None:
        self._last_result = message.result
        result = message.result

        # Diff
        self.query_one("#t-diff", DiffView).show_diff(result.input, result.output)

        # Post-score gauge
        post = result.post_score
        gauge = self.query_one("#t-postscore-gauge", ScoreGauge)
        gauge.set_score(post.score, post.band)

        # Status line
        pre = result.pre_score
        delta = post.score - pre.score
        sign = "+" if delta >= 0 else ""
        determ_count = len(result.deterministic_log)
        self._set_status(
            f"pre {pre.score:.3f} ({pre.band}) → post {post.score:.3f} ({post.band})  "
            f"Δ {sign}{delta:.3f}  "
            f"determ_edits={determ_count}  "
            f"elapsed={result.elapsed_seconds:.2f}s  "
            f"llm={'yes' if result.llm_used else 'no'}"
        )
        # Fold any pipeline notes into the log pane.
        log = self.query_one("#t-log", LogPane)
        for note in result.notes:
            log.append_note(note)

    def on_pipeline_failed(self, message: PipelineFailed) -> None:
        self._set_status(f"pipeline failed: {message.error}", error=True)


__all__ = ["TransformScreen", "DEFAULT_STAGES"]
