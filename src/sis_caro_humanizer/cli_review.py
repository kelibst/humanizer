"""Review-import sub-command for the humanize CLI (v1.6)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from .cli_utils import _load_profile_or
from .pipeline.runner import run_pipeline
from .scoring.risk import ai_risk_score


def review_import_cmd(
    reviewed_docx: Path = typer.Argument(..., help="Lecturer-reviewed .docx file"),
    original: Optional[Path] = typer.Option(
        None, "--original", "-i", help="Original markdown source"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Voice profile name"
    ),
) -> None:
    """Import a lecturer-reviewed .docx: accept tracked changes, show diff and comments."""
    from .cli import _console

    try:
        from .docx_bridge import (
            accept_tracked_changes,
            diff_text_sections,
            extract_word_comments,
        )
    except ImportError as exc:
        _console.print(f"[red]docx error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    if not reviewed_docx.exists():
        _console.print(f"[red]file not found:[/red] {reviewed_docx}")
        raise typer.Exit(code=2)

    try:
        accepted = accept_tracked_changes(reviewed_docx)
    except Exception as exc:  # noqa: BLE001
        _console.print(f"[red]failed to parse docx:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    try:
        comments = extract_word_comments(reviewed_docx)
    except Exception:  # noqa: BLE001
        comments = []

    # --- Accepted text preview ---
    preview = accepted[:400] + ("…" if len(accepted) > 400 else "")
    _console.print(Panel(preview, title="Accepted Text Preview", expand=False))

    # --- Diff sections ---
    sections = None
    if original is not None:
        if not original.exists():
            _console.print(f"[red]original not found:[/red] {original}")
            raise typer.Exit(code=2)
        original_text = original.read_text(encoding="utf-8")
        sections = diff_text_sections(original_text, accepted)

        diff_table = Table(title="Changed Sections")
        diff_table.add_column("Para #", justify="right")
        diff_table.add_column("Changed")
        diff_table.add_column("Original (50 chars)")
        diff_table.add_column("Revised (50 chars)")
        for sec in sections:
            mark = "[red]YES[/red]" if sec["changed"] else "[dim]no[/dim]"
            diff_table.add_row(
                str(sec["paragraph_idx"]),
                mark,
                (sec["original"] or "")[:50],
                (sec["revised"] or "")[:50],
            )
        _console.print(diff_table)

    # --- Comments ---
    if comments:
        comments_text = "\n".join(
            f"[bold]{c['author']}[/bold] (para {c['paragraph_idx']}): {c['text']}"
            for c in comments
        )
        _console.print(Panel(comments_text, title="Reviewer Comments", expand=False))

    # --- Post-import score ---
    prof = _load_profile_or(False, profile)
    report = ai_risk_score(accepted, prof)
    band_colour = {"low": "green", "medium": "yellow", "high": "red"}.get(
        report.band, "white"
    )
    _console.print(
        f"Post-import score: [{band_colour}]{report.score:.2f} ({report.band.upper()})[/{band_colour}]"
    )

    # --- Re-humanize changed sections? ---
    if sections and any(s["changed"] for s in sections):
        if typer.confirm("Re-humanize changed sections?", default=False):
            changed_revised = [
                s["revised"] for s in sections if s["changed"] and s["revised"]
            ]
            reassembled_parts: list[str] = []
            for para_text in changed_revised:
                result = run_pipeline(para_text, prof, stages=("prescan", "determ", "postscan"))
                reassembled_parts.append(result.output)
            reassembled = "\n\n".join(reassembled_parts)
            _console.print(Panel(reassembled, title="Re-humanized Changed Sections", expand=False))
