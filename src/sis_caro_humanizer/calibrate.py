"""humanize calibrate — interactive calibration wizard (v1.6).

Guides the user through providing human-written and AI-generated sample files,
scores each, and proposes updated calibration anchors for the perplexity
feature (``LOW_PPL`` / ``HIGH_PPL``).  Proposed anchors are written to
``~/.config/humanizer/calibration.toml`` and loaded automatically by the
perplexity feature on the next run.

Usage:
    humanize calibrate
    humanize calibrate --human myessay.txt --ai aiparagraph.txt --profile academic

The wizard is fully non-interactive when ``--human`` and ``--ai`` are both
supplied (CI-friendly).
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .profile.schema import Profile

# ---------------------------------------------------------------------------
# Calibration config file location
# ---------------------------------------------------------------------------

def _calibration_path() -> Path:
    """Return the path to the user-level calibration.toml."""
    from .config import profiles_dir
    p = profiles_dir().parent / "calibration.toml"
    return p


def load_calibration() -> dict[str, float]:
    """Load persisted calibration anchors, or return empty dict if not found."""
    p = _calibration_path()
    if not p.exists():
        return {}
    try:
        import tomllib  # type: ignore[import]
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[import,no-redef]
        except ImportError:
            return {}
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
        return {k: float(v) for k, v in data.items() if isinstance(v, (int, float))}
    except Exception:  # noqa: BLE001
        return {}


def _write_calibration(anchors: dict[str, float]) -> Path:
    """Persist calibration anchors to TOML and return the file path."""
    p = _calibration_path()
    lines = ["# humanize calibrate — auto-generated anchors\n"]
    for k, v in sorted(anchors.items()):
        lines.append(f"{k} = {v:.4f}\n")
    p.write_text("".join(lines), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Core calibration logic (pure, testable, no Rich/Typer)
# ---------------------------------------------------------------------------

def compute_anchors(
    human_xent: list[float],
    ai_xent: list[float],
    *,
    margin: float = 0.3,
) -> dict[str, float]:
    """Derive LOW_PPL and HIGH_PPL calibration anchors from cross-entropy lists.

    ``human_xent`` = mean per-token cross-entropy values for known-human texts.
    ``ai_xent``    = mean per-token cross-entropy values for known-AI texts.

    We pick:
      LOW_PPL  = mean(ai_xent)    − margin   (AI texts have LOW perplexity → high score)
      HIGH_PPL = mean(human_xent) + margin   (Human texts have HIGH perplexity → low score)

    This ensures that:
      - AI text maps to value ≈ 1.0 (HIGH risk)
      - Human text maps to value ≈ 0.0 (LOW risk)

    Both are clamped to a sane range [1.0, 10.0] to avoid edge cases from
    tiny/degenerate corpora.
    """
    if not human_xent or not ai_xent:
        raise ValueError("Need at least one human and one AI sample to calibrate.")

    mean_ai = sum(ai_xent) / len(ai_xent)
    mean_human = sum(human_xent) / len(human_xent)

    low = max(1.0, min(9.0, mean_ai - margin))
    high = max(low + 0.5, min(10.0, mean_human + margin))

    return {"LOW_PPL": round(low, 4), "HIGH_PPL": round(high, 4)}


def _xent_for_file(path: Path, profile: "Profile | None") -> float | None:
    """Score a single file and return its mean cross-entropy (nats), or None."""
    text = path.read_text(encoding="utf-8", errors="replace")
    # Try Ollama logprobs first (fast, high quality), then DistilGPT2 fallback.
    from .scoring.perplexity import _ollama_xent, _distilgpt2_xent  # type: ignore[attr-defined]
    from .config import DEFAULT_MODEL

    model = DEFAULT_MODEL
    if profile is not None:
        model = getattr(profile, "perplexity_model", None) or DEFAULT_MODEL

    xent = _ollama_xent(text, model)
    if xent is None:
        xent = _distilgpt2_xent(text)
    return xent


# ---------------------------------------------------------------------------
# Wizard entry point (called by cli.py::calibrate)
# ---------------------------------------------------------------------------

def run_wizard(
    *,
    human_paths: list[Path],
    ai_paths: list[Path],
    profile: "Profile | None",
    console,  # rich.console.Console — injected by CLI
    dry_run: bool = False,
) -> dict[str, float]:
    """Run the calibration wizard and return the proposed anchor dict.

    If ``dry_run`` is True, the calibration.toml file is NOT written.
    The function always returns the computed anchors.

    This is the testable entry point; the Typer command in cli.py is a thin wrapper.
    """
    import math

    console.print("\n[bold cyan]humanize calibrate[/bold cyan] — perplexity anchor wizard\n")

    # Load current anchors for comparison
    current = load_calibration()
    from .scoring.perplexity import LOW_PPL as _DEFAULT_LOW, HIGH_PPL as _DEFAULT_HIGH
    current_low = current.get("LOW_PPL", _DEFAULT_LOW)
    current_high = current.get("HIGH_PPL", _DEFAULT_HIGH)
    console.print(
        f"Current anchors:  LOW_PPL={current_low:.3f}  HIGH_PPL={current_high:.3f}\n"
    )

    # Score human files
    console.print(f"[bold]Scoring {len(human_paths)} human sample(s)…[/bold]")
    human_xent: list[float] = []
    for p in human_paths:
        console.print(f"  [dim]{p.name}[/dim] ", end="")
        xe = _xent_for_file(p, profile)
        if xe is None:
            console.print("[yellow]perplexity unavailable — skipping[/yellow]")
        else:
            human_xent.append(xe)
            ppl = math.exp(xe) if xe < 50 else float("inf")
            console.print(f"xent={xe:.3f} nats  PPL={ppl:.1f}")

    # Score AI files
    console.print(f"\n[bold]Scoring {len(ai_paths)} AI sample(s)…[/bold]")
    ai_xent: list[float] = []
    for p in ai_paths:
        console.print(f"  [dim]{p.name}[/dim] ", end="")
        xe = _xent_for_file(p, profile)
        if xe is None:
            console.print("[yellow]perplexity unavailable — skipping[/yellow]")
        else:
            ai_xent.append(xe)
            ppl = math.exp(xe) if xe < 50 else float("inf")
            console.print(f"xent={xe:.3f} nats  PPL={ppl:.1f}")

    if not human_xent or not ai_xent:
        console.print(
            "\n[red]Cannot calibrate:[/red] need at least one scoreable human "
            "and one scoreable AI sample. Check that Ollama is running or "
            "that the transformers / DistilGPT2 fallback is available."
        )
        raise SystemExit(1)

    anchors = compute_anchors(human_xent, ai_xent)

    console.print("\n[bold]Proposed anchors:[/bold]")
    _BAND = {"LOW_PPL": "cyan", "HIGH_PPL": "magenta"}
    for k, v in anchors.items():
        delta = v - current.get(k, v)
        delta_str = f" ({delta:+.3f} vs current)" if k in current else " (new)"
        console.print(f"  [{_BAND.get(k,'white')}]{k}[/] = {v:.4f}{delta_str}")

    if not dry_run:
        out = _write_calibration(anchors)
        console.print(f"\n[green]Saved →[/green] {out}")
    else:
        console.print("\n[dim](dry-run: calibration.toml NOT written)[/dim]")

    console.print(
        "\n[dim]Re-run [bold]humanize check[/bold] on your samples to verify the new band assignments.[/dim]\n"
    )
    return anchors


__all__ = [
    "compute_anchors",
    "load_calibration",
    "run_wizard",
    "_calibration_path",
]
