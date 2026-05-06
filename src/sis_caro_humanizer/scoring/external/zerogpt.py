"""ZeroGPT free-tier adapter.

ZeroGPT exposes a public "detectText" endpoint that does not require a key,
but is heavily rate-limited.

Per V1_4_CONTRACT §4.4: 8 s timeout, never persists the input, logs URL hit
at INFO.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from . import DetectorResult, DetectorUnavailable, band_for

URL = "https://api.zerogpt.com/api/detect/detectText"
_LOG = logging.getLogger(__name__)


def detect(text: str, *, timeout: float = 8.0) -> DetectorResult:
    if not text or not text.strip():
        raise DetectorUnavailable("empty text")
    payload = {"input_text": text}
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    _LOG.info("zerogpt: hitting %s", URL)

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

    # ZeroGPT shape: {"data": {"fakePercentage": 0.78, "isHuman": 0.22, ...}}
    inner = data.get("data") if isinstance(data, dict) else None
    score: float | None = None
    if isinstance(inner, dict):
        fp = inner.get("fakePercentage")
        if isinstance(fp, (int, float)):
            # ZeroGPT returns 0–100 percent.
            score = float(fp) / 100.0 if fp > 1.0 else float(fp)
    if score is None:
        raise DetectorUnavailable("unparseable_response")
    score = max(0.0, min(1.0, score))
    return DetectorResult(score=score, band=band_for(score), confidence=None)


__all__ = ["URL", "detect"]
