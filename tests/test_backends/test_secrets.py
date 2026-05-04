"""API-key resolution: explicit config -> env var -> secrets.toml."""
from __future__ import annotations

from sis_caro_humanizer.backends import _secrets
from sis_caro_humanizer.backends._secrets import resolve_api_key


def test_resolve_explicit_config_wins(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    _secrets.reset_cache()
    monkeypatch.setattr(_secrets, "_load_secrets_file", lambda: {"ANTHROPIC_API_KEY": "from-file"})
    got = resolve_api_key("ANTHROPIC_API_KEY", {"api_key": "from-config"})
    assert got == "from-config"


def test_resolve_env_beats_file(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    _secrets.reset_cache()
    monkeypatch.setattr(_secrets, "_load_secrets_file", lambda: {"ANTHROPIC_API_KEY": "from-file"})
    assert resolve_api_key("ANTHROPIC_API_KEY") == "from-env"


def test_resolve_file_when_env_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _secrets.reset_cache()
    monkeypatch.setattr(_secrets, "_load_secrets_file", lambda: {"ANTHROPIC_API_KEY": "from-file"})
    assert resolve_api_key("ANTHROPIC_API_KEY") == "from-file"


def test_resolve_returns_none_when_nothing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _secrets.reset_cache()
    monkeypatch.setattr(_secrets, "_load_secrets_file", lambda: {})
    assert resolve_api_key("ANTHROPIC_API_KEY") is None
