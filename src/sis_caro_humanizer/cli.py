"""Typer CLI for the humanizer.

Subcommands per CONTRACTS.md § 6:

    humanize doctor
    humanize profile create <name> <samples...> [--dialect ...]
    humanize profile show <name>
    humanize profile edit <name>
    humanize profile list
    humanize check <input> [--profile NAME] [--why] [--json]
    humanize transform <input> [-p NAME] [-o OUT] [--model M]
                               [--stages all|llm|determ|grammar]
                               [--seed N] [--json]
    humanize grammar <input> [--profile NAME] [--json]
    humanize calibrate
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from .config import DEFAULT_MODEL
from .ollama_client import ensure_model, is_running, list_models
from .pipeline.runner import ALL_STAGES, run_pipeline
from .reporting.report import render_check, render_grammar, render_transform
from .scoring.risk import ai_risk_score

app = typer.Typer(
    name="humanize",
    help="Local profile-driven humanizer for academic writing.",
    no_args_is_help=False,  # v1.2: bare `humanize` launches the TUI instead.
    add_completion=False,
    invoke_without_command=True,
)

_console = Console()

# ---------------------------------------------------------------------------
# Register sub-apps (imported after app + _console are defined to avoid
# circular-import issues; sub-modules do `from .cli import _console` inside
# their function bodies, not at module level).
# ---------------------------------------------------------------------------

from .cli_profile import profile_app  # noqa: E402
from .cli_benchmark import benchmark  # noqa: E402
from .cli_review import review_import_cmd  # noqa: E402
from .cli_utils import _load_profile_or, _read_input, _to_jsonable  # noqa: E402

app.add_typer(profile_app, name="profile")
app.command()(benchmark)
app.command("review-import")(review_import_cmd)


@app.callback()
def _root(ctx: typer.Context) -> None:
    """Launch the Textual TUI when invoked with no subcommand.

    Subcommands (``humanize check ...``, ``humanize transform ...``, etc.)
    behave exactly as before. Only the bare ``humanize`` invocation changed.
    The flag CLI is preserved for scripting.
    """
    if ctx.invoked_subcommand is not None:
        return
    # Lazy import so `humanize --help` and the subcommands do not pay the
    # textual import cost (and so a missing textual install only bites the
    # bare-launch path, not the rest of the CLI).
    try:
        from .tui.app import HumanizerApp
    except Exception as exc:  # noqa: BLE001
        _console.print(
            "[red]could not start TUI:[/red] "
            f"{exc}\n"
            "[dim]install with `pip install textual>=0.60` or use a subcommand "
            "(see `humanize --help`).[/dim]"
        )
        raise typer.Exit(code=2) from exc
    HumanizerApp().run()


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


@app.command()
def doctor() -> None:
    """Check that all optional integrations are reachable."""
    table = Table(title="humanize doctor", show_lines=False)
    table.add_column("component", style="bold")
    table.add_column("status")
    table.add_column("note")

    def row(name: str, ok: bool, note: str = "") -> None:
        mark = Text("OK", style="bold green") if ok else Text("MISSING", style="bold red")
        table.add_row(name, mark, note)

    ollama_up = is_running()
    row("Ollama daemon", ollama_up, "http://localhost:11434" if ollama_up else "start with `ollama serve`")

    if ollama_up:
        models = list_models()
        has_default = ensure_model(DEFAULT_MODEL)
        row(
            f"model {DEFAULT_MODEL}",
            has_default,
            ", ".join(models[:6]) if models else f"run `ollama pull {DEFAULT_MODEL}`",
        )
    else:
        row(f"model {DEFAULT_MODEL}", False, "(daemon down)")

    java = shutil.which("java")
    row("Java (LanguageTool)", bool(java), java or "install JRE/JDK to enable LanguageTool")

    vale = shutil.which("vale")
    row("vale binary", bool(vale), vale or "install Vale to enable style checks")

    try:
        import proselint  # noqa: F401

        proselint_ok = True
        proselint_note = "import OK"
    except Exception as exc:  # noqa: BLE001
        proselint_ok = False
        proselint_note = f"import failed: {exc}"
    row("proselint", proselint_ok, proselint_note)

    _console.print(table)


# ---------------------------------------------------------------------------
# check / transform / grammar / calibrate
# ---------------------------------------------------------------------------


@app.command()
def check(
    input: Path = typer.Argument(..., help="Path to a text file."),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile name or path."),
    why: bool = typer.Option(False, "--why", help="Show feature breakdown."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
) -> None:
    """Score a file's AI-risk."""
    text = _read_input(input)
    prof = _load_profile_or(False, profile)
    report = ai_risk_score(text, prof)
    if json_out:
        typer.echo(json.dumps(_to_jsonable(report), indent=2))
        return
    render_check(report, console=_console, why=why)


def _parse_stages(value: str) -> tuple[str, ...]:
    raw = [v.strip() for v in value.split(",") if v.strip()]
    if not raw:
        return ALL_STAGES
    if raw == ["all"]:
        return ALL_STAGES
    return tuple(raw)


@app.command()
def transform(
    input: Path = typer.Argument(..., help="Path to a text file."),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile name or path."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Write rewritten text here."),
    model: str | None = typer.Option(None, "--model", help="Override the LLM model."),
    stages: str = typer.Option(
        "all",
        "--stages",
        help="Comma-separated stages: all, llm, determ, grammar, prescan, postscan.",
    ),
    seed: int | None = typer.Option(None, "--seed", help="Deterministic-stage seed."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON summary."),
    show_diff: bool = typer.Option(False, "--diff", help="Show before/after diff."),
) -> None:
    """Run the full pipeline on a file."""
    text = _read_input(input)
    prof = _load_profile_or(False, profile)
    try:
        stage_tuple = _parse_stages(stages)
    except ValueError as exc:
        _console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc

    result = run_pipeline(text, prof, stages=stage_tuple, model=model, seed=seed)

    # Determine effective output path; for .docx input default to <stem>_humanized.docx
    is_docx_input = input.suffix.lower() == ".docx"
    if out is None and is_docx_input:
        out = input.parent / f"{input.stem}_humanized.docx"

    if out is None:
        sys.stdout.write(result.output)
        if not result.output.endswith("\n"):
            sys.stdout.write("\n")
    elif out.suffix.lower() == ".docx":
        if input.suffix.lower() == ".docx":
            from .docx_bridge import write_docx

            write_docx(input, result.output, out)
        else:
            from .docx_bridge import new_docx_from_markdown

            new_docx_from_markdown(result.output, out)
        Console(stderr=True).print(f"[green]saved[/green] {out}")
    else:
        out.write_text(result.output, encoding="utf-8")

    if json_out:
        payload = {
            "input_path": str(input),
            "output_path": str(out) if out else None,
            "pre_score": _to_jsonable(result.pre_score),
            "post_score": _to_jsonable(result.post_score),
            "llm_used": result.llm_used,
            "deterministic_count": len(result.deterministic_log),
            "grammar_active": (
                None
                if result.grammar is None
                else sum(1 for i in result.grammar.issues if not i.suppressed)
            ),
            "elapsed_seconds": result.elapsed_seconds,
            "notes": result.notes,
        }
        # JSON to stderr if we already piped output to stdout, else stdout.
        stream = sys.stderr if out is None else sys.stdout
        stream.write(json.dumps(payload, indent=2) + "\n")
    else:
        # Render summary to stderr so stdout stays clean for piping.
        summary_console = Console(stderr=True) if out is None else _console
        render_transform(result, show_diff=show_diff, console=summary_console)
        for note in result.notes:
            summary_console.print(f"[yellow]note:[/yellow] {note}")


@app.command()
def grammar(
    input: Path = typer.Argument(..., help="Path to a text file."),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile name or path."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Run only the grammar pass and print issues."""
    text = _read_input(input)
    prof = _load_profile_or(False, profile)
    from .grammar.runner import run_grammar

    report = run_grammar(text, prof)
    if json_out:
        typer.echo(json.dumps(_to_jsonable(report), indent=2))
        return
    render_grammar(report, console=_console)


@app.command()
def calibrate() -> None:
    """Reserved for v0.2."""
    _console.print("calibrate not implemented in v0.1")
    raise typer.Exit(code=0)


# ---------------------------------------------------------------------------
# serve — local HTTPS bridge daemon (v1.2)
# ---------------------------------------------------------------------------


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address (loopback by default)."),
    port: int = typer.Option(9999, "--port", help="TCP port."),
    no_tls: bool = typer.Option(
        False,
        "--no-tls",
        help="Disable TLS (local debugging only; the Docs sidebar refuses non-TLS).",
    ),
    rotate_token: bool = typer.Option(
        False,
        "--rotate-token",
        help="Generate a fresh bearer token instead of reusing the persisted one.",
    ),
    rotate_cert: bool = typer.Option(
        False,
        "--rotate-cert",
        help="Generate a fresh self-signed cert/key pair.",
    ),
) -> None:
    """Run the local bridge daemon for the Google Docs add-in.

    Prints the bearer token and cert path to stderr at startup, then blocks on
    uvicorn until SIGINT.
    """
    from .serve.runner import serve as _serve

    _serve(
        host=host,
        port=port,
        tls=not no_tls,
        rotate_token=rotate_token,
        rotate_cert=rotate_cert,
    )


def main() -> None:  # pragma: no cover - entry point
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
