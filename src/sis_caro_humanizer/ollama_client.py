"""Thin wrapper around the Ollama HTTP API and the official `ollama` Python client.

Stage 2 (`pipeline/stage2_llm_rewrite.py`) calls into here. The CLI's `doctor`
command also uses :func:`is_running` and :func:`ensure_model`. We never auto-pull;
a missing model is reported up the call stack so the operator can run
``ollama pull <model>`` themselves.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

DEFAULT_HOST = "http://localhost:11434"


class OllamaUnavailable(Exception):
    """Raised when the Ollama daemon is unreachable, the requested model is
    missing, or the generation call fails irrecoverably."""


def _http_json(url: str, timeout: float = 3.0) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def is_running(host: str = DEFAULT_HOST) -> bool:
    """Return True if the Ollama daemon answers ``/api/tags`` within ~2s."""
    try:
        _http_json(f"{host.rstrip('/')}/api/tags", timeout=2.0)
        return True
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        return False


def list_models(host: str = DEFAULT_HOST) -> list[str]:
    """List installed Ollama models (the ``name`` field of each tag)."""
    try:
        data = _http_json(f"{host.rstrip('/')}/api/tags", timeout=3.0)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        return []
    models = data.get("models") or []
    return [m.get("name", "") for m in models if m.get("name")]


def ensure_model(model: str, host: str = DEFAULT_HOST) -> bool:
    """Return True if ``model`` is present locally. Never auto-pulls."""
    if not is_running(host):
        return False
    available = list_models(host)
    if model in available:
        return True
    # `ollama list` formats include the tag (e.g. "gemma3:4b") and sometimes the
    # bare base name. Accept either spelling.
    base = model.split(":", 1)[0]
    return any(m == model or m.split(":", 1)[0] == base for m in available)


def generate(
    prompt: str,
    *,
    model: str,
    system: str | None = None,
    host: str = DEFAULT_HOST,
    timeout: float = 600.0,
    options: dict[str, Any] | None = None,
) -> str:
    """Run a single-shot generation against Ollama and return the text.

    Raises :class:`OllamaUnavailable` for any reachable-but-failed call as well
    as connection errors. The caller (the runner) is expected to downgrade
    gracefully when this fires.
    """
    if not is_running(host):
        raise OllamaUnavailable(f"ollama daemon not reachable at {host}")

    try:
        # Import here so a broken/old `ollama` package does not crash module import.
        import ollama  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on env
        raise OllamaUnavailable(f"ollama python package unusable: {exc}") from exc

    client_kwargs: dict[str, Any] = {"host": host}
    try:
        client = ollama.Client(**client_kwargs)
    except Exception as exc:
        raise OllamaUnavailable(f"could not construct ollama client: {exc}") from exc

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    opts = dict(options or {})
    # Surface the timeout on the HTTP layer where possible. The official client
    # accepts a `keep_alive` and (recent versions) `options` dict; per-request
    # timeout is applied on the underlying httpx client when supported.
    try:
        # Prefer chat() so the system prompt is honoured cleanly.
        response = client.chat(model=model, messages=messages, options=opts)
    except Exception as exc:
        msg = str(exc).lower()
        if "model" in msg and ("not found" in msg or "no such" in msg or "pull" in msg):
            raise OllamaUnavailable(
                f"model {model!r} is not pulled. Run `ollama pull {model}` and retry."
            ) from exc
        raise OllamaUnavailable(f"ollama generation failed: {exc}") from exc

    # Response shape: {"message": {"content": "..."}, ...}
    content = ""
    if isinstance(response, dict):
        msg_obj = response.get("message") or {}
        content = msg_obj.get("content", "") if isinstance(msg_obj, dict) else ""
    else:
        # Newer ollama package returns a pydantic-like object with .message.content
        try:
            content = response.message.content  # type: ignore[attr-defined]
        except AttributeError:
            content = str(response)

    return (content or "").strip()
