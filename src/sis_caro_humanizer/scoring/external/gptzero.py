"""GPTZero free-tier adapter.

Calls the public predict-text endpoint. Honours ``GPTZERO_API_KEY`` if set
(documented free-tier rate limit applies); falls back to a
no-key request which works for short snippets but is quota-limited.

Per V1_4_CONTRACT §4.4: 8 s timeout, never persists the input, logs URL hit
at INFO so the user can audit.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

from . import DetectorResult, DetectorUnavailable, band_for

URL = "https://api.gptzero.me/v2/predict/text"
_LOG = logging.getLogger(__name__)


def detect(text: str, *, timeout: float = 8.0) -> DetectorResult:
    if not text or not text.strip():
        raise DetectorUnavailable("empty text")
    payload = {"document": text}
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    api_key = os.environ.get("GPTZERO_API_KEY", "").strip()
    if api_key:
        headers["x-api-key"] = api_key

    _LOG.info("gptzero: hitting %s (key=%s)", URL, "set" if api_key else "absent")

    req = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise DetectorUnavailable("rate_limited") from exc
        if exc.code in (401, 403):
            raise DetectorUnavailable("unauthorised") from exc
        raise DetectorUnavailable(f"http_{exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DetectorUnavailable(f"network_error: {exc}") from exc

    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise DetectorUnavailable(f"bad_json: {exc}") from exc

    # GPTZero documents/predictions: documents[0].class_probabilities.ai
    docs = data.get("documents") if isinstance(data, dict) else None
    score: float | None = None
    if isinstance(docs, list) and docs and isinstance(docs[0], dict):
        d = docs[0]
        cprobs = d.get("class_probabilities") or {}
        ai = cprobs.get("ai") if isinstance(cprobs, dict) else None
        if isinstance(ai, (int, float)):
            score = float(ai)
        else:
            ag = d.get("completely_generated_prob")
            if isinstance(ag, (int, float)):
                score = float(ag)
    if score is None:
        gen_prob = data.get("completely_generated_prob") if isinstance(data, dict) else None
        if isinstance(gen_prob, (int, float)):
            score = float(gen_prob)
    if score is None:
        raise DetectorUnavailable("unparseable_response")
    score = max(0.0, min(1.0, score))
    return DetectorResult(score=score, band=band_for(score), confidence=None)


__all__ = ["URL", "detect"]
