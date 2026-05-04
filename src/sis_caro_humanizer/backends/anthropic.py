"""Anthropic Claude backend adapter.

Uses the official ``anthropic`` Python SDK. Applies prompt caching to the
system prompt (``cache_control={"type": "ephemeral"}``) so the sidebar's
repeated calls within a 5-minute window pay only once for the long voice-spec
prompt.

API-key resolution: explicit config → ``ANTHROPIC_API_KEY`` env var →
``~/.config/humanizer/secrets.toml``. Default model: ``claude-sonnet-4-6``
(per the contract).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import BackendError, BackendUnavailable, clean_output, wrap_user_message
from ._secrets import resolve_api_key

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 4096
ENV_VAR = "ANTHROPIC_API_KEY"


@dataclass
class AnthropicBackend:
    api_key: str | None = None
    model: str = DEFAULT_MODEL
    timeout: float = 120.0
    max_tokens: int = DEFAULT_MAX_TOKENS
    options: dict[str, Any] = field(default_factory=dict)
    name: str = field(default="anthropic", init=False)

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> "AnthropicBackend":
        cfg = config or {}
        return cls(
            api_key=resolve_api_key(ENV_VAR, cfg),
            model=str(cfg.get("model") or DEFAULT_MODEL),
            timeout=float(cfg.get("timeout") or 120.0),
            max_tokens=int(cfg.get("max_tokens") or DEFAULT_MAX_TOKENS),
            options=dict(cfg.get("options") or {}),
        )

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _client(self):
        try:
            import anthropic  # type: ignore
        except ImportError as exc:  # pragma: no cover - dep is in pyproject
            raise BackendUnavailable(f"anthropic SDK not installed: {exc}") from exc
        if not self.api_key:
            raise BackendUnavailable(
                f"no Anthropic API key configured (set {ENV_VAR} or "
                "~/.config/humanizer/secrets.toml)"
            )
        return anthropic.Anthropic(api_key=self.api_key)

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
        # Prompt caching: mark the system block as ephemeral so the next call
        # within ~5 minutes reuses the cached prefix.
        system_blocks = [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        messages = [{"role": "user", "content": wrap_user_message(text)}]

        kwargs: dict[str, Any] = {
            "model": chosen_model,
            "max_tokens": self.max_tokens,
            "system": system_blocks,
            "messages": messages,
        }
        if options:
            kwargs.update(options)
        # SDK's per-request timeout is applied via the ``timeout`` kwarg or
        # client-level default; we surface it via ``with_options`` when set.
        try:
            if timeout is not None or self.timeout:
                client = client.with_options(
                    timeout=timeout if timeout is not None else self.timeout
                )
            response = client.messages.create(**kwargs)
        except BackendUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if "api key" in msg or "unauthorized" in msg or "401" in msg:
                raise BackendError(f"anthropic auth failed: {exc}") from exc
            if "rate" in msg or "quota" in msg or "429" in msg:
                raise BackendError(f"anthropic rate limited: {exc}") from exc
            raise BackendError(f"anthropic call failed: {exc}") from exc

        return clean_output(_extract_text(response))


def _extract_text(response: Any) -> str:
    """Pull the rewritten text out of an Anthropic ``Message`` response."""
    content = getattr(response, "content", None)
    if content is None and isinstance(response, dict):
        content = response.get("content")
    if not content:
        return ""
    parts: list[str] = []
    for block in content:
        # SDK objects expose ``.text``; dicts use ``["text"]``.
        if hasattr(block, "text"):
            parts.append(str(block.text or ""))
        elif isinstance(block, dict):
            t = block.get("text")
            if t is not None:
                parts.append(str(t))
    return "".join(parts)


__all__ = ["AnthropicBackend", "DEFAULT_MODEL", "ENV_VAR"]
