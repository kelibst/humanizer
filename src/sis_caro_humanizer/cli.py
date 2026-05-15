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
from .scoring.external import KNOWN_DETECTORS
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

    # --- External AI detectors (optional; used by `humanize check --external`) ---
    import os
    _DETECTOR_KEYS = {
        "GPTZero": "GPTZERO_API_KEY",
        "Sapling": "SAPLING_API_KEY",
        "ZeroGPT": "ZEROGPT_API_KEY",
    }
    for display_name, env_var in _DETECTOR_KEYS.items():
        key_set = bool(os.environ.get(env_var, "").strip())
        # GPTZero has a keyless free tier; the others require a key.
        if display_name == "GPTZero":
            note = env_var if key_set else f"{env_var} not set (keyless free tier still works)"
            row(f"{display_name} (external)", True, note)
        else:
            row(
                f"{display_name} (external)",
                key_set,
                env_var if key_set else f"set {env_var} to enable",
            )

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
    external: bool = typer.Option(
        False,
        "--external",
        help="Also call public AI-detectors (best-effort, opt-in). Useful to cross-validate the internal score.",
    ),
    detectors: str = typer.Option(
        ",".join(KNOWN_DETECTORS),
        "--detectors",
        help="Comma-separated detector names (gptzero, sapling, zerogpt).",
    ),
) -> None:
    """Score a file's AI-risk.

    Use --external to cross-validate against online detectors (GPTZero,
    Sapling, ZeroGPT). GPTZero works without an API key (rate-limited);
    the others need their env-var keys set (see `humanize doctor`).
    """
    import time as _time
    from .scoring.external import DetectorUnavailable, get_detector

    text = _read_input(input)
    prof = _load_profile_or(False, profile)
    report = ai_risk_score(text, prof)

    # Check if perplexity was unavailable and warn the user (stderr so JSON stays clean).
    _stderr = Console(stderr=True)
    for c in report.components:
        if c.name == "perplexity" and "perplexity_unavailable" in c.examples:
            _stderr.print(
                "[yellow]warning:[/yellow] perplexity feature unavailable "
                "(Ollama not running / DistilGPT2 not installed). "
                "Score may be under-estimated. Run [bold]humanize doctor[/bold] for details."
            )
            break

    if json_out and not external:
        typer.echo(json.dumps(_to_jsonable(report), indent=2))
        return
    if not external:
        render_check(report, console=_console, why=why)
        return

    # --- External cross-validation ---
    names = [d.strip() for d in detectors.split(",") if d.strip()]
    unknown = [n for n in names if n not in KNOWN_DETECTORS]
    if unknown:
        _console.print(
            f"[red]unknown detector(s):[/red] {', '.join(unknown)} "
            f"(known: {', '.join(KNOWN_DETECTORS)})"
        )
        raise typer.Exit(code=2)

    from rich.table import Table as _Table
    from rich.text import Text as _Text

    _BAND_STYLE = {"low": "bold green", "medium": "bold yellow", "high": "bold red"}

    ext_rows: list[dict] = []
    for name in names:
        row_data: dict = {"detector": name}
        t0 = _time.monotonic()
        try:
            det = get_detector(name)
            url = getattr(det, "URL", "?")
            Console(stderr=True).print(f"[dim]check: querying {url} …[/dim]")
            res = det.detect(text, timeout=8.0)
            row_data["score"] = res.score
            row_data["band"] = res.band
            row_data["elapsed"] = _time.monotonic() - t0
        except DetectorUnavailable as exc:
            row_data["error"] = str(exc)
        except Exception as exc:  # noqa: BLE001
            row_data["error"] = f"internal: {exc}"
        ext_rows.append(row_data)

    if json_out:
        payload = {
            "input_path": str(input),
            "humanizer": _to_jsonable(report),
            "external": ext_rows,
        }
        typer.echo(json.dumps(payload, indent=2))
        return

    # Render internal score first.
    render_check(report, console=_console, why=why)

    # Then render the cross-validation table.
    tbl = _Table(title="External AI-detector comparison", show_header=True, header_style="bold")
    tbl.add_column("Detector")
    tbl.add_column("Score", justify="right")
    tbl.add_column("Band")
    tbl.add_column("Latency", justify="right")

    # Humanizer internal row first.
    tbl.add_row(
        "humanizer (internal)",
        f"{report.score:.3f}",
        _Text(report.band.upper(), style=_BAND_STYLE.get(report.band, "bold")),
        "–",
    )
    for row_data in ext_rows:
        if "error" in row_data:
            tbl.add_row(
                row_data["detector"],
                f"(unavailable: {row_data['error']})",
                "–",
                "–",
            )
        else:
            band = row_data["band"]
            tbl.add_row(
                row_data["detector"],
                f"{row_data['score']:.3f}",
                _Text(band.upper(), style=_BAND_STYLE.get(band, "bold")),
                f"{row_data['elapsed']:.2f}s",
            )
    _console.print(tbl)


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
def calibrate(
    human: list[Path] = typer.Option(
        None,
        "--human",
        help="Path to a known-human-written text file. Repeat for multiple files.",
    ),
    ai: list[Path] = typer.Option(
        None,
        "--ai",
        help="Path to a known-AI-generated text file. Repeat for multiple files.",
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile name or path."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Compute anchors but do NOT write calibration.toml."
    ),
) -> None:
    """Calibrate perplexity scoring anchors from your own sample files.

    Provide at least one --human and one --ai file.  The wizard scores each
    file and proposes updated LOW_PPL / HIGH_PPL anchors that it writes to
    ~/.config/humanizer/calibration.toml.  Those anchors are loaded
    automatically by `humanize check` on the next run.

    When run with no arguments, the wizard prompts you interactively.
    """
    from .calibrate import run_wizard

    human_paths = list(human or [])
    ai_paths = list(ai or [])

    # Interactive prompting when no files provided
    if not human_paths:
        _console.print(
            "[bold]No --human file provided.[/bold] Enter the path to one or more "
            "human-written text files, one per line. Press Enter on a blank line when done."
        )
        while True:
            raw = input("  human file> ").strip()
            if not raw:
                break
            p = Path(raw)
            if not p.exists():
                _console.print(f"[red]File not found:[/red] {p}")
            else:
                human_paths.append(p)

    if not ai_paths:
        _console.print(
            "[bold]No --ai file provided.[/bold] Enter the path to one or more "
            "AI-generated text files, one per line. Press Enter on a blank line when done."
        )
        while True:
            raw = input("  AI file> ").strip()
            if not raw:
                break
            p = Path(raw)
            if not p.exists():
                _console.print(f"[red]File not found:[/red] {p}")
            else:
                ai_paths.append(p)

    if not human_paths or not ai_paths:
        _console.print(
            "[red]Calibration requires at least one human and one AI sample.[/red]\n"
            "Usage: humanize calibrate --human myessay.txt --ai aiparagraph.txt"
        )
        raise typer.Exit(code=2)

    # Validate that all files exist
    for p in human_paths + ai_paths:
        if not p.exists():
            _console.print(f"[red]File not found:[/red] {p}")
            raise typer.Exit(code=2)

    prof = _load_profile_or(False, profile)

    run_wizard(
        human_paths=human_paths,
        ai_paths=ai_paths,
        profile=prof,
        console=_console,
        dry_run=dry_run,
    )


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
