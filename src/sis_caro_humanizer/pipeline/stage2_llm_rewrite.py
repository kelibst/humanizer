"""Stage 2: LLM rewrite via the configured backend.

Historically this stage spoke directly to Ollama. v1.2 rewires it through the
multi-backend registry (``sis_caro_humanizer.backends``) so the same call site
works against Ollama, Anthropic, OpenAI, or Gemini, selected via
``profile.backend`` / ``profile.backend_config``.

For runner compatibility the legacy ``OllamaUnavailable`` exception name is
preserved: any :class:`backends.BackendUnavailable` is wrapped in it before
bubbling up. ``pipeline/runner.py`` already catches ``OllamaUnavailable`` and
downgrades, so no runner edit is needed.
"""
from __future__ import annotations

from ..backends import BackendError, BackendUnavailable, clean_output, get_backend
from ..config import DEFAULT_MODEL
from ..ollama_client import OllamaUnavailable
from ..profile.schema import Profile


def _build_system_prompt(profile: Profile) -> str:
    p = profile

    never = ", ".join(p.vocabulary.never_use[:18]) or "(none)"
    swaps_lines: list[str] = []
    for src, alts in list(p.vocabulary.preferred_swaps.items())[:14]:
        swaps_lines.append(f"  - {src} -> {', '.join(alts[:3])}")
    swaps_block = "\n".join(swaps_lines) if swaps_lines else "  (no required swaps)"

    forbidden_openers = "; ".join(p.forbidden_openers[:10]) or "(none)"

    shape = p.sentence_shape
    mean_words = shape.mean_words
    pct_short = int(shape.pct_short_lt10 * 100)
    pct_long = int(shape.pct_long_gt35 * 100)

    register = p.domain_register
    dialect = p.dialect

    return (
        "You are a careful copy editor preparing English prose to match a specific human "
        "writer's voice. You will receive text inside <text>...</text> tags. Rewrite the text "
        "so it carries the voice profile below, then return ONLY the rewritten text - no "
        "preface, no explanation, no markdown fences, no quoted block.\n"
        "\n"
        f"Register: {register}.\n"
        f"Dialect: {dialect} English (use spelling and idiom for that dialect).\n"
        "\n"
        "Never use these words or phrases:\n"
        f"  {never}\n"
        "\n"
        "When you encounter the word on the left, prefer one of the alternatives:\n"
        f"{swaps_block}\n"
        "\n"
        "Do NOT open paragraphs with any of the following: "
        f"{forbidden_openers}.\n"
        "\n"
        "Punctuation rules (hard):\n"
        "  - No em-dashes (-) or en-dashes (-) anywhere. Use a comma, full stop, "
        "or parentheses instead.\n"
        "  - No semicolons in flowing prose. Split into two sentences.\n"
        "  - Avoid the cadence of three-item lists 'X, Y, and Z'; vary to two items, "
        "four items, or rephrase.\n"
        "\n"
        "Sentence shape:\n"
        f"  - Aim for an average of about {mean_words:.0f} words per sentence.\n"
        f"  - About {pct_short}% of sentences should be under 10 words.\n"
        f"  - About {pct_long}% of sentences should be over 30 words.\n"
        "  - Vary structure: mix simple, compound, and complex sentences.\n"
        "  - Do not start every paragraph with a perfect 12-22 word topic sentence.\n"
        "\n"
        "Voice notes:\n"
        "  - Mix formal hedges (may, might, suggests) with informal ones "
        "(seems like, hard to say) at roughly equal rates.\n"
        "  - Preserve all factual claims, citations, numbers, names, and quoted material exactly.\n"
        "  - Preserve markdown structure (headings, lists, code blocks, tables, citations).\n"
        "  - Do not add new content, examples, or transitions the source did not have.\n"
        "\n"
        "Return only the rewritten text."
    )


def _strip_chatter(reply: str) -> str:
    """Backwards-compat re-export.

    Older tests / external callers imported ``_strip_chatter`` from this
    module. The implementation now lives in :func:`backends.base.clean_output`.
    """
    return clean_output(reply)


def llm_rewrite(
    text: str,
    profile: Profile,
    *,
    model: str | None = None,
    host: str | None = None,
    timeout: float = 600.0,
) -> str:
    """Rewrite ``text`` to match ``profile``.

    Routes through the backend named by ``profile.backend``. Raises
    :class:`OllamaUnavailable` (the legacy name) for any unreachable provider so
    ``pipeline/runner.py``'s existing catch behaviour continues to work without
    edits.
    """
    if not text.strip():
        return text

    config = dict(profile.backend_config)
    # Allow the CLI's ``--host`` flag to override the Ollama host without
    # editing the profile YAML.
    if host and profile.backend == "ollama" and "host" not in config:
        config["host"] = host

    try:
        backend = get_backend(profile.backend, config=config)
    except ValueError as exc:
        # Misconfigured profile — surface as unavailable so the runner downgrades.
        raise OllamaUnavailable(f"unknown backend {profile.backend!r}: {exc}") from exc

    if not backend.is_available():
        raise OllamaUnavailable(
            f"backend {profile.backend!r} not available "
            "(API key missing or daemon down)"
        )

    system = _build_system_prompt(profile)
    chosen_model = model or config.get("model") or (
        DEFAULT_MODEL if profile.backend == "ollama" else None
    )

    try:
        rewritten = backend.rewrite(
            text,
            system=system,
            model=chosen_model,
            timeout=timeout,
        )
    except BackendUnavailable as exc:
        raise OllamaUnavailable(str(exc)) from exc
    except BackendError as exc:
        # The runner only knows about OllamaUnavailable; widen the error so a
        # billed-but-failed call still downgrades cleanly.
        raise OllamaUnavailable(f"{profile.backend} error: {exc}") from exc

    if not rewritten:
        raise OllamaUnavailable("LLM returned empty rewrite after stripping chatter")
    return rewritten


__all__ = ["llm_rewrite"]
