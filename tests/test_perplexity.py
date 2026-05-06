"""Tests for the v1.4 perplexity feature.

Covers:
- Ollama happy-path (mocked logprobs).
- Ollama unavailable / logprobs unsupported → DistilGPT2 fallback.
- DistilGPT2 unavailable / load failure → graceful no-op.
- Score-report integration: perplexity is the 7th component, weights sum to 1.
"""
from __future__ import annotations

import math

import pytest

from sis_caro_humanizer.scoring import perplexity as perp_mod
from sis_caro_humanizer.scoring.perplexity import (
    HIGH_PPL,
    LOW_PPL,
    LogprobsNotSupported,
    PERPLEXITY_WEIGHT,
    perplexity_feature,
)
from sis_caro_humanizer.scoring.risk import ai_risk_score


@pytest.fixture(autouse=True)
def _reset_fallback_state(monkeypatch):
    """Reset the cached DistilGPT2 model + the failure latch + the test-suite
    kill-switch before each test so monkeypatched paths can run."""
    monkeypatch.delenv("HUMANIZE_DISABLE_PERPLEXITY", raising=False)
    perp_mod._FALLBACK = None
    perp_mod._FALLBACK_FAILED = False
    perp_mod._OLLAMA_LATCHED = False
    yield
    perp_mod._FALLBACK = None
    perp_mod._FALLBACK_FAILED = False
    perp_mod._OLLAMA_LATCHED = False


def test_ollama_happy_path(monkeypatch):
    """When Ollama logprobs returns numbers, the feature uses them and
    skips the fallback entirely."""

    def fake_logprobs(text, *, model, host=None, timeout=30.0):
        # Mean cross-entropy ≈ 2.0 nats → very AI-like (below LOW_PPL=2.4).
        return [-2.0, -2.0, -2.0, -2.0]

    monkeypatch.setattr("sis_caro_humanizer.ollama_client.logprobs", fake_logprobs)
    # Neuter the fallback so we know we hit Ollama.
    monkeypatch.setattr(perp_mod, "_distilgpt2_xent", lambda text: pytest.fail("should not call fallback"))

    contrib = perplexity_feature("This is a test paragraph that an LLM would happily produce." * 3)
    assert contrib.name == "perplexity"
    assert contrib.weight == PERPLEXITY_WEIGHT
    # mean_xent = 2.0; LOW_PPL=2.4; HIGH_PPL=5.5 → value = 1 - (2.0-2.4)/3.1 ≈ 1.13 → clamp 1.
    assert contrib.value == pytest.approx(1.0, abs=1e-6)
    assert "ollama" in contrib.detail


def test_ollama_logprobs_unsupported_falls_through(monkeypatch):
    def boom(text, *, model, host=None, timeout=30.0):
        raise LogprobsNotSupported("old runtime")

    monkeypatch.setattr("sis_caro_humanizer.ollama_client.logprobs", boom)
    # Force the fallback to also be unavailable.
    monkeypatch.setattr(perp_mod, "_distilgpt2_xent", lambda text: None)
    contrib = perplexity_feature("a paragraph long enough to score, " * 5)
    assert contrib.value == 0.0
    assert "perplexity_unavailable" in contrib.examples


def test_ollama_daemon_unreachable_uses_fallback(monkeypatch):
    """If Ollama is down, the DistilGPT2 fallback should run."""
    from sis_caro_humanizer.ollama_client import OllamaUnavailable

    def boom(text, *, model, host=None, timeout=30.0):
        raise OllamaUnavailable("daemon down")

    monkeypatch.setattr("sis_caro_humanizer.ollama_client.logprobs", boom)
    monkeypatch.setattr(perp_mod, "_distilgpt2_xent", lambda text: 4.0)
    contrib = perplexity_feature("an academic paragraph with mid-range perplexity.")
    # mean_xent = 4.0; LOW=2.4 HIGH=5.5 → value = 1 - (4.0-2.4)/3.1 ≈ 0.484
    assert contrib.value == pytest.approx(1.0 - (4.0 - LOW_PPL) / (HIGH_PPL - LOW_PPL), abs=1e-3)
    assert "distilgpt2" in contrib.detail


def test_distilgpt2_load_failure_returns_unavailable(monkeypatch):
    """If transformers cannot be imported, _load_fallback returns None and
    the feature degrades gracefully with value=0."""
    from sis_caro_humanizer.ollama_client import OllamaUnavailable

    def boom(text, *, model, host=None, timeout=30.0):
        raise OllamaUnavailable("nope")

    monkeypatch.setattr("sis_caro_humanizer.ollama_client.logprobs", boom)
    # Force the load helper to fail.
    monkeypatch.setattr(perp_mod, "_load_fallback", lambda: None)
    contrib = perplexity_feature("a paragraph long enough to score, " * 3)
    assert contrib.value == 0.0
    assert contrib.weight == PERPLEXITY_WEIGHT
    assert "perplexity_unavailable" in contrib.examples


def test_short_text_is_noop():
    contrib = perplexity_feature("hi")
    assert contrib.value == 0.0
    assert "too short" in contrib.detail


def test_high_xent_yields_low_value(monkeypatch):
    """A perplexity-heavy text (mean_xent above HIGH_PPL) maps to value 0."""
    from sis_caro_humanizer.ollama_client import OllamaUnavailable

    def boom(text, *, model, host=None, timeout=30.0):
        raise OllamaUnavailable("nope")

    monkeypatch.setattr("sis_caro_humanizer.ollama_client.logprobs", boom)
    monkeypatch.setattr(perp_mod, "_distilgpt2_xent", lambda text: 9.0)  # very high PPL
    contrib = perplexity_feature("normal academic prose about a topic. " * 3)
    assert contrib.value == 0.0


def test_perplexity_integrates_into_risk_score(monkeypatch):
    """A score report should include `perplexity` as the 7th component and
    weights should sum to 1.0."""
    monkeypatch.setattr(perp_mod, "_distilgpt2_xent", lambda text: 3.0)
    monkeypatch.setattr(
        "sis_caro_humanizer.ollama_client.logprobs",
        lambda text, *, model, host=None, timeout=30.0: (_ for _ in ()).throw(
            __import__("sis_caro_humanizer.ollama_client", fromlist=["OllamaUnavailable"]).OllamaUnavailable("nope")
        ),
    )
    rep = ai_risk_score("Some prose. " * 5)
    names = {c.name for c in rep.components}
    assert "perplexity" in names
    assert len(rep.components) == 7
    assert math.isclose(sum(c.weight for c in rep.components), 1.0, abs_tol=1e-6)


def test_profile_perplexity_model_passed_through(monkeypatch):
    """If the profile sets perplexity_model, the Ollama path uses it."""
    captured = {}

    def fake_logprobs(text, *, model, host=None, timeout=30.0):
        captured["model"] = model
        return [-3.0, -3.0]

    monkeypatch.setattr("sis_caro_humanizer.ollama_client.logprobs", fake_logprobs)

    class FakeProfile:
        perplexity_model = "gemma3:9b"

    perplexity_feature("a paragraph long enough.", FakeProfile())
    assert captured["model"] == "gemma3:9b"
