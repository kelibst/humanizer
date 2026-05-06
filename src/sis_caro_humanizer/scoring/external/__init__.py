"""External AI-detector adapters (v1.4).

Each module exposes ``detect(text, *, timeout=8.0) -> DetectorResult`` and may
raise :class:`DetectorUnavailable` on transport / authentication / quota
failures. The CLI and the ``/v1/benchmark`` daemon route call these
best-effort: a single failure does not abort the batch.

Adapters never persist the input text. URL hits are logged at INFO so the
user can audit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class DetectorResult:
    score: float
    band: str  # "low" | "medium" | "high"
    confidence: float | None = None


class DetectorUnavailable(Exception):
    """Raised by an adapter when the detector is unreachable, returned an
    error, was rate-limited, or requires an API key that is not set.

    The string form of the exception is what the CLI / route surfaces in the
    ``error`` field.
    """


class Detector(Protocol):
    def detect(self, text: str, *, timeout: float = 8.0) -> DetectorResult: ...


def band_for(score: float) -> str:
    if score < 0.34:
        return "low"
    if score < 0.67:
        return "medium"
    return "high"


def get_detector(name: str) -> "Detector":
    """Look up an adapter module by short name. Raises ``KeyError`` for an
    unknown name."""
    name = (name or "").lower().strip()
    if name == "gptzero":
        from . import gptzero
        return gptzero  # type: ignore[return-value]
    if name == "sapling":
        from . import sapling
        return sapling  # type: ignore[return-value]
    if name == "zerogpt":
        from . import zerogpt
        return zerogpt  # type: ignore[return-value]
    raise KeyError(f"unknown detector {name!r}")


KNOWN_DETECTORS = ("gptzero", "sapling", "zerogpt")


__all__ = [
    "Detector",
    "DetectorResult",
    "DetectorUnavailable",
    "KNOWN_DETECTORS",
    "band_for",
    "get_detector",
]
