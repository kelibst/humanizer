"""Benchmark sub-command for the humanize CLI (v1.4)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from .cli_utils import _load_profile_or, _read_input, _to_jsonable
from .scoring.risk import ai_risk_score


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

    from .cli import _console
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
