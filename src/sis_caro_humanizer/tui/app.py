"""Top-level Textual app for the humanizer.

Lays out:

* a top tab bar with single-letter shortcuts (P/C/T/G/S)
* a screen-stack-style switcher in the middle (one screen at a time)
* a footer status line showing the active profile, backend, and bridge state

See ``plan/TUI_LAYOUT.md`` §1 for the wireframe and §4 for the key bindings.
"""
from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from ..profile.loader import resolve_profile
from ..profile.schema import Profile
from .screens import (
    CheckScreen,
    GrammarScreen,
    HomeScreen,
    ProfilesScreen,
    SettingsScreen,
    TransformScreen,
)


# Tab shortcut -> (label shown in the tab bar, screen factory keyword)
_TABS: tuple[tuple[str, str, str], ...] = (
    ("p", "P", "rofiles"),
    ("c", "C", "heck"),
    ("t", "T", "ransform"),
    ("g", "G", "rammar"),
    ("s", "S", "ettings"),
)


def _tab_screen_id(letter: str) -> str:
    return f"tab-{letter}"


class HumanizerApp(App):
    """Main TUI entry point.

    Use ``HumanizerApp().run()`` to launch interactively. The app is also
    test-driven via Textual's :class:`textual.pilot.Pilot` harness.
    """

    CSS = """
    #tab-bar {
        height: 1;
        padding: 0 1;
        background: $boost;
    }
    .tab {
        margin-right: 2;
    }
    .tab-active {
        text-style: bold reverse;
    }
    #status-bar {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        background: $boost;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "quit", priority=True),
        Binding("?", "help", "help", priority=True),
        # Numeric tab shortcuts use priority so they fire even when an Input
        # widget on the active screen has focus. The single-letter aliases
        # (p/c/t/g/s) are convenience-only and yield to focused inputs.
        Binding("1", "open_tab('p')", "profiles", priority=True),
        Binding("2", "open_tab('c')", "check", priority=True),
        Binding("3", "open_tab('t')", "transform", priority=True),
        Binding("4", "open_tab('g')", "grammar", priority=True),
        Binding("5", "open_tab('s')", "settings", priority=True),
        Binding("p", "open_tab('p')", "profiles", show=False),
        Binding("c", "open_tab('c')", "check", show=False),
        Binding("t", "open_tab('t')", "transform", show=False),
        Binding("g", "open_tab('g')", "grammar", show=False),
        Binding("s", "open_tab('s')", "settings", show=False),
        Binding("ctrl+r", "refresh", "refresh", show=False),
    ]

    TITLE = "humanizer"
    SUB_TITLE = "local profile-driven AI-detection-evading rewriter"

    def __init__(self, *, profile: Profile | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._profile_name = "default_ghanaian"
        try:
            self._profile: Profile = profile or resolve_profile(self._profile_name)
        except FileNotFoundError:
            # Should not happen — the bundled default ships in the wheel —
            # but we degrade rather than crash.
            self._profile = None  # type: ignore[assignment]
        self._active_tab: str = ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield self._compose_tab_bar()
        yield Container(id="screen-host")
        yield Static(self._status_text(), id="status-bar")
        yield Footer()

    def _compose_tab_bar(self) -> Horizontal:
        bar = Horizontal(id="tab-bar")
        return bar

    async def on_mount(self) -> None:
        # Populate the tab bar lazily so we can attach styled Static widgets.
        bar = self.query_one("#tab-bar", Horizontal)
        for letter, accent, rest in _TABS:
            label = Static(
                Text.assemble(
                    ("[", "dim"),
                    (accent, "bold cyan"),
                    ("]", "dim"),
                    (rest, ""),
                ),
                classes="tab",
                id=f"tab-label-{letter}",
            )
            await bar.mount(label)
        # Default landing screen.
        await self.push_screen(HomeScreen())
        self._active_tab = ""
        self._refresh_status()

    # -- actions -----------------------------------------------------------

    def action_help(self) -> None:
        # Lightweight inline help — replace with an overlay screen later.
        self.notify(
            "Tabs: 1 profiles · 2 check · 3 transform · 4 grammar · 5 settings\n"
            "Ctrl+S = primary action · Ctrl+R refresh · q quit",
            title="humanizer help",
            timeout=8,
        )

    def action_refresh(self) -> None:
        self.notify("refresh", timeout=2)

    def action_open_tab(self, letter: str, *, initial_path: str | None = None) -> None:
        """Switch to one of the lettered tabs.

        Extra keyword args (e.g. ``initial_path`` from the Check screen) are
        passed to the destination screen's constructor where supported.
        """
        screen = self._build_screen(letter, initial_path=initial_path)
        if screen is None:
            return
        # ``switch_screen`` replaces the top of the stack atomically, which
        # avoids a brief intermediate state where the action handler runs
        # before pop completes (and a follow-up shortcut press would race).
        try:
            self.switch_screen(screen)
        except Exception:  # noqa: BLE001 - default-screen edge cases
            self.push_screen(screen)
        self._active_tab = letter
        self._refresh_status()

    # -- routing -----------------------------------------------------------

    def _build_screen(
        self, letter: str, *, initial_path: str | None = None
    ) -> Screen | None:
        if letter == "p":
            return ProfilesScreen()
        if letter == "c":
            return CheckScreen(profile=self._profile)
        if letter == "t":
            return TransformScreen(profile=self._profile, initial_path=initial_path)
        if letter == "g":
            return GrammarScreen(profile=self._profile)
        if letter == "s":
            return SettingsScreen()
        return None

    # -- status bar --------------------------------------------------------

    def _status_text(self) -> Text:
        out = Text()
        out.append("profile: ", style="dim")
        out.append(self._profile_name or "(none)", style="bold")
        out.append("   backend: ", style="dim")
        out.append("ollama (local)", style="bold")
        out.append("   bridge: ", style="dim")
        out.append("off", style="bold yellow")
        if self._active_tab:
            out.append("   tab: ", style="dim")
            out.append(self._active_tab.upper(), style="bold cyan")
        return out

    def _refresh_status(self) -> None:
        try:
            bar = self.query_one("#status-bar", Static)
        except Exception:  # noqa: BLE001 - status bar missing during teardown
            return
        bar.update(self._status_text())

        # Mark the active tab label.
        for letter, _, _ in _TABS:
            try:
                label = self.query_one(f"#tab-label-{letter}", Static)
            except Exception:  # noqa: BLE001
                continue
            if letter == self._active_tab:
                label.add_class("tab-active")
            else:
                label.remove_class("tab-active")


def run() -> None:  # pragma: no cover - convenience runner
    HumanizerApp().run()


__all__ = ["HumanizerApp", "run"]
