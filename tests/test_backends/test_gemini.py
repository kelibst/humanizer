"""Gemini adapter tests with the google-generativeai SDK monkeypatched out."""
from __future__ import annotations

import sys
import types

import pytest

from sis_caro_humanizer.backends import get_backend
from sis_caro_humanizer.backends.base import BackendError, BackendUnavailable
from sis_caro_humanizer.backends import _secrets


@pytest.fixture(autouse=True)
def _no_secrets_file(monkeypatch):
    _secrets.reset_cache()
    monkeypatch.setattr(_secrets, "_load_secrets_file", lambda: {})


@pytest.fixture
def env_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AI-test")
    yield
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


class _Resp:
    def __init__(self, text):
        self.text = text


class _Model:
    def __init__(self, captured, model_name, system_instruction):
        self._captured = captured
        captured["model_name"] = model_name
        captured["system_instruction"] = system_instruction

    def generate_content(self, prompt, **kwargs):
        self._captured["prompt"] = prompt
        self._captured.update(kwargs)
        return _Resp("rewritten body")


def _install_fake_gemini(monkeypatch, captured):
    fake_root = types.ModuleType("google")
    fake_genai = types.ModuleType("google.generativeai")

    def _configure(api_key=None):
        captured["api_key"] = api_key

    def _model_factory(model_name, system_instruction=None, **_):
        return _Model(captured, model_name, system_instruction)

    fake_genai.configure = _configure
    fake_genai.GenerativeModel = _model_factory
    fake_root.generativeai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_root)
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)


def test_gemini_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    b = get_backend("gemini")
    assert b.is_available() is False
    with pytest.raises(BackendUnavailable):
        b.rewrite("hi", system="sys")


def test_gemini_rewrite_passes_system_instruction(monkeypatch, env_key):
    captured: dict = {}
    _install_fake_gemini(monkeypatch, captured)

    b = get_backend("gemini")
    out = b.rewrite("source body", system="be human")
    assert out == "rewritten body"
    assert captured["api_key"] == "AI-test"
    assert captured["system_instruction"] == "be human"
    assert "<text>" in captured["prompt"] and "source body" in captured["prompt"]
    # Model name resolves to default Gemini flash model.
    assert captured["model_name"].startswith("gemini-")


def test_gemini_model_override(monkeypatch, env_key):
    captured: dict = {}
    _install_fake_gemini(monkeypatch, captured)
    b = get_backend("gemini", config={"model": "gemini-1.5-pro"})
    b.rewrite("x", system="y")
    assert captured["model_name"] == "gemini-1.5-pro"


def test_gemini_quota_error_maps_to_backend_error(monkeypatch, env_key):
    fake_root = types.ModuleType("google")
    fake_genai = types.ModuleType("google.generativeai")

    def _configure(api_key=None):
        return None

    class _BoomModel:
        def __init__(self, **kw):
            pass

        def generate_content(self, prompt, **kwargs):
            raise RuntimeError("429 quota exceeded")

    fake_genai.configure = _configure
    fake_genai.GenerativeModel = lambda **kw: _BoomModel(**kw)
    fake_root.generativeai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_root)
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)

    with pytest.raises(BackendError, match="rate"):
        get_backend("gemini").rewrite("hi", system="sys")


def test_gemini_chatter_stripped(monkeypatch, env_key):
    captured: dict = {}
    fake_root = types.ModuleType("google")
    fake_genai = types.ModuleType("google.generativeai")

    fake_genai.configure = lambda api_key=None: None

    class _M:
        def __init__(self, **kw):
            pass

        def generate_content(self, prompt, **kwargs):
            return _Resp("Sure! Here is the rewritten text:\n\nbody only")

    fake_genai.GenerativeModel = lambda **kw: _M(**kw)
    fake_root.generativeai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_root)
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)

    out = get_backend("gemini").rewrite("x", system="y")
    assert out == "body only"
