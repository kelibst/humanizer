"""Stage 2: LLM rewrite via Ollama.

The model gets a profile-derived system prompt and the input text wrapped in
``<text>...</text>`` tags so it is less likely to add commentary. Any chatty
preface or apology is stripped from the response.
"""
from __future__ import annotations

import re

from ..config import DEFAULT_MODEL
from ..ollama_client import OllamaUnavailable, generate
from ..profile.schema import Profile

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
    out = reply.strip()
    # Strip a single leading/trailing fenced block if the model wrapped output.
    if out.startswith("```"):
        first_nl = out.find("\n")
        if first_nl != -1:
            out = out[first_nl + 1 :]
        if out.endswith("```"):
            out = out[: -3]
    out = _LEADING_CHATTER.sub("", out, count=1)
    out = _TRAILING_APOLOGY.sub("", out)
    out = _TEXT_TAG.sub("", out)
    return out.strip()


def llm_rewrite(
    text: str,
    profile: Profile,
    *,
    model: str | None = None,
    host: str | None = None,
    timeout: float = 600.0,
) -> str:
    """Rewrite ``text`` to match ``profile``. Raises :class:`OllamaUnavailable`."""
    if not text.strip():
        return text

    system = _build_system_prompt(profile)
    user_prompt = f"<text>\n{text}\n</text>"

    chosen_model = model or DEFAULT_MODEL
    kwargs: dict = {
        "model": chosen_model,
        "system": system,
        "timeout": timeout,
        "options": {"temperature": 0.7, "top_p": 0.9},
    }
    if host:
        kwargs["host"] = host

    reply = generate(user_prompt, **kwargs)
    cleaned = _strip_chatter(reply)
    if not cleaned:
        # Model produced only chatter; treat as failure so the runner can downgrade.
        raise OllamaUnavailable("LLM returned empty rewrite after stripping chatter")
    return cleaned
