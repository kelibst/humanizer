"""Registry-level tests for the multi-backend layer."""
from __future__ import annotations

import pytest

from sis_caro_humanizer.backends import (
    BACKEND_NAMES,
    Backend,
    BackendError,
    BackendUnavailable,
    get_backend,
    list_available,
    list_backends,
)


def test_list_backends_returns_all_four():
    assert list_backends() == ["ollama", "anthropic", "openai", "gemini"]
    assert BACKEND_NAMES == ("ollama", "anthropic", "openai", "gemini")


@pytest.mark.parametrize("name", ["ollama", "anthropic", "openai", "gemini"])
def test_get_backend_returns_protocol_match(name):
    b = get_backend(name)
    assert isinstance(b, Backend)
    assert b.name == name
    # Each backend declares a non-empty default model.
    assert b.model


def test_get_backend_unknown_raises():
    with pytest.raises(ValueError, match="unknown backend"):
        get_backend("not-a-thing")


def test_get_backend_passes_config_to_factory(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    b = get_backend("anthropic", config={"api_key": "sk-test", "model": "claude-haiku-4-5"})
    assert b.api_key == "sk-test"
    assert b.model == "claude-haiku-4-5"
    assert b.is_available()


def test_list_available_with_only_ollama_running(monkeypatch):
    """Only Ollama should be available when no API keys are configured."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    # Stub out the secrets file so it cannot supply keys.
    from sis_caro_humanizer.backends import _secrets

    _secrets.reset_cache()
    monkeypatch.setattr(_secrets, "_load_secrets_file", lambda: {})

    # Force Ollama health check to True/False explicitly.
    from sis_caro_humanizer.backends import ollama as ollama_backend_mod

    monkeypatch.setattr(ollama_backend_mod._ollama, "is_running", lambda host=...: True)
    avail = list_available()
    assert "ollama" in avail
    assert "anthropic" not in avail
    assert "openai" not in avail
    assert "gemini" not in avail

    monkeypatch.setattr(ollama_backend_mod._ollama, "is_running", lambda host=...: False)
    avail = list_available()
    assert "ollama" not in avail


def test_list_available_picks_up_env_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("GEMINI_API_KEY", "AI-test")
    from sis_caro_humanizer.backends import _secrets, ollama as ollama_backend_mod

    _secrets.reset_cache()
    monkeypatch.setattr(_secrets, "_load_secrets_file", lambda: {})
    monkeypatch.setattr(ollama_backend_mod._ollama, "is_running", lambda host=...: False)

    avail = list_available()
    assert set(avail) >= {"anthropic", "openai", "gemini"}


def test_exceptions_are_distinct():
    assert issubclass(BackendUnavailable, Exception)
    assert issubclass(BackendError, Exception)
    assert BackendError is not BackendUnavailable
