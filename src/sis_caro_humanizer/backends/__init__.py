"""Multi-backend registry for the LLM rewrite stage.

See ``plan/BACKEND_CONTRACT.md``.

Public surface:

* :func:`get_backend` — construct a backend by name, optionally configured.
* :func:`list_backends` — names of every supported provider.
* :func:`list_available` — names of providers that report ``is_available()``.
* Re-exports :class:`Backend`, :class:`BackendUnavailable`, :class:`BackendError`.
"""
from __future__ import annotations

from typing import Any, Callable

from .base import Backend, BackendError, BackendUnavailable, clean_output, wrap_user_message

# Adapter factories. Each ``from_config`` returns an instance whose static type
# satisfies the :class:`Backend` protocol.
_FACTORIES: dict[str, Callable[[dict[str, Any] | None], Backend]] = {}


def _register_default_factories() -> None:
    """Lazy-register adapters so importing this module does not import the
    hosted-provider SDKs unless they are actually used."""
    from .ollama import OllamaBackend
    from .anthropic import AnthropicBackend
    from .openai import OpenAIBackend
    from .gemini import GeminiBackend

    _FACTORIES["ollama"] = OllamaBackend.from_config
    _FACTORIES["anthropic"] = AnthropicBackend.from_config
    _FACTORIES["openai"] = OpenAIBackend.from_config
    _FACTORIES["gemini"] = GeminiBackend.from_config


_register_default_factories()

BACKEND_NAMES: tuple[str, ...] = ("ollama", "anthropic", "openai", "gemini")


def list_backends() -> list[str]:
    """Return the names of every registered backend, in canonical order."""
    return [n for n in BACKEND_NAMES if n in _FACTORIES]


def get_backend(name: str, *, config: dict[str, Any] | None = None) -> Backend:
    """Construct the named backend.

    Raises :class:`ValueError` for an unknown name.
    """
    factory = _FACTORIES.get(name)
    if factory is None:
        raise ValueError(
            f"unknown backend {name!r}; expected one of {list_backends()}"
        )
    return factory(config)


def list_available(configs: dict[str, dict[str, Any]] | None = None) -> list[str]:
    """Return the subset of registered backends whose ``is_available()`` is True.

    ``configs`` lets a caller pass per-backend config (e.g. an API key) so the
    health check sees the same config the actual rewrite will see. Backends
    whose construction itself raises :class:`BackendUnavailable` are skipped.
    """
    out: list[str] = []
    cfgs = configs or {}
    for name in list_backends():
        try:
            backend = get_backend(name, config=cfgs.get(name))
        except BackendUnavailable:
            continue
        except Exception:
            continue
        try:
            if backend.is_available():
                out.append(name)
        except Exception:
            continue
    return out


__all__ = [
    "Backend",
    "BackendError",
    "BackendUnavailable",
    "BACKEND_NAMES",
    "clean_output",
    "wrap_user_message",
    "get_backend",
    "list_backends",
    "list_available",
]
