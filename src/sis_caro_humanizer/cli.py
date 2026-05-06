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
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from .config import DEFAULT_MODEL, profile_path, profiles_dir
from .ollama_client import ensure_model, is_running, list_models
from .pipeline.runner import ALL_STAGES, run_pipeline
from .profile.extractor import extract_profile
from .profile.loader import resolve_profile
from .profile.schema import Profile, save_profile
from .reporting.report import render_check, render_grammar, render_transform
from .scoring.risk import ai_risk_score

app = typer.Typer(
    name="humanize",
    help="Local profile-driven humanizer for academic writing.",
    no_args_is_help=False,  # v1.2: bare `humanize` launches the TUI instead.
    add_completion=False,
    invoke_without_command=True,
)

profile_app = typer.Typer(name="profile", help="Manage voice profiles.", no_args_is_help=True)
app.add_typer(profile_app, name="profile")

_console = Console()


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
# helpers
# ---------------------------------------------------------------------------


def _load_profile_or(default: bool, name: str | None) -> Profile:
    """Resolve a profile, falling back to the bundled default."""
    if name:
        try:
            return resolve_profile(name)
        except FileNotFoundError as exc:
            _console.print(f"[red]profile error:[/red] {exc}")
            raise typer.Exit(code=2) from exc
    return resolve_profile("default_ghanaian")


def _read_input(path: Path) -> str:
    if not path.exists():
        _console.print(f"[red]input not found:[/red] {path}")
        raise typer.Exit(code=2)
    if path.suffix.lower() == ".docx":
        try:
            from .docx_bridge import extract_text

            return extract_text(path)
        except ImportError as exc:
            _console.print(f"[red]docx error:[/red] {exc}")
            raise typer.Exit(code=2) from exc
    return path.read_text(encoding="utf-8")


def _to_jsonable(obj: Any) -> Any:
    """Best-effort dataclass / dict / list conversion for JSON output."""
    if is_dataclass(obj):
        return _to_jsonable(asdict(obj))
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    return obj


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
# profile commands
# ---------------------------------------------------------------------------


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
        from .docx_bridge import write_docx

        write_docx(input, result.output, out)
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
# benchmark — local breakdown + optional external detector comparison (v1.4)
# ---------------------------------------------------------------------------


@app.command()
def benchmark(
    input: Path = typer.Argument(..., help="Path to a text file."),
    external: bool = typer.Option(
        False,
        "--external",
        help="Also call public AI-detectors (best-effort, opt-in).",
    ),
    detectors: str = typer.Option(
        "gptzero,sapling,zerogpt",
        "--detectors",
        help="Comma-separated detector names (gptzero, sapling, zerogpt).",
    ),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile name or path."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
) -> None:
    """Score a file's AI-risk and optionally compare with external detectors."""
    import time as _time

    from .scoring.external import (
        DetectorUnavailable,
        KNOWN_DETECTORS,
        get_detector,
    )

    text = _read_input(input)
    prof = _load_profile_or(False, profile)
    report = ai_risk_score(text, prof)

    detector_results: list[dict[str, Any]] = []
    if external:
        names = [d.strip() for d in detectors.split(",") if d.strip()]
        unknown = [n for n in names if n not in KNOWN_DETECTORS]
        if unknown:
            _console.print(
                f"[red]unknown detector(s):[/red] {', '.join(unknown)} "
                f"(known: {', '.join(KNOWN_DETECTORS)})"
            )
            raise typer.Exit(code=2)
        for name in names:
            row: dict[str, Any] = {"detector": name}
            t0 = _time.monotonic()
            try:
                d = get_detector(name)
                # Print URL hit to stderr per CONTRACT §4.3.
                url = getattr(d, "URL", "?")
                Console(stderr=True).print(f"[dim]benchmark: hit {url}[/dim]")
                res = d.detect(text, timeout=8.0)
                row["score"] = res.score
                row["band"] = res.band
                row["confidence"] = res.confidence
                row["elapsed_seconds"] = _time.monotonic() - t0
            except DetectorUnavailable as exc:
                row["error"] = str(exc)
            except Exception as exc:  # noqa: BLE001
                row["error"] = f"internal: {exc}"
            detector_results.append(row)

    if json_out:
        payload = {
            "input_path": str(input),
            "humanizer": _to_jsonable(report),
            "external": detector_results,
        }
        typer.echo(json.dumps(payload, indent=2))
        return

    _console.print(f"\n[bold]Humanizer v1.4 — Benchmark[/bold]")
    _console.print(f"File: {input}")
    _console.print(f"Profile: {getattr(prof, 'profile_name', 'default_ghanaian')}\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Feature")
    table.add_column("Value", justify="right")
    table.add_column("Weight", justify="right")
    for c in report.components:
        table.add_row(c.name, f"{c.value:.2f}", f"{c.weight:.2f}")
    _console.print(table)
    _console.print(
        f"\n[bold]Score:[/bold] {report.score:.3f}    "
        f"[bold]Band:[/bold] {report.band.upper()}\n"
    )

    if external:
        ext_table = Table(title="External detectors", show_header=True, header_style="bold")
        ext_table.add_column("Detector")
        ext_table.add_column("Score", justify="right")
        ext_table.add_column("Band")
        ext_table.add_column("Latency", justify="right")
        for row in detector_results:
            if "error" in row:
                ext_table.add_row(
                    row["detector"],
                    f"(unavailable: {row['error']})",
                    "-",
                    "-",
                )
            else:
                ext_table.add_row(
                    row["detector"],
                    f"{row['score']:.2f}",
                    str(row["band"]).upper(),
                    f"{row['elapsed_seconds']:.2f}s",
                )
        _console.print(ext_table)


# ---------------------------------------------------------------------------
# review-import — accept tracked changes from a lecturer-reviewed DOCX (v1.6)
# ---------------------------------------------------------------------------


@app.command("review-import")
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
    from rich.panel import Panel
    from rich.table import Table

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
