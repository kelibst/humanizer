"""Google Gemini backend adapter.

Uses the ``google-generativeai`` SDK. Gemini's ``GenerativeModel`` accepts
``system_instruction=`` directly (SDK 0.5+). Default model: ``gemini-2.0-flash``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import BackendError, BackendUnavailable, clean_output, wrap_user_message
from ._secrets import resolve_api_key

DEFAULT_MODEL = "gemini-2.0-flash"
ENV_VAR = "GEMINI_API_KEY"


@dataclass
class GeminiBackend:
    api_key: str | None = None
    model: str = DEFAULT_MODEL
    timeout: float = 120.0
    options: dict[str, Any] = field(default_factory=dict)
    name: str = field(default="gemini", init=False)

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> "GeminiBackend":
        cfg = config or {}
        return cls(
            api_key=resolve_api_key(ENV_VAR, cfg),
            model=str(cfg.get("model") or DEFAULT_MODEL),
            timeout=float(cfg.get("timeout") or 120.0),
            options=dict(cfg.get("options") or {}),
        )

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _model_handle(self, system: str, model_name: str):
        try:
            # TODO(v1.7): migrate to google.genai — see FutureWarning above
            import google.generativeai as genai  # type: ignore
        except ImportError as exc:  # pragma: no cover - dep is in pyproject
            raise BackendUnavailable(f"google-generativeai SDK not installed: {exc}") from exc
        if not self.api_key:
            raise BackendUnavailable(
                f"no Gemini API key configured (set {ENV_VAR} or "
                "~/.config/humanizer/secrets.toml)"
            )
        try:
            genai.configure(api_key=self.api_key)
        except Exception as exc:  # noqa: BLE001
            raise BackendError(f"gemini configure failed: {exc}") from exc
        return genai.GenerativeModel(model_name=model_name, system_instruction=system)

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
        chosen_model = model or self.model
        handle = self._model_handle(system=system, model_name=chosen_model)
        prompt = wrap_user_message(text)

        gen_config: dict[str, Any] = dict(self.options)
        if options:
            gen_config.update(options)
        request_kwargs: dict[str, Any] = {}
        if gen_config:
            request_kwargs["generation_config"] = gen_config
        timeout_val = timeout if timeout is not None else self.timeout
        if timeout_val:
            request_kwargs["request_options"] = {"timeout": timeout_val}

        try:
            response = handle.generate_content(prompt, **request_kwargs)
        except BackendUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if "api key" in msg or "unauthorized" in msg or "401" in msg:
                raise BackendError(f"gemini auth failed: {exc}") from exc
            if "rate" in msg or "quota" in msg or "429" in msg:
                raise BackendError(f"gemini rate limited: {exc}") from exc
            raise BackendError(f"gemini call failed: {exc}") from exc

        return clean_output(_extract_text(response))


def _extract_text(response: Any) -> str:
    """Pull the rewritten text out of a Gemini ``GenerateContentResponse``."""
    text = getattr(response, "text", None)
    if isinstance(text, str) and text:
        return text
    if isinstance(response, dict):
        t = response.get("text")
        if isinstance(t, str) and t:
            return t
    candidates = getattr(response, "candidates", None)
    if candidates is None and isinstance(response, dict):
        candidates = response.get("candidates")
    if not candidates:
        return ""
    first = candidates[0]
    content = getattr(first, "content", None)
    if content is None and isinstance(first, dict):
        content = first.get("content")
    if content is None:
        return ""
    parts = getattr(content, "parts", None)
    if parts is None and isinstance(content, dict):
        parts = content.get("parts")
    if not parts:
        return ""
    pieces: list[str] = []
    for part in parts:
        t = getattr(part, "text", None)
        if t is None and isinstance(part, dict):
            t = part.get("text")
        if t:
            pieces.append(str(t))
    return "".join(pieces)


__all__ = ["GeminiBackend", "DEFAULT_MODEL", "ENV_VAR"]
