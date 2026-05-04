"""Five-step pipeline strip widget.

Renders the five pipeline stages (prescan / llm / determ / grammar /
postscan) as a row of markers that transition between four states:

* ``pending``  ⏺  (default)
* ``running``  ⏳
* ``done``     ✓
* ``skipped``  ✗  (also used for failure)

The :meth:`apply_event` method maps the ``StageEvent`` tuples emitted by
:func:`pipeline.runner.run_pipeline` into widget state, so a TUI screen can
just forward the callback without bookkeeping.
"""
from __future__ import annotations

from typing import Iterable

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

# In stage display order, matching the Transform screen wireframe.
STAGE_ORDER: tuple[str, ...] = ("prescan", "llm", "determ", "grammar", "postscan")

State = str  # "pending" | "running" | "done" | "skipped"

_MARKER: dict[str, str] = {
    "pending": "⏺",   # ⏺
    "running": "⏳",   # ⏳
    "done":    "✓",   # ✓
    "skipped": "✗",   # ✗
}

_STYLE: dict[str, str] = {
    "pending": "dim",
    "running": "bold yellow",
    "done":    "bold green",
    "skipped": "bold red",
}


class StagePipeline(Static):
    """Reactive five-marker strip driven by ``on_event`` callbacks."""

    DEFAULT_CSS = """
    StagePipeline {
        height: 1;
        width: 100%;
    }
    """

    # Reactive store of the per-stage state, exposed for tests.
    states: reactive[dict[str, str]] = reactive(
        lambda: {s: "pending" for s in STAGE_ORDER},
        always_update=True,
    )

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._states: dict[str, str] = {s: "pending" for s in STAGE_ORDER}

    def on_mount(self) -> None:
        self._refresh()

    # -- public API --------------------------------------------------------

    def reset(self) -> None:
        """Set every stage back to ``pending`` (e.g. before re-running)."""
        for s in STAGE_ORDER:
            self._states[s] = "pending"
        self._refresh()

    def state(self, stage: str) -> str:
        """Return the current state for ``stage`` (or ``"pending"`` if unknown)."""
        return self._states.get(stage, "pending")

    def set_state(self, stage: str, state: State) -> None:
        if stage in self._states and state in _MARKER:
            self._states[stage] = state
            self._refresh()

    def apply_event(self, event: tuple) -> None:
        """Translate a :data:`pipeline.runner.StageEvent` into a state change.

        Unknown event kinds are ignored so the widget stays compatible with
        future event additions.
        """
        if not event:
            return
        kind = event[0]
        if kind == "stage_start" and len(event) >= 2:
            self.set_state(event[1], "running")
        elif kind == "stage_done" and len(event) >= 2:
            self.set_state(event[1], "done")
        elif kind == "stage_skipped" and len(event) >= 2:
            self.set_state(event[1], "skipped")
        # determ_step events are handled by the LogPane, not the strip.

    # -- rendering ---------------------------------------------------------

    def _refresh(self) -> None:
        # Mirror into the reactive dict so tests/observers can read state.
        self.states = dict(self._states)
        self.update(self._render_text(self._states))

    def render(self) -> Text:  # type: ignore[override]
        return self._render_text(self._states)

    @staticmethod
    def _render_text(states: dict[str, str]) -> Text:
        out = Text()
        for i, stage in enumerate(STAGE_ORDER):
            st = states.get(stage, "pending")
            out.append(_MARKER[st] + " ", style=_STYLE[st])
            out.append(stage, style=_STYLE[st])
            if i != len(STAGE_ORDER) - 1:
                out.append("   →   ", style="dim")
        return out

    @staticmethod
    def stages() -> Iterable[str]:
        return STAGE_ORDER


__all__ = ["StagePipeline", "STAGE_ORDER"]
