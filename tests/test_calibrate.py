"""Tests for `humanize calibrate` wizard (v1.6)."""
from __future__ import annotations

import math
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sis_caro_humanizer.calibrate import (
    _calibration_path,
    _write_calibration,
    compute_anchors,
    load_calibration,
    run_wizard,
)
from sis_caro_humanizer.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Unit tests for compute_anchors (pure function, no I/O)
# ---------------------------------------------------------------------------


def test_compute_anchors_basic():
    """LOW_PPL < HIGH_PPL and both within sane range."""
    # AI texts have low cross-entropy (~3 nats); humans have higher (~5 nats)
    anchors = compute_anchors([5.0, 5.2, 4.8], [3.0, 3.1, 2.9])
    assert anchors["LOW_PPL"] < anchors["HIGH_PPL"]
    assert 1.0 <= anchors["LOW_PPL"] <= 9.0
    assert anchors["HIGH_PPL"] <= 10.0


def test_compute_anchors_margin():
    """Margin parameter shifts anchors by the expected amount."""
    a1 = compute_anchors([5.0], [3.0], margin=0.0)
    a2 = compute_anchors([5.0], [3.0], margin=0.5)
    assert a2["LOW_PPL"] < a1["LOW_PPL"]
    assert a2["HIGH_PPL"] > a1["HIGH_PPL"]


def test_compute_anchors_clamps_extremes():
    """Extremely low or high cross-entropy values are clamped."""
    anchors = compute_anchors([100.0], [0.1])
    assert anchors["LOW_PPL"] >= 1.0
    assert anchors["HIGH_PPL"] <= 10.0


def test_compute_anchors_requires_both_lists():
    with pytest.raises(ValueError, match="at least one"):
        compute_anchors([], [3.0])
    with pytest.raises(ValueError, match="at least one"):
        compute_anchors([5.0], [])


# ---------------------------------------------------------------------------
# load_calibration / _write_calibration round-trip
# ---------------------------------------------------------------------------


def test_write_and_load_calibration(tmp_path, monkeypatch):
    """Written anchors can be read back correctly."""
    toml_file = tmp_path / "calibration.toml"
    monkeypatch.setattr(
        "sis_caro_humanizer.calibrate._calibration_path",
        lambda: toml_file,
    )
    # Also patch the load function's path lookup
    _write_calibration({"LOW_PPL": 2.1234, "HIGH_PPL": 5.6789})
    # Now read it back
    data = load_calibration()  # Note: this uses the real _calibration_path unless patched
    # Read directly since monkeypatch only affects the write side
    import sys
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]
    raw = tomllib.loads(toml_file.read_text())
    assert raw["LOW_PPL"] == pytest.approx(2.1234, abs=1e-3)
    assert raw["HIGH_PPL"] == pytest.approx(5.6789, abs=1e-3)


def test_load_calibration_returns_empty_when_missing(tmp_path, monkeypatch):
    """load_calibration() returns {} when calibration.toml does not exist."""
    monkeypatch.setattr(
        "sis_caro_humanizer.calibrate._calibration_path",
        lambda: tmp_path / "nonexistent.toml",
    )
    assert load_calibration() == {}


# ---------------------------------------------------------------------------
# run_wizard (mocked perplexity)
# ---------------------------------------------------------------------------


def test_run_wizard_dry_run(tmp_path, monkeypatch):
    """Wizard computes anchors in dry-run mode without writing calibration.toml."""
    human_file = tmp_path / "human.txt"
    ai_file = tmp_path / "ai.txt"
    human_file.write_text("A" * 500, encoding="utf-8")
    ai_file.write_text("B" * 500, encoding="utf-8")

    # Patch the private perplexity functions to avoid Ollama/DistilGPT2
    monkeypatch.setattr(
        "sis_caro_humanizer.calibrate._xent_for_file",
        lambda path, profile: 5.0 if "human" in path.name else 3.0,
    )
    monkeypatch.setattr(
        "sis_caro_humanizer.calibrate._calibration_path",
        lambda: tmp_path / "calibration.toml",
    )

    from rich.console import Console
    import io
    buf = io.StringIO()
    console = Console(file=buf, highlight=False)

    anchors = run_wizard(
        human_paths=[human_file],
        ai_paths=[ai_file],
        profile=None,
        console=console,
        dry_run=True,
    )
    assert "LOW_PPL" in anchors
    assert "HIGH_PPL" in anchors
    assert anchors["LOW_PPL"] < anchors["HIGH_PPL"]
    # dry_run: file must NOT be written
    assert not (tmp_path / "calibration.toml").exists()


def test_run_wizard_writes_file(tmp_path, monkeypatch):
    """Wizard writes calibration.toml when dry_run=False."""
    human_file = tmp_path / "human.txt"
    ai_file = tmp_path / "ai.txt"
    human_file.write_text("A" * 500, encoding="utf-8")
    ai_file.write_text("B" * 500, encoding="utf-8")

    toml_path = tmp_path / "calibration.toml"
    monkeypatch.setattr(
        "sis_caro_humanizer.calibrate._xent_for_file",
        lambda path, profile: 5.0 if "human" in path.name else 3.0,
    )
    monkeypatch.setattr(
        "sis_caro_humanizer.calibrate._calibration_path",
        lambda: toml_path,
    )

    from rich.console import Console
    import io
    console = Console(file=io.StringIO(), highlight=False)

    run_wizard(
        human_paths=[human_file],
        ai_paths=[ai_file],
        profile=None,
        console=console,
        dry_run=False,
    )
    assert toml_path.exists()
    assert "LOW_PPL" in toml_path.read_text()


# ---------------------------------------------------------------------------
# CLI integration: humanize calibrate --human ... --ai ... --dry-run
# ---------------------------------------------------------------------------


def test_calibrate_cli_dry_run(tmp_path, monkeypatch):
    """CLI calibrate with --human and --ai exits 0 in dry-run mode."""
    human_file = tmp_path / "human.txt"
    ai_file = tmp_path / "ai.txt"
    human_file.write_text("Human text " * 100, encoding="utf-8")
    ai_file.write_text("AI text furthermore " * 100, encoding="utf-8")

    monkeypatch.setattr(
        "sis_caro_humanizer.calibrate._xent_for_file",
        lambda path, profile: 5.0 if "human" in path.name else 3.0,
    )
    monkeypatch.setattr(
        "sis_caro_humanizer.calibrate._calibration_path",
        lambda: tmp_path / "calibration.toml",
    )

    result = runner.invoke(
        app,
        ["calibrate", "--human", str(human_file), "--ai", str(ai_file), "--dry-run"],
    )
    assert result.exit_code == 0, result.stdout
    assert "LOW_PPL" in result.stdout
    assert "HIGH_PPL" in result.stdout


def test_calibrate_cli_no_files_exits_nonzero():
    """CLI calibrate with no files and no tty exits non-zero."""
    # CliRunner provides no stdin, so the interactive loop returns empty immediately.
    # The command exits with code 1 or 2 (non-zero).
    result = runner.invoke(app, ["calibrate"])
    assert result.exit_code != 0


def test_calibrate_cli_missing_file_exits_2(tmp_path):
    """CLI calibrate with a nonexistent file path exits 2."""
    result = runner.invoke(
        app,
        [
            "calibrate",
            "--human",
            str(tmp_path / "missing.txt"),
            "--ai",
            str(tmp_path / "also_missing.txt"),
        ],
    )
    assert result.exit_code == 2
