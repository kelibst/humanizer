"""Rich-based renderers for the CLI commands.

The library code in :mod:`sis_caro_humanizer.pipeline` and ``scoring`` never
prints. Anything the user sees on stdout flows through here.
"""
from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..scoring.risk import ScoreReport
from .diff import render_diff

if TYPE_CHECKING:  # pragma: no cover
    from ..pipeline.runner import PipelineResult

__all__ = ["render_check", "render_transform", "render_grammar"]

_BAND_STYLE = {
    "low": "bold green",
    "medium": "bold yellow",
    "high": "bold red",
}


def _band_text(band: str) -> Text:
    return Text(band.upper(), style=_BAND_STYLE.get(band, "bold"))


def render_check(report: ScoreReport, *, console: Console | None = None, why: bool = False) -> None:
    """Pretty-print an :class:`ScoreReport`. Set ``why=True`` to include the
    full feature breakdown table."""
    cons = console or Console()
    band = _band_text(report.band)
    summary = Text.assemble(
        ("AI-risk score: ", "bold"),
        (f"{report.score:.3f}", "bold cyan"),
        ("    band: ", "bold"),
        band,
        ("    weighted sum: ", "dim"),
        (f"{report.raw_weighted_sum:.3f}", "dim"),
    )
    cons.print(Panel(summary, title="check", expand=False))

    if why:
        table = Table(title="feature contributions", show_lines=False)
        table.add_column("feature", style="bold")
        table.add_column("value", justify="right")
        table.add_column("weight", justify="right")
        table.add_column("contribution", justify="right")
        table.add_column("detail")
        for c in sorted(report.components, key=lambda x: x.value * x.weight, reverse=True):
            contribution = c.value * c.weight
            table.add_row(
                c.name,
                f"{c.value:.2f}",
                f"{c.weight:.2f}",
                f"{contribution:.3f}",
                c.detail,
            )
        cons.print(table)
        # Top examples per feature, two lines apiece.
        for c in report.components:
            if c.examples:
                cons.print(f"  [dim]{c.name}[/dim]: " + " | ".join(c.examples[:3]))


def render_grammar(grammar, *, console: Console | None = None) -> None:
    """Render a :class:`GrammarReport`. Imported lazily to avoid a hard
    dependency on the grammar subsystem at module import time."""
    cons = console or Console()
    if grammar is None:
        cons.print("[yellow]grammar stage was not run.[/yellow]")
        return

    status_table = Table(title="grammar tools")
    status_table.add_column("tool", style="bold")
    status_table.add_column("status")
    for tool, status in grammar.tool_status.items():
        style = {"ok": "green", "missing": "yellow", "skipped": "dim", "error": "red"}.get(
            status, "white"
        )
        status_table.add_row(tool, Text(status, style=style))
    cons.print(status_table)

    active = [i for i in grammar.issues if not i.suppressed]
    suppressed = [i for i in grammar.issues if i.suppressed]
    cons.print(
        f"[bold]{len(active)}[/bold] active issue(s); "
        f"[dim]{len(suppressed)} suppressed by profile[/dim]"
    )
    if not active:
        return

    table = Table(show_lines=False)
    table.add_column("tool", style="cyan")
    table.add_column("rule", style="magenta")
    table.add_column("offset", justify="right")
    table.add_column("message")
    for issue in active[:50]:
        table.add_row(
            issue.tool,
            issue.rule_id or "-",
            str(issue.offset),
            issue.message,
        )
    cons.print(table)
    if len(active) > 50:
        cons.print(f"[dim]... and {len(active) - 50} more[/dim]")


def render_transform(
    result: "PipelineResult",
    *,
    show_diff: bool = False,
    console: Console | None = None,
) -> None:
    """Render the outcome of ``run_pipeline``."""
    cons = console or Console()

    pre = result.pre_score
    post = result.post_score
    delta = post.score - pre.score
    delta_style = "green" if delta < 0 else ("red" if delta > 0 else "white")
    summary = Text.assemble(
        ("score before: ", "bold"),
        (f"{pre.score:.3f}", "bold cyan"),
        (f" ({pre.band})", _BAND_STYLE.get(pre.band, "white")),
        ("    after: ", "bold"),
        (f"{post.score:.3f}", "bold cyan"),
        (f" ({post.band})", _BAND_STYLE.get(post.band, "white")),
        ("    delta: ", "bold"),
        (f"{delta:+.3f}", delta_style),
        ("    elapsed: ", "dim"),
        (f"{result.elapsed_seconds:.2f}s", "dim"),
        ("    llm: ", "dim"),
        ("yes" if result.llm_used else "no", "dim"),
    )
    cons.print(Panel(summary, title="transform", expand=False))

    # Top deterministic transforms by count.
    if result.deterministic_log:
        counter: Counter[str] = Counter(getattr(t, "transform", str(t)) for t in result.deterministic_log)
        table = Table(title="deterministic edits")
        table.add_column("transform", style="bold")
        table.add_column("count", justify="right")
        for name, count in counter.most_common():
            table.add_row(name, str(count))
        cons.print(table)
    elif result.notes:
        for note in result.notes:
            cons.print(f"[yellow]note:[/yellow] {note}")

    if result.grammar is not None:
        render_grammar(result.grammar, console=cons)

    if show_diff:
        diff = render_diff(result.input, result.output)
        if diff:
            cons.print(Panel(diff, title="diff", expand=True))
        else:
            cons.print("[dim]no textual change.[/dim]")
