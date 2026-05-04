"""Settings screen (TUI_LAYOUT.md §2.6).

This is intentionally a *read-mostly* placeholder for v1.2 round 1: the
backend abstraction lives behind Agent A's `backends/` and the `humanize
serve` daemon, neither of which is in this round's scope. We expose:

* the current backend choice (radio buttons, persisted-on-save behaviour
  is a stub — Settings persistence comes in a later round once Agent A's
  ``backend_config`` schema lands).
* a snapshot of Ollama's reachability (best-effort).
* the bridge daemon row, with a placeholder ``[start]`` button that
  surfaces a "not in this round" message rather than shelling out — Agent
  A owns ``humanize serve``.

The screen never raises if Ollama / backends are missing: it just shows a
dim "unavailable" line.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, RadioButton, RadioSet, Static

from ...config import DEFAULT_MODEL
from ..widgets.tab_aware_input import TabAwareInput


def _ollama_status_line() -> Text:
    """Best-effort reachability probe; never raises."""
    try:
        from ...ollama_client import is_running, list_models
    except Exception as exc:  # noqa: BLE001
        return Text(f"unavailable ({exc})", style="dim")
    try:
        running = is_running()
    except Exception as exc:  # noqa: BLE001
        return Text(f"probe failed: {exc}", style="dim")
    if not running:
        return Text("daemon not running", style="yellow")
    try:
        models = list_models()
    except Exception:  # noqa: BLE001
        models = []
    return Text(
        "running ✓  " + (", ".join(models[:3]) if models else "(no models found)"),
        style="green",
    )


class SettingsScreen(Screen):
    """Mostly-readonly settings page; full editing arrives with Agent A's backend config."""

    DEFAULT_CSS = """
    SettingsScreen {
        layout: vertical;
        padding: 1 2;
    }
    #s-section-backends, #s-section-bridge, #s-section-misc {
        border: round $primary;
        padding: 1 2;
        height: auto;
        margin-bottom: 1;
    }
    #s-section-title {
        text-style: bold;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="s-section-backends"):
            yield Static("[bold]backend[/bold]", id="s-section-title")
            with RadioSet(id="s-backend"):
                yield RadioButton("ollama", value=True, id="s-be-ollama")
                yield RadioButton("anthropic", id="s-be-anthropic")
                yield RadioButton("openai", id="s-be-openai")
                yield RadioButton("gemini", id="s-be-gemini")
            yield Static(id="s-ollama-status")
            yield Static(
                f"default model: {DEFAULT_MODEL}",
                id="s-default-model",
            )
            yield Static(
                "(hosted-API key fields land with Agent A's backend config)",
                id="s-be-note",
            )

        with Vertical(id="s-section-bridge"):
            yield Static("[bold]docs bridge daemon[/bold]")
            with Horizontal():
                yield Label("port:")
                yield TabAwareInput(value="9999", id="s-bridge-port")
                yield Label("host:")
                yield TabAwareInput(value="127.0.0.1", id="s-bridge-host")
            yield Static("status: stopped", id="s-bridge-status")
            with Horizontal():
                yield Button("start daemon", id="s-bridge-start", disabled=True)
                yield Button("stop", id="s-bridge-stop", disabled=True)
            yield Static(
                "(bridge daemon ships with Agent A's `humanize serve` sub-app)",
                id="s-bridge-note",
            )

        with Vertical(id="s-section-misc"):
            yield Static("[bold]misc[/bold]")
            with Horizontal():
                yield Label("default profile:")
                yield TabAwareInput(value="default_ghanaian", id="s-default-profile")
            with Horizontal():
                yield Label("risk target:")
                yield TabAwareInput(value="0.35", id="s-risk-target")

    def on_mount(self) -> None:
        self.query_one("#s-ollama-status", Static).update(
            Text.assemble(("ollama: ", "bold"), _ollama_status_line())
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in {"s-bridge-start", "s-bridge-stop"}:
            self.query_one("#s-bridge-note", Static).update(
                Text(
                    "bridge daemon control is provided by Agent A's `humanize serve` "
                    "sub-app — run it from a separate terminal.",
                    style="yellow",
                )
            )


__all__ = ["SettingsScreen"]
