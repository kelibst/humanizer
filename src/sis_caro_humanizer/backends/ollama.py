"""Ollama backend adapter.

Wraps the existing :mod:`sis_caro_humanizer.ollama_client` so the pipeline can
go through ``get_backend("ollama")`` like any other provider.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .. import ollama_client as _ollama
from .base import BackendError, BackendUnavailable, clean_output, wrap_user_message

DEFAULT_MODEL = "gemma3:4b"
DEFAULT_HOST = _ollama.DEFAULT_HOST


@dataclass
class OllamaBackend:
    """Backend for a locally-running Ollama daemon."""

    host: str = DEFAULT_HOST
    model: str = DEFAULT_MODEL
    timeout: float = 600.0
    options: dict[str, Any] = field(default_factory=lambda: {"temperature": 0.7, "top_p": 0.9})
    name: str = field(default="ollama", init=False)

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> "OllamaBackend":
        cfg = config or {}
        return cls(
            host=str(cfg.get("host") or DEFAULT_HOST),
            model=str(cfg.get("model") or DEFAULT_MODEL),
            timeout=float(cfg.get("timeout") or 600.0),
            options=dict(cfg.get("options") or {"temperature": 0.7, "top_p": 0.9}),
        )

    def is_available(self) -> bool:
        return _ollama.is_running(self.host)

    def rewrite(
        self,
        text: str,
        *,
        system: str,
        model: str | None = None,
        timeout: float | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        if not text.strip():
            return text
        prompt = wrap_user_message(text)
        chosen_model = model or self.model
        chosen_timeout = timeout if timeout is not None else self.timeout
        merged_options = dict(self.options)
        if options:
            merged_options.update(options)
        try:
            reply = _ollama.generate(
                prompt,
                model=chosen_model,
                system=system,
                host=self.host,
                timeout=chosen_timeout,
                options=merged_options,
            )
        except _ollama.OllamaUnavailable as exc:
            raise BackendUnavailable(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise BackendError(f"ollama call failed: {exc}") from exc
        return clean_output(reply)


__all__ = ["OllamaBackend", "DEFAULT_MODEL", "DEFAULT_HOST"]
