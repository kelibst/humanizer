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


def logprobs(
    text: str,
    *,
    model: str,
    host: str = DEFAULT_HOST,
    timeout: float = 30.0,
) -> list[float]:
    """Return per-token natural-log probabilities for ``text`` under ``model``.

    Used by the perplexity feature (v1.4). Tries Ollama's ``/api/generate``
    with ``logprobs`` enabled; if the runtime / model does not surface them,
    raises :class:`scoring.perplexity.LogprobsNotSupported` so the caller can
    fall back to DistilGPT2.

    Raises :class:`OllamaUnavailable` if the daemon itself is unreachable.
    """
    # Local import to avoid circular: scoring.perplexity imports ollama_client.
    from .scoring.perplexity import LogprobsNotSupported

    if not is_running(host):
        raise OllamaUnavailable(f"ollama daemon not reachable at {host}")

    payload = {
        "model": model,
        "prompt": text,
        "raw": True,
        "stream": False,
        "options": {
            "num_predict": 0,
            # Newer Ollama exposes `logprobs` here; older versions ignore it.
            "logprobs": True,
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
        raise OllamaUnavailable(f"ollama logprobs request failed: {exc}") from exc

    # Walk a few likely shapes. Ollama's logprobs API is in flux across
    # versions; tolerate any of (a) `logprobs` top-level list of floats,
    # (b) `logprobs.token_logprobs`, (c) `tokens[].logprob` array.
    raw = data.get("logprobs") if isinstance(data, dict) else None
    if isinstance(raw, list) and raw and all(isinstance(x, (int, float)) for x in raw):
        return [float(x) for x in raw]
    if isinstance(raw, dict):
        token_lp = raw.get("token_logprobs")
        if isinstance(token_lp, list) and token_lp:
            return [float(x) for x in token_lp if isinstance(x, (int, float))]
    tokens = data.get("tokens") if isinstance(data, dict) else None
    if isinstance(tokens, list) and tokens and isinstance(tokens[0], dict) and "logprob" in tokens[0]:
        return [float(t["logprob"]) for t in tokens if isinstance(t.get("logprob"), (int, float))]

    raise LogprobsNotSupported(
        f"ollama at {host} returned no logprobs for model {model!r} — runtime "
        "may be too old or the model does not expose them."
    )
