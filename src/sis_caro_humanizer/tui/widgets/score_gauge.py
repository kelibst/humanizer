"""Horizontal coloured gauge for an AI-risk score.

Specified in ``plan/TUI_LAYOUT.md`` §3.1: 60-char-wide bar coloured by the
score's band (green LOW / yellow MEDIUM / red HIGH) with the numeric score
and band label as a suffix. Reactive ``score`` and ``band`` properties drive
re-render.

The widget is dependency-light and renders pure Rich markup so unit tests
can call :meth:`render` directly without mounting Textual.
"""
from __future__ import annotations

from typing import Literal

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

Band = Literal["low", "medium", "high", ""]

_BAND_STYLE: dict[str, str] = {
    "low": "bold green",
    "medium": "bold yellow",
    "high": "bold red",
}

_BAR_WIDTH: int = 60


def _band_for(score: float) -> Band:
    if score < 0.34:
        return "low"
    if score < 0.67:
        return "medium"
    return "high"


class ScoreGauge(Static):
    """Bar showing an AI-risk score from 0..1 with band colour.

    Set :attr:`score` to update; :attr:`band` is recomputed automatically but
    can also be overridden (e.g. when feeding a value directly from a
    ``ScoreReport`` whose band is already known).
    """

    DEFAULT_CSS = """
    ScoreGauge {
        height: 1;
        width: 100%;
    }
    """

    score: reactive[float] = reactive(0.0)
    band: reactive[str] = reactive("")

    def __init__(self, score: float = 0.0, band: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._initial_score = float(score)
        self._initial_band = band

    def on_mount(self) -> None:
        self.set_score(self._initial_score, self._initial_band)

    def set_score(self, score: float, band: str | None = None) -> None:
        """Update the gauge atomically (one re-render)."""
        clamped = max(0.0, min(1.0, float(score)))
        self.score = clamped
        self.band = band or _band_for(clamped)
        self.update(self.render())

    def render(self) -> Text:  # type: ignore[override]
        return self._render_text(self.score, self.band)

    @staticmethod
    def _render_text(score: float, band: str) -> Text:
        """Build the gauge as a Rich :class:`Text` (testable without mounting)."""
        clamped = max(0.0, min(1.0, float(score)))
        b = band or _band_for(clamped)
        filled = int(round(clamped * _BAR_WIDTH))
        empty = _BAR_WIDTH - filled
        style = _BAND_STYLE.get(b, "white")
        out = Text()
        out.append("█" * filled, style=style)
        out.append("░" * empty, style="dim")
        out.append(f"  {clamped:.3f} ", style="bold cyan")
        out.append(b.upper() if b else "?", style=style)
        return out


__all__ = ["ScoreGauge"]
