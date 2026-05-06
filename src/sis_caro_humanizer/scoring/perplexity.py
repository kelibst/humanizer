"""Perplexity feature for the AI-risk score (v1.4).

Lower per-token cross-entropy (= lower perplexity) is a strong AI tell — modern
LLMs produce text that the underlying language model finds *predictable*. This
module computes mean per-token cross-entropy in two paths:

1. **Ollama logprobs** (preferred). See :func:`ollama_client.logprobs`. If
   the daemon or model does not expose logprobs we fall through.
2. **DistilGPT2** via :mod:`transformers` (lazy import). Runs on CPU; ~80 MB
   model download cached by Hugging Face. If neither path succeeds we return
   ``value=0.0`` with ``note='perplexity_unavailable'`` so the rest of the
   weighted score still produces a sensible number.

Mapping from cross-entropy to feature value is per V1_4_CONTRACT §3.4:

    score_norm = clamp(1.0 - (mean_xent - LOW_PPL) / (HIGH_PPL - LOW_PPL), 0, 1)

Note: we compare *natural-log* cross-entropy (nats per token). DistilGPT2's
``loss`` is already in nats. Constants ``LOW_PPL`` / ``HIGH_PPL`` are the
calibration anchors from the contract.
"""
from __future__ import annotations

import logging
import math
import os
from typing import TYPE_CHECKING

from .risk import FeatureContribution

if TYPE_CHECKING:  # pragma: no cover - only for type hints
    from ..profile.schema import Profile

_LOG = logging.getLogger(__name__)


# Calibration anchors (CONTRACT §3.4). Lower is more AI-like.
LOW_PPL = 2.4
HIGH_PPL = 5.5
PERPLEXITY_WEIGHT = 0.36

# DistilGPT2 fallback cap.
_MAX_TOKENS = 1024

# Cached fallback model + tokenizer; lazily populated on first use.
_FALLBACK: tuple[object, object] | None = None
_FALLBACK_FAILED = False

# Per-process latch: once Ollama tells us it doesn't expose logprobs (or the
# call times out), don't retry — that wasted ~30 s every score call. Tests
# that need to reset this can ``monkeypatch.setattr(perplexity_module,
# "_OLLAMA_LATCHED", False)``.
_OLLAMA_LATCHED = False


class LogprobsNotSupported(Exception):
    """Raised by :func:`ollama_client.logprobs` when the runtime cannot
    return per-token logprobs (older Ollama versions, non-supporting models)."""


def _ollama_xent(text: str, model: str) -> float | None:
    """Return mean per-token cross-entropy via Ollama logprobs, or ``None``
    if the path is unavailable. Never raises.

    Latches the "not supported" outcome for the rest of the process so
    repeated score calls don't pay the per-request timeout penalty.
    """
    global _OLLAMA_LATCHED
    if _OLLAMA_LATCHED:
        return None
    try:
        from ..ollama_client import OllamaUnavailable, logprobs

        lp = logprobs(text, model=model, timeout=5.0)
    except LogprobsNotSupported:
        _OLLAMA_LATCHED = True
        return None
    except OllamaUnavailable:
        _OLLAMA_LATCHED = True
        return None
    except Exception as exc:  # noqa: BLE001 - explicit fallthrough
        _LOG.debug("perplexity: ollama logprobs raised %r; falling through", exc)
        _OLLAMA_LATCHED = True
        return None
    if not lp:
        _OLLAMA_LATCHED = True
        return None
    # logprobs come back as natural-log probabilities (negative numbers).
    # cross-entropy = -mean(logprob).
    return -sum(lp) / len(lp)


def _load_fallback() -> tuple[object, object] | None:
    """Lazy-import DistilGPT2; cache on success; latch on failure."""
    global _FALLBACK, _FALLBACK_FAILED
    if _FALLBACK is not None:
        return _FALLBACK
    if _FALLBACK_FAILED:
        return None
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
    except Exception as exc:  # noqa: BLE001
        _LOG.debug("perplexity: transformers unavailable (%r)", exc)
        _FALLBACK_FAILED = True
        return None
    try:
        tok = AutoTokenizer.from_pretrained("distilgpt2")
        mdl = AutoModelForCausalLM.from_pretrained("distilgpt2")
        mdl.eval()  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        _LOG.debug("perplexity: distilgpt2 load failed (%r)", exc)
        _FALLBACK_FAILED = True
        return None
    _FALLBACK = (tok, mdl)
    return _FALLBACK


def _distilgpt2_xent(text: str) -> float | None:
    """Compute mean per-token cross-entropy (nats) via DistilGPT2; sliding
    window for inputs longer than :data:`_MAX_TOKENS`. Returns ``None`` if
    transformers is not installed or the model could not be loaded.
    """
    bundle = _load_fallback()
    if bundle is None:
        return None
    tok, mdl = bundle
    try:
        import torch  # type: ignore
    except Exception:  # noqa: BLE001
        return None

    enc = tok(text, return_tensors="pt", truncation=False)  # type: ignore[operator]
    input_ids = enc["input_ids"][0]
    if input_ids.numel() < 2:
        return None

    # Slide a 1024-token window in 512-step strides; aggregate by summed
    # negative log-likelihood over total non-overlapping tokens.
    nll_sum = 0.0
    n_tokens = 0
    stride = _MAX_TOKENS // 2
    end = int(input_ids.size(0))
    for start in range(0, end, stride):
        chunk = input_ids[start: start + _MAX_TOKENS].unsqueeze(0)
        if chunk.size(1) < 2:
            break
        with torch.no_grad():  # type: ignore[attr-defined]
            out = mdl(chunk, labels=chunk)  # type: ignore[operator]
        loss = float(out.loss.detach())
        # `loss` is mean over (chunk_len - 1) tokens.
        n = int(chunk.size(1)) - 1
        nll_sum += loss * n
        n_tokens += n
        if chunk.size(1) < _MAX_TOKENS:
            break
    if n_tokens == 0:
        return None
    return nll_sum / n_tokens


def _xent_to_value(mean_xent: float) -> float:
    if HIGH_PPL <= LOW_PPL:
        return 0.0
    raw = 1.0 - (mean_xent - LOW_PPL) / (HIGH_PPL - LOW_PPL)
    return max(0.0, min(1.0, raw))


def perplexity_feature(text: str, profile: "Profile" | None = None) -> FeatureContribution:
    """Compute the perplexity feature contribution.

    Returns ``value=0.0, examples=["perplexity_unavailable"]`` when neither the
    Ollama nor the DistilGPT2 path succeeds, so the rest of the weighted score
    still produces a well-defined number.
    """
    text = text or ""
    # Hard kill-switch for tests / users who don't want any network calls.
    if os.environ.get("HUMANIZE_DISABLE_PERPLEXITY"):
        return FeatureContribution(
            name="perplexity",
            value=0.0,
            weight=PERPLEXITY_WEIGHT,
            detail="perplexity_unavailable (HUMANIZE_DISABLE_PERPLEXITY set)",
            examples=["perplexity_unavailable"],
        )
    # Need a few tokens for a meaningful estimate.
    if len(text.strip()) < 12:
        return FeatureContribution(
            name="perplexity",
            value=0.0,
            weight=PERPLEXITY_WEIGHT,
            detail="too short for perplexity",
            examples=[],
        )

    model_override: str | None = None
    if profile is not None:
        model_override = getattr(profile, "perplexity_model", None)

    # 1. Ollama path.
    try:
        from ..config import DEFAULT_MODEL
    except Exception:  # noqa: BLE001 - test harness may stub config
        DEFAULT_MODEL = "gemma3:4b"
    chosen_model = model_override or DEFAULT_MODEL

    mean_xent = _ollama_xent(text, model=chosen_model)
    source = "ollama"

    # 2. DistilGPT2 fallback.
    if mean_xent is None:
        mean_xent = _distilgpt2_xent(text)
        source = "distilgpt2"

    # 3. Graceful no-op.
    if mean_xent is None:
        return FeatureContribution(
            name="perplexity",
            value=0.0,
            weight=PERPLEXITY_WEIGHT,
            detail="perplexity_unavailable",
            examples=["perplexity_unavailable"],
        )

    value = _xent_to_value(mean_xent)
    ppl = math.exp(mean_xent) if mean_xent < 50 else float("inf")
    detail = f"mean cross-entropy {mean_xent:.2f} nats (PPL {ppl:.2f}) via {source}"
    return FeatureContribution(
        name="perplexity",
        value=value,
        weight=PERPLEXITY_WEIGHT,
        detail=detail,
        examples=[],
    )


__all__ = [
    "HIGH_PPL",
    "LOW_PPL",
    "LogprobsNotSupported",
    "PERPLEXITY_WEIGHT",
    "perplexity_feature",
]
