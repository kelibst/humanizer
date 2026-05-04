"""Home screen: landing menu (TUI_LAYOUT.md §2.1).

Six entries, each routing to one of the other screens. Uses arrow keys to
navigate and Enter to select; the routing happens by setting the App's
active screen, not by ``push_screen`` (we keep the main app in
single-screen-at-a-time mode so the top tab bar stays consistent).
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import Label, ListItem, ListView, Static

# (label, target tab id) — tab ids are the single-letter shortcuts the App
# knows about (see ``HumanizerApp.action_open_tab``).
HOME_ENTRIES: tuple[tuple[str, str], ...] = (
    ("check a document for AI-detector risk", "c"),
    ("transform a document (rewrite it)", "t"),
    ("run a grammar pass", "g"),
    ("manage profiles", "p"),
    ("start the docs bridge daemon", "s"),
    ("settings", "s"),
)


class HomeScreen(Screen):
    """Landing screen with an arrow-key menu."""

    BINDINGS = [
        Binding("enter", "select", "select"),
    ]

    DEFAULT_CSS = """
    HomeScreen {
        align: center middle;
    }
    #home-card {
        width: 70%;
        height: auto;
        border: round $primary;
        padding: 1 2;
    }
    #home-title {
        text-style: bold;
        margin-bottom: 1;
    }
    #home-list {
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="home-card"):
            yield Static("welcome to humanizer — what would you like to do?", id="home-title")
            yield ListView(
                *(ListItem(Label(text), id=f"entry-{i}") for i, (text, _) in enumerate(HOME_ENTRIES)),
                id="home-list",
            )
            yield Static(
                "↑/↓ navigate · enter select · q quit · 1-5 jump to tab",
                id="home-hint",
            )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx_str = (event.item.id or "").removeprefix("entry-")
        try:
            idx = int(idx_str)
        except ValueError:
            return
        _, target = HOME_ENTRIES[idx]
        self.app.action_open_tab(target)  # type: ignore[attr-defined]

    def action_select(self) -> None:
        # Fallback if Enter falls through.
        listview = self.query_one(ListView)
        if listview.highlighted_child is not None:
            listview.action_select_cursor()


__all__ = ["HomeScreen", "HOME_ENTRIES"]
