"""Profiles screen (TUI_LAYOUT.md §2.5).

Two-column layout: list of profile names on the left, detail pane on the
right. Profile authoring (the "create new" wizard) intentionally degrades
to a stub message in v1.2 round 1 — `humanize profile create` already
exists for that, so the TUI surface for new profiles can be expanded in a
later round without blocking shipping.
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Label, ListItem, ListView, Static

from ...config import profiles_dir
from ...profile.loader import BUNDLED_DEFAULT, resolve_profile
from ...profile.schema import Profile


def _list_profile_names() -> list[str]:
    """Return all profile names visible to the user."""
    names: list[str] = []
    pdir = profiles_dir()
    for path in sorted(pdir.glob("*.yaml")):
        names.append(path.stem)
    if "default_ghanaian" not in names:
        names.insert(0, "default_ghanaian")
    return names


class ProfilesScreen(Screen):
    """List + detail view for profiles."""

    BINDINGS = [Binding("enter", "open", "open")]

    DEFAULT_CSS = """
    ProfilesScreen {
        layout: horizontal;
        padding: 1 2;
    }
    #p-list-col {
        width: 30;
        border: round $primary;
        padding: 0 1;
    }
    #p-detail-col {
        width: 1fr;
        border: round $primary;
        padding: 0 1;
        margin-left: 1;
    }
    #p-detail-body {
        height: auto;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._names: list[str] = _list_profile_names()

    def compose(self) -> ComposeResult:
        with Vertical(id="p-list-col"):
            yield Static("[bold]profiles[/bold]")
            items: list[ListItem] = []
            for i, name in enumerate(self._names):
                items.append(ListItem(Label(name), id=f"p-{i}"))
            items.append(ListItem(Label("[+ create new]"), id="p-new"))
            yield ListView(*items, id="p-list")
        with Vertical(id="p-detail-col"):
            yield Static("[bold]profile detail[/bold]", id="p-detail-title")
            yield Static(
                "(select a profile on the left)",
                id="p-detail-body",
            )

    def on_mount(self) -> None:
        if self._names:
            self._show_detail(self._names[0])

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        item = event.item
        if item is None:
            return
        item_id = item.id or ""
        if item_id == "p-new":
            self._show_create_stub()
            return
        try:
            idx = int(item_id.removeprefix("p-"))
        except ValueError:
            return
        if 0 <= idx < len(self._names):
            self._show_detail(self._names[idx])

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        # Same routing as highlight; included for completeness.
        self.on_list_view_highlighted(
            ListView.Highlighted(self.query_one(ListView), event.item)  # type: ignore[arg-type]
        )

    def _show_create_stub(self) -> None:
        body = self.query_one("#p-detail-body", Static)
        msg = Text()
        msg.append("Create a new profile from sample text via the CLI:\n\n", style="bold")
        msg.append(
            "  humanize profile create <name> <sample.md> [...]\n\n",
            style="green",
        )
        msg.append(
            "(A full TUI wizard is planned for a later round.)",
            style="dim",
        )
        body.update(msg)

    def _show_detail(self, name: str) -> None:
        body = self.query_one("#p-detail-body", Static)
        try:
            profile = resolve_profile(name)
        except FileNotFoundError as exc:
            body.update(Text(f"could not load profile: {exc}", style="red"))
            return
        body.update(self._format_profile(profile, name))

    @staticmethod
    def _format_profile(profile: Profile, name: str) -> Text:
        out = Text()
        out.append(f"name        ", style="bold")
        out.append(f"{name}\n", style="cyan")
        out.append(f"dialect     ", style="bold")
        out.append(f"{profile.dialect}\n")
        out.append(f"register    ", style="bold")
        out.append(f"{profile.domain_register}\n")
        out.append(f"mean words  ", style="bold")
        out.append(
            f"{profile.sentence_shape.mean_words:.1f}    σ {profile.sentence_shape.std_words:.1f}\n"
        )
        if profile.vocabulary.never_use:
            out.append("never use   ", style="bold")
            out.append(", ".join(profile.vocabulary.never_use[:8]) + "\n")
        out.append("\nblupper rates:\n", style="bold")
        bp = profile.blupper_probabilities
        for field, value in (
            ("data_singular_verb", bp.data_singular_verb),
            ("less_for_fewer", bp.less_for_fewer),
            ("which_for_that", bp.which_for_that),
            ("comma_splice_rate", bp.comma_splice_rate),
            ("oxford_comma_rate", bp.oxford_comma_rate),
            ("start_with_and_but", bp.start_with_and_but),
            ("article_drop_ghanaian", bp.article_drop_ghanaian),
        ):
            out.append(f"  {field:<24}", style="dim")
            out.append(f"{value:.2f}\n")
        out.append("\nrisk target ", style="bold")
        out.append(f"{profile.risk_target:.2f}\n")
        return out


__all__ = ["ProfilesScreen"]
