"""OpenAI adapter tests with the SDK monkeypatched out."""
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
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    yield
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]


class _Completions:
    def __init__(self, captured):
        self._captured = captured

    def create(self, **kwargs):
        self._captured.update(kwargs)
        return _Resp("rewritten")


class _Chat:
    def __init__(self, captured):
        self.completions = _Completions(captured)


class _Client:
    def __init__(self, captured, **init_kwargs):
        captured["_init"] = init_kwargs
        self.chat = _Chat(captured)


def _install_fake_openai(monkeypatch, captured):
    fake = types.ModuleType("openai")
    fake.OpenAI = lambda **kwargs: _Client(captured, **kwargs)
    monkeypatch.setitem(sys.modules, "openai", fake)


def test_openai_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    b = get_backend("openai")
    assert b.is_available() is False
    with pytest.raises(BackendUnavailable):
        b.rewrite("hi", system="sys")


def test_openai_rewrite_sends_correct_shape(monkeypatch, env_key):
    captured: dict = {}
    _install_fake_openai(monkeypatch, captured)

    b = get_backend("openai", config={"model": "gpt-4o-mini"})
    out = b.rewrite("source body", system="be human")
    assert out == "rewritten"
    assert captured["model"] == "gpt-4o-mini"
    msgs = captured["messages"]
    assert msgs[0] == {"role": "system", "content": "be human"}
    assert msgs[1]["role"] == "user"
    assert "<text>" in msgs[1]["content"] and "source body" in msgs[1]["content"]
    # Client init received api_key + base_url + timeout.
    init = captured["_init"]
    assert init["api_key"] == "sk-test"
    assert init["base_url"].startswith("https://")


def test_openai_default_host(env_key):
    b = get_backend("openai")
    assert b.host == "https://api.openai.com/v1"
    assert b.model.startswith("gpt-")


def test_openai_rate_limit_maps_to_backend_error(monkeypatch, env_key):
    fake = types.ModuleType("openai")

    class _BoomCompletions:
        def create(self, **kwargs):
            raise RuntimeError("429 rate limit reached")

    class _BoomChat:
        completions = _BoomCompletions()

    class _BoomClient:
        def __init__(self, **kwargs):
            self.chat = _BoomChat()

    fake.OpenAI = _BoomClient
    monkeypatch.setitem(sys.modules, "openai", fake)

    with pytest.raises(BackendError, match="rate"):
        get_backend("openai").rewrite("hi", system="sys")


def test_openai_chatter_stripped(monkeypatch, env_key):
    captured: dict = {}
    fake = types.ModuleType("openai")

    class _Cmp:
        def create(self, **kwargs):
            return _Resp("Sure! Here is the rewritten text:\n\nbody only")

    class _Ch:
        completions = _Cmp()

    class _Cl:
        def __init__(self, **kwargs):
            self.chat = _Ch()

    fake.OpenAI = _Cl
    monkeypatch.setitem(sys.modules, "openai", fake)

    out = get_backend("openai").rewrite("x", system="y")
    assert out == "body only"
