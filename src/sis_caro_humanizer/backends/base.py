"""Backend protocol shared by every LLM adapter.

See ``plan/BACKEND_CONTRACT.md`` for the locked interface.

A backend wraps a single provider (Ollama, Anthropic, OpenAI, Gemini) behind a
narrow ``rewrite()`` call. The pipeline's stage 2 looks up a backend by name and
calls ``is_available()`` followed by ``rewrite()``. Two exceptions, both defined
here, communicate failure modes:

* :class:`BackendUnavailable` — provider unreachable, daemon down, or no API
  key configured. The pipeline downgrades to deterministic-only when this fires.
* :class:`BackendError` — provider responded with a non-success status (auth,
  quota, 5xx). The bridge surfaces this as HTTP 502.
"""
from __future__ import annotations

import re
from typing import Any, Protocol, runtime_checkable


class BackendUnavailable(Exception):
    """Provider unreachable, daemon down, or no API key configured.

    The pipeline runner catches this and continues with un-rewritten text.
    """


class BackendError(Exception):
    """Provider responded but with a non-success status (auth, quota, 5xx).

    The bridge maps this to HTTP 502 ``backend_unavailable``; the runner records
    the error in ``PipelineResult.notes`` and continues with un-rewritten text.
    """


@runtime_checkable
class Backend(Protocol):
    """Narrow protocol every adapter implements.

    Adapters are dataclass-like value objects: cheap to construct, no IO at
    init time. All IO is in ``rewrite()`` and (cheaply) ``is_available()``.
    """

    name: str
    model: str

    def is_available(self) -> bool:
        """Cheap health check; must NOT make a billed request.

        For Ollama: hit ``/api/tags``. For hosted providers: just check that an
        API key is configured. The bridge's ``/v1/health`` route uses this to
        report ``backends_configured``.
        """

    def rewrite(
        self,
        text: str,
        *,
        system: str,
        model: str | None = None,
        timeout: float = 120.0,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Send ``system`` as the system message and ``text`` wrapped in
        ``<text>...</text>`` as the user message. Return the rewritten text
        with leading/trailing chatter stripped.

        Implementations should call :func:`clean_output` before returning.
        """


# ---------------------------------------------------------------------------
# Output post-processing (extracted from pipeline/stage2_llm_rewrite._strip_chatter)
# ---------------------------------------------------------------------------

_LEADING_CHATTER = re.compile(
    r"^\s*(?:here(?:'s| is)\s+(?:the\s+)?(?:rewrit|edit|revis|updat)[^\n:]*?:\s*"
    r"|sure[!,.]?\s+(?:here[^\n]*:\s*)?"
    r"|certainly[!,.]?\s+(?:here[^\n]*:\s*)?"
    r"|of course[!,.]?\s+(?:here[^\n]*:\s*)?"
    r"|okay[!,.]?\s+(?:here[^\n]*:\s*)?"
    r"|here you go[!,.]?\s*"
    r")",
    re.IGNORECASE,
)
_TRAILING_APOLOGY = re.compile(
    r"\n+\s*(?:i\s+hope\s+this\s+helps|let\s+me\s+know|hope\s+that\s+helps)[^\n]*$",
    re.IGNORECASE,
)
_TEXT_TAG = re.compile(r"<\s*/?\s*text[^>]*>", re.IGNORECASE)


def clean_output(reply: str) -> str:
    """Strip the common chatter prefixes/fence wrappers/`<text>` tags.

    Public so every adapter's ``rewrite()`` can call it before returning.
    """
    out = reply.strip()
    if out.startswith("```"):
        first_nl = out.find("\n")
        if first_nl != -1:
            out = out[first_nl + 1:]
        if out.endswith("```"):
            out = out[:-3]
    out = _LEADING_CHATTER.sub("", out, count=1)
    out = _TRAILING_APOLOGY.sub("", out)
    out = _TEXT_TAG.sub("", out)
    return out.strip()


def wrap_user_message(text: str) -> str:
    """Wrap user text in ``<text>...</text>`` so the model is less likely to
    inject chatter."""
    return f"<text>\n{text}\n</text>"


__all__ = [
    "Backend",
    "BackendUnavailable",
    "BackendError",
    "clean_output",
    "wrap_user_message",
]
