"""Deterministic-stage runner.

Chains the eight individual transform modules in the canonical order. After
every transform that changes the text, the protected-spans list is rebuilt
so the next transform sees an authoritative snapshot.

See CONTRACTS § 4 for the ordering and the per-module signature.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from .protected import build_protected_spans

if TYPE_CHECKING:
    from ...profile.schema import Profile


@dataclass
class TransformLog:
    transform: str
    site: tuple[int, int]
    before: str
    after: str
    reason: str


# Late imports so each module can `from .runner import TransformLog` without
# circular grief.
from . import (  # noqa: E402
    anti_cluster,
    bluppers,
    em_dashes,
    ghanaian,
    semicolons,
    topic_softener,
    triple_lists,
    vocab_swap,
)


TransformFn = Callable[
    [str, "Profile", random.Random, list[tuple[int, int]]],
    tuple[str, list[TransformLog]],
]


DETERMINISTIC_PIPELINE: list[TransformFn] = [
    em_dashes.apply,
    semicolons.apply,
    triple_lists.apply,
    vocab_swap.apply,
    bluppers.apply,
    topic_softener.apply,
    ghanaian.apply,
    anti_cluster.apply,
]


def _seeded_rng(text: str, profile_seed: int, override: int | None) -> random.Random:
    if override is not None:
        return random.Random(override)
    seed = (hash(text) ^ profile_seed) & 0xFFFFFFFF
    return random.Random(seed)


def run_deterministic(
    text: str, profile: "Profile", *, seed: int | None = None
) -> tuple[str, list[TransformLog]]:
    rng = _seeded_rng(text, profile.seed, seed)
    spans = build_protected_spans(text)
    all_logs: list[TransformLog] = []
    current = text
    for transform in DETERMINISTIC_PIPELINE:
        new_text, logs = transform(current, profile, rng, spans)
        all_logs.extend(logs)
        if new_text != current:
            current = new_text
            spans = build_protected_spans(current)
    return current, all_logs


__all__ = ["DETERMINISTIC_PIPELINE", "TransformLog", "run_deterministic"]
