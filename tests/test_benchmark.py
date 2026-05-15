"""Smoke tests for `humanize benchmark` CLI subcommand (v1.4)."""
from __future__ import annotations

import json

from typer.testing import CliRunner

from sis_caro_humanizer.cli import app
from sis_caro_humanizer.scoring.external import (
    DetectorResult,
    DetectorUnavailable,
)


runner = CliRunner()


def _write_sample(tmp_path):
    p = tmp_path / "sample.md"
    p.write_text(
        "We delve into the multifaceted tapestry of stakeholder dynamics. "
        "Furthermore, leaders must leverage robust strategies. " * 5,
        encoding="utf-8",
    )
    return p


def test_benchmark_no_external_prints_breakdown(tmp_path):
    sample = _write_sample(tmp_path)
    result = runner.invoke(app, ["benchmark", str(sample)])
    assert result.exit_code == 0, (result.stdout, result.stderr)
    out = result.stdout
    assert "Humanizer v1.4" in out
    assert "perplexity" in out
    assert "Score:" in out


def test_benchmark_json_output(tmp_path):
    sample = _write_sample(tmp_path)
    result = runner.invoke(app, ["benchmark", str(sample), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "humanizer" in payload
    names = {c["name"] for c in payload["humanizer"]["components"]}
    assert "perplexity" in names


def test_benchmark_external_with_mocked_detector(tmp_path, monkeypatch):
    sample = _write_sample(tmp_path)

    class _FakeDetector:
        URL = "https://example.test/api"

        def detect(self, text, *, timeout=8.0):
            return DetectorResult(score=0.74, band="high", confidence=0.9)

    monkeypatch.setattr(
        "sis_caro_humanizer.scoring.external.get_detector",
        lambda name: _FakeDetector(),
    )
    result = runner.invoke(
        app,
        [
            "benchmark",
            str(sample),
            "--external",
            "--detectors",
            "gptzero",
        ],
    )
    assert result.exit_code == 0, (result.stdout, result.stderr)
    assert "External detectors" in result.stdout
    assert "gptzero" in result.stdout


def test_benchmark_external_failure_does_not_crash(tmp_path, monkeypatch):
    sample = _write_sample(tmp_path)

    class _BadDetector:
        URL = "https://example.test/api"

        def detect(self, text, *, timeout=8.0):
            raise DetectorUnavailable("rate_limited")

    monkeypatch.setattr(
        "sis_caro_humanizer.scoring.external.get_detector",
        lambda name: _BadDetector(),
    )
    result = runner.invoke(
        app,
        [
            "benchmark",
            str(sample),
            "--external",
            "--detectors",
            "gptzero",
        ],
    )
    assert result.exit_code == 0
    assert "unavailable" in result.stdout


def test_benchmark_unknown_detector_exits_2(tmp_path):
    sample = _write_sample(tmp_path)
    result = runner.invoke(
        app,
        [
            "benchmark",
            str(sample),
            "--external",
            "--detectors",
            "whoops",
        ],
    )
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# New: check --external
# ---------------------------------------------------------------------------


def test_check_external_shows_comparison_table(tmp_path, monkeypatch):
    """check --external must render the side-by-side comparison table."""
    sample = _write_sample(tmp_path)

    class _FakeDetector:
        URL = "https://example.test/api"

        def detect(self, text, *, timeout=8.0):
            return DetectorResult(score=0.82, band="high", confidence=None)

    monkeypatch.setattr(
        "sis_caro_humanizer.scoring.external.get_detector",
        lambda name: _FakeDetector(),
    )
    result = runner.invoke(
        app,
        ["check", str(sample), "--external", "--detectors", "gptzero"],
    )
    assert result.exit_code == 0, result.stdout
    out = result.stdout
    assert "External AI-detector comparison" in out
    assert "humanizer (internal)" in out
    assert "gptzero" in out


def test_check_external_json_output(tmp_path, monkeypatch):
    """check --external --json emits {humanizer, external} payload."""
    sample = _write_sample(tmp_path)

    class _FakeDetector:
        URL = "https://example.test/api"

        def detect(self, text, *, timeout=8.0):
            return DetectorResult(score=0.65, band="medium", confidence=None)

    monkeypatch.setattr(
        "sis_caro_humanizer.scoring.external.get_detector",
        lambda name: _FakeDetector(),
    )
    result = runner.invoke(
        app,
        ["check", str(sample), "--external", "--detectors", "gptzero", "--json"],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert "humanizer" in payload
    assert "external" in payload
    assert len(payload["external"]) == 1
    assert payload["external"][0]["detector"] == "gptzero"


def test_check_external_unavailable_shows_error_row(tmp_path, monkeypatch):
    """When a detector fails, check --external still exits 0 and shows the error."""
    sample = _write_sample(tmp_path)

    class _BadDetector:
        URL = "https://example.test/api"

        def detect(self, text, *, timeout=8.0):
            raise DetectorUnavailable("missing_api_key")

    monkeypatch.setattr(
        "sis_caro_humanizer.scoring.external.get_detector",
        lambda name: _BadDetector(),
    )
    result = runner.invoke(
        app,
        ["check", str(sample), "--external", "--detectors", "sapling"],
    )
    assert result.exit_code == 0
    assert "unavailable" in result.stdout


def test_check_external_unknown_detector_exits_2(tmp_path):
    """check --external with an unknown detector name exits with code 2."""
    sample = _write_sample(tmp_path)
    result = runner.invoke(
        app,
        ["check", str(sample), "--external", "--detectors", "notadetector"],
    )
    assert result.exit_code == 2


def test_doctor_shows_external_detector_rows(tmp_path):
    """humanize doctor must include GPTZero, Sapling, ZeroGPT rows."""
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    out = result.stdout
    assert "GPTZero (external)" in out
    assert "Sapling (external)" in out
    assert "ZeroGPT (external)" in out
