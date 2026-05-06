"""Sapling AI-detector adapter.

The free demo endpoint at ``api.sapling.ai/api/v1/aidetect`` requires a free
API key (``SAPLING_API_KEY``). Without one we mark the detector unavailable
rather than guess.

Per V1_4_CONTRACT §4.4: 8 s timeout, never persists the input, logs URL hit
at INFO.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

from . import DetectorResult, DetectorUnavailable, band_for

URL = "https://api.sapling.ai/api/v1/aidetect"
_LOG = logging.getLogger(__name__)


def detect(text: str, *, timeout: float = 8.0) -> DetectorResult:
    if not text or not text.strip():
        raise DetectorUnavailable("empty text")
    api_key = os.environ.get("SAPLING_API_KEY", "").strip()
    if not api_key:
        raise DetectorUnavailable("missing_api_key (set SAPLING_API_KEY)")

    payload = {"key": api_key, "text": text}
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    _LOG.info("sapling: hitting %s (key=set)", URL)

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

    score = data.get("score") if isinstance(data, dict) else None
    if not isinstance(score, (int, float)):
        raise DetectorUnavailable("unparseable_response")
    score = max(0.0, min(1.0, float(score)))
    return DetectorResult(score=score, band=band_for(score), confidence=None)


__all__ = ["URL", "detect"]
