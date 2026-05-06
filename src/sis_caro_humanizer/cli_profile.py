"""Profile sub-commands for the humanize CLI."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import typer
from rich.syntax import Syntax
from rich.table import Table

from .config import profile_path, profiles_dir
from .profile.extractor import extract_profile
from .profile.loader import resolve_profile
from .profile.schema import save_profile

profile_app = typer.Typer(name="profile", help="Manage voice profiles.", no_args_is_help=True)


@profile_app.command("create")
def profile_create(
    name: str = typer.Argument(..., help="Name to save the profile under."),
    samples: list[Path] = typer.Argument(..., exists=True, readable=True, help="Sample text files."),
    dialect: str = typer.Option(
        "ghanaian",
        "--dialect",
        help="Dialect tag for the profile.",
        show_default=True,
    ),
) -> None:
    """Build a profile from one or more sample files and save it."""
    from .cli import _console

    if dialect not in {"ghanaian", "british", "american", "neutral"}:
        _console.print(f"[red]bad --dialect:[/red] {dialect}")
        raise typer.Exit(code=2)
    profile = extract_profile(name, [Path(s) for s in samples], dialect=dialect)
    out = profile_path(name)
    save_profile(profile, out)
    _console.print(f"[green]saved[/green] {out}")
    _console.print(
        f"  basis: {profile.word_count_basis} words from {len(profile.extracted_from)} file(s)"
    )
    _console.print(
        f"  mean sentence length: {profile.sentence_shape.mean_words:.1f} words "
        f"(short<10: {profile.sentence_shape.pct_short_lt10:.0%}, "
        f"long>35: {profile.sentence_shape.pct_long_gt35:.0%})"
    )


@profile_app.command("show")
def profile_show(name: str = typer.Argument(..., help="Profile name or path.")) -> None:
    """Pretty-print a profile YAML."""
    from .cli import _console

    try:
        profile = resolve_profile(name)
    except FileNotFoundError as exc:
        _console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    import yaml

    payload = profile.model_dump(mode="json", exclude_none=True)
    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    _console.print(Syntax(text, "yaml", theme="ansi_dark", word_wrap=True))


@profile_app.command("edit")
def profile_edit(name: str = typer.Argument(..., help="Profile name.")) -> None:
    """Open the profile's YAML file in $EDITOR."""
    from .cli import _console

    target = profile_path(name)
    if not target.exists():
        _console.print(f"[red]profile not found:[/red] {target}")
        raise typer.Exit(code=2)
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vi"
    cmd = editor.split() + [str(target)]
    try:
        rc = subprocess.call(cmd)
    except FileNotFoundError as exc:
        _console.print(f"[red]editor {editor!r} not found:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    raise typer.Exit(code=rc)


@profile_app.command("list")
def profile_list() -> None:
    """List profile files under the user config dir."""
    from .cli import _console

    pdir = profiles_dir()
    rows = sorted(p.stem for p in pdir.glob("*.yaml"))
    if not rows:
        _console.print(f"[dim]no profiles in {pdir}[/dim]")
        _console.print("[dim]bundled fallback: 'default_ghanaian'[/dim]")
        return
    table = Table(title=f"profiles in {pdir}")
    table.add_column("name", style="bold")
    for r in rows:
        table.add_row(r)
    _console.print(table)
