"""OpenAI backend adapter.

Uses the official ``openai`` Python SDK (>=1.30). Default model: ``gpt-5-mini``
per the contract; users on older tiers can override via
``backend_config.model``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import BackendError, BackendUnavailable, clean_output, wrap_user_message
from ._secrets import resolve_api_key

DEFAULT_MODEL = "gpt-5-mini"
DEFAULT_HOST = "https://api.openai.com/v1"
ENV_VAR = "OPENAI_API_KEY"


@dataclass
class OpenAIBackend:
    api_key: str | None = None
    host: str = DEFAULT_HOST
    model: str = DEFAULT_MODEL
    timeout: float = 120.0
    options: dict[str, Any] = field(default_factory=dict)
    name: str = field(default="openai", init=False)

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> "OpenAIBackend":
        cfg = config or {}
        return cls(
            api_key=resolve_api_key(ENV_VAR, cfg),
            host=str(cfg.get("host") or DEFAULT_HOST),
            model=str(cfg.get("model") or DEFAULT_MODEL),
            timeout=float(cfg.get("timeout") or 120.0),
            options=dict(cfg.get("options") or {}),
        )

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _client(self):
        try:
            import openai  # type: ignore
        except ImportError as exc:  # pragma: no cover - dep is in pyproject
            raise BackendUnavailable(f"openai SDK not installed: {exc}") from exc
        if not self.api_key:
            raise BackendUnavailable(
                f"no OpenAI API key configured (set {ENV_VAR} or "
                "~/.config/humanizer/secrets.toml)"
            )
        return openai.OpenAI(api_key=self.api_key, base_url=self.host, timeout=self.timeout)

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
        client = self._client()
        chosen_model = model or self.model
        kwargs: dict[str, Any] = {
            "model": chosen_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": wrap_user_message(text)},
            ],
        }
        if timeout is not None:
            kwargs["timeout"] = timeout
        merged = dict(self.options)
        if options:
            merged.update(options)
        kwargs.update(merged)

        try:
            response = client.chat.completions.create(**kwargs)
        except BackendUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if "api key" in msg or "unauthorized" in msg or "401" in msg:
                raise BackendError(f"openai auth failed: {exc}") from exc
            if "rate" in msg or "quota" in msg or "429" in msg:
                raise BackendError(f"openai rate limited: {exc}") from exc
            raise BackendError(f"openai call failed: {exc}") from exc

        return clean_output(_extract_text(response))


def _extract_text(response: Any) -> str:
    """Pull the rewritten text out of a chat-completions response."""
    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, dict):
        choices = response.get("choices")
    if not choices:
        return ""
    first = choices[0]
    msg = getattr(first, "message", None)
    if msg is None and isinstance(first, dict):
        msg = first.get("message")
    if msg is None:
        return ""
    content = getattr(msg, "content", None)
    if content is None and isinstance(msg, dict):
        content = msg.get("content")
    return str(content or "")


__all__ = ["OpenAIBackend", "DEFAULT_MODEL", "DEFAULT_HOST", "ENV_VAR"]
