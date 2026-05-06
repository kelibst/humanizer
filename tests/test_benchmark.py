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
