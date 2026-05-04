"""Ollama adapter tests with the real Ollama HTTP layer monkeypatched out."""
from __future__ import annotations

import pytest

from sis_caro_humanizer.backends import get_backend
from sis_caro_humanizer.backends.base import BackendError, BackendUnavailable
from sis_caro_humanizer.backends import ollama as ollama_backend_mod


def test_ollama_default_model_and_host():
    b = get_backend("ollama")
    assert b.name == "ollama"
    assert b.host.startswith("http://")
    assert ":" in b.model  # gemma3:4b style


def test_ollama_is_available_consults_is_running(monkeypatch):
    monkeypatch.setattr(ollama_backend_mod._ollama, "is_running", lambda host=...: True)
    assert get_backend("ollama").is_available() is True
    monkeypatch.setattr(ollama_backend_mod._ollama, "is_running", lambda host=...: False)
    assert get_backend("ollama").is_available() is False


def test_ollama_rewrite_calls_generate(monkeypatch):
    captured: dict = {}

    def fake_generate(prompt, *, model, system, host, timeout, options):
        captured["prompt"] = prompt
        captured["model"] = model
        captured["system"] = system
        captured["host"] = host
        captured["timeout"] = timeout
        captured["options"] = options
        return "Here is the rewritten text:\n\nrewritten body"

    monkeypatch.setattr(ollama_backend_mod._ollama, "generate", fake_generate)
    monkeypatch.setattr(ollama_backend_mod._ollama, "is_running", lambda host=...: True)

    b = get_backend("ollama", config={"model": "gemma3:4b"})
    out = b.rewrite("source text", system="be human", model="gemma3:4b", timeout=10.0)
    assert out == "rewritten body"  # chatter stripped
    assert "source text" in captured["prompt"]
    assert "<text>" in captured["prompt"]
    assert captured["system"] == "be human"
    assert captured["model"] == "gemma3:4b"
    assert captured["timeout"] == 10.0


def test_ollama_unavailable_maps_to_backend_unavailable(monkeypatch):
    def boom(*a, **kw):
        from sis_caro_humanizer.ollama_client import OllamaUnavailable

        raise OllamaUnavailable("daemon down")

    monkeypatch.setattr(ollama_backend_mod._ollama, "generate", boom)
    monkeypatch.setattr(ollama_backend_mod._ollama, "is_running", lambda host=...: True)

    b = get_backend("ollama")
    with pytest.raises(BackendUnavailable, match="daemon down"):
        b.rewrite("hi", system="sys")


def test_ollama_other_error_maps_to_backend_error(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(ollama_backend_mod._ollama, "generate", boom)
    monkeypatch.setattr(ollama_backend_mod._ollama, "is_running", lambda host=...: True)

    b = get_backend("ollama")
    with pytest.raises(BackendError, match="exploded"):
        b.rewrite("hi", system="sys")


def test_ollama_empty_text_short_circuits(monkeypatch):
    called = {"n": 0}

    def fake_generate(*a, **kw):
        called["n"] += 1
        return ""

    monkeypatch.setattr(ollama_backend_mod._ollama, "generate", fake_generate)

    b = get_backend("ollama")
    assert b.rewrite("", system="sys") == ""
    assert called["n"] == 0
