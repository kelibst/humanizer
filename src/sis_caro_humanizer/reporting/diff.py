"""Coloured unified diff renderer.

Used by the CLI to show what the pipeline did to the text. Returns a Rich
markup string; the CLI is responsible for handing it to a Console.
"""
from __future__ import annotations

import difflib

__all__ = ["render_diff"]


def _escape(line: str) -> str:
    # Rich treats square brackets as markup; escape so diff content survives.
    return line.replace("[", r"\[")


def render_diff(before: str, after: str, *, fromfile: str = "before", tofile: str = "after") -> str:
    """Return a coloured unified diff (Rich markup) of two strings.

    Empty inputs return an empty string. The default ``n=3`` lines of context
    keeps small edits readable without flooding the terminal.
    """
    if before == after:
        return ""
    a = before.splitlines(keepends=False)
    b = after.splitlines(keepends=False)
    diff = difflib.unified_diff(a, b, fromfile=fromfile, tofile=tofile, lineterm="")

    out: list[str] = []
    for line in diff:
        esc = _escape(line)
        if line.startswith("+++") or line.startswith("---"):
            out.append(f"[bold]{esc}[/bold]")
        elif line.startswith("@@"):
            out.append(f"[cyan]{esc}[/cyan]")
        elif line.startswith("+"):
            out.append(f"[green]{esc}[/green]")
        elif line.startswith("-"):
            out.append(f"[red]{esc}[/red]")
        else:
            out.append(esc)
    return "\n".join(out)
