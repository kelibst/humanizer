"""Anthropic adapter tests with the SDK monkeypatched out."""
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
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    yield
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


class _Block:
    def __init__(self, text):
        self.text = text


class _Resp:
    def __init__(self, text):
        self.content = [_Block(text)]


class _Messages:
    def __init__(self, captured):
        self._captured = captured

    def create(self, **kwargs):
        self._captured.update(kwargs)
        return _Resp("polished output")


class _Client:
    def __init__(self, captured):
        self.messages = _Messages(captured)
        self._captured = captured

    def with_options(self, **kwargs):
        self._captured["with_options"] = kwargs
        return self


def _install_fake_anthropic(monkeypatch, captured):
    fake = types.ModuleType("anthropic")
    fake.Anthropic = lambda **kwargs: _Client(captured)
    monkeypatch.setitem(sys.modules, "anthropic", fake)


def test_anthropic_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    b = get_backend("anthropic")
    assert b.is_available() is False
    with pytest.raises(BackendUnavailable):
        b.rewrite("hi", system="sys")


def test_anthropic_available_with_env_key(env_key):
    b = get_backend("anthropic")
    assert b.is_available() is True


def test_anthropic_rewrite_sends_correct_shape(monkeypatch, env_key):
    captured: dict = {}
    _install_fake_anthropic(monkeypatch, captured)

    b = get_backend("anthropic")
    out = b.rewrite("hello world", system="be a human", model="claude-haiku-4-5")
    assert out == "polished output"
    assert captured["model"] == "claude-haiku-4-5"
    # System sent as cache-controlled blocks list.
    assert isinstance(captured["system"], list)
    assert captured["system"][0]["type"] == "text"
    assert captured["system"][0]["text"] == "be a human"
    assert captured["system"][0]["cache_control"] == {"type": "ephemeral"}
    # User message wrapped in <text>...</text>.
    user = captured["messages"][0]["content"]
    assert "<text>" in user and "hello world" in user and "</text>" in user
    assert captured["max_tokens"] >= 1024


def test_anthropic_auth_error_maps_to_backend_error(monkeypatch, env_key):
    captured: dict = {}
    fake = types.ModuleType("anthropic")

    class _BoomMessages:
        def create(self, **kwargs):
            raise RuntimeError("401 unauthorized")

    class _BoomClient:
        messages = _BoomMessages()

        def with_options(self, **kwargs):
            return self

    fake.Anthropic = lambda **kwargs: _BoomClient()
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    b = get_backend("anthropic")
    with pytest.raises(BackendError, match="auth"):
        b.rewrite("hi", system="sys")


def test_anthropic_chatter_stripped_from_response(monkeypatch, env_key):
    captured: dict = {}
    fake = types.ModuleType("anthropic")

    class _Msgs:
        def create(self, **kwargs):
            return _Resp("Sure! Here is the rewritten text:\n\nthe body")

    class _Cl:
        messages = _Msgs()

        def with_options(self, **kwargs):
            return self

    fake.Anthropic = lambda **kwargs: _Cl()
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    b = get_backend("anthropic")
    out = b.rewrite("x", system="y")
    assert out == "the body"
