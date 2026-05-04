"""Top-level pipeline orchestrator.

Stitches every stage together according to CONTRACTS.md § 2 / "Pipeline runner".

The runner is a *library* function: it must not write to stdout. The CLI is the
only place that prints. When the LLM stage is unreachable we record
``llm_used=False`` and pass the un-rewritten text to the next stage.

Stage 3 (deterministic post-edits) is owned by Agent A and lives in
``pipeline.stage3_deterministic.runner``. We import it lazily so that the rest
of the pipeline (and ``humanize --help``) keeps working while that subsystem is
still under construction.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable

from ..profile.schema import Profile
from ..scoring.risk import ScoreReport
from .stage1_prescan import prescan
from .stage5_postscan import postscan

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from ..grammar.runner import GrammarReport

ALL_STAGES: tuple[str, ...] = ("prescan", "llm", "determ", "grammar", "postscan")


@dataclass
class TransformLog:
    """Mirror of the dataclass Agent A defines in stage3 - duplicated here so
    the runner can construct an empty list without importing Agent A's module
    when stage3 is disabled or unavailable."""

    transform: str
    site: tuple[int, int]
    before: str
    after: str
    reason: str


@dataclass
class PipelineResult:
    input: str
    output: str
    pre_score: ScoreReport
    post_score: ScoreReport
    llm_used: bool
    deterministic_log: list[Any] = field(default_factory=list)
    grammar: "GrammarReport | None" = None
    elapsed_seconds: float = 0.0
    notes: list[str] = field(default_factory=list)


def _normalize_stages(stages: Iterable[str]) -> tuple[str, ...]:
    seq = tuple(stages)
    if len(seq) == 1 and seq[0] == "all":
        return ALL_STAGES
    out: list[str] = []
    for s in seq:
        if s == "all":
            for x in ALL_STAGES:
                if x not in out:
                    out.append(x)
            continue
        if s not in ALL_STAGES:
            raise ValueError(
                f"unknown stage {s!r}; expected one of {ALL_STAGES + ('all',)}"
            )
        if s not in out:
            out.append(s)
    return tuple(out)


def _run_llm(text: str, profile: Profile, model: str | None) -> tuple[str, bool, str | None]:
    """Returns (text, llm_used, note). ``note`` carries any downgrade reason."""
    try:
        from .stage2_llm_rewrite import llm_rewrite
        from ..ollama_client import OllamaUnavailable
    except Exception as exc:  # pragma: no cover - import paths are stable
        return text, False, f"llm import failed: {exc}"

    try:
        rewritten = llm_rewrite(text, profile, model=model)
    except OllamaUnavailable as exc:
        return text, False, f"llm unavailable: {exc}"
    except Exception as exc:  # noqa: BLE001 - any model error must downgrade, not crash
        return text, False, f"llm error: {exc}"
    return rewritten, True, None


def _run_determ(
    text: str, profile: Profile, seed: int | None
) -> tuple[str, list[Any], str | None]:
    """Lazy import of Agent A's deterministic runner. If the module is not yet
    on disk, downgrade to a no-op."""
    try:
        from .stage3_deterministic.runner import run_deterministic  # type: ignore
    except Exception as exc:
        return text, [], f"deterministic stage unavailable: {exc}"
    try:
        new_text, log = run_deterministic(text, profile, seed=seed)
    except Exception as exc:  # noqa: BLE001
        return text, [], f"deterministic stage error: {exc}"
    return new_text, list(log), None


def _run_grammar(text: str, profile: Profile) -> tuple["GrammarReport | None", str | None]:
    try:
        from ..grammar.runner import run_grammar
    except Exception as exc:  # pragma: no cover
        return None, f"grammar import failed: {exc}"
    try:
        return run_grammar(text, profile), None
    except Exception as exc:  # noqa: BLE001
        return None, f"grammar stage error: {exc}"


def run_pipeline(
    text: str,
    profile: Profile,
    *,
    stages: Iterable[str] = ALL_STAGES,
    model: str | None = None,
    seed: int | None = None,
) -> PipelineResult:
    """Execute the requested stages and return a :class:`PipelineResult`.

    The runner *never* raises for an individual stage failure: missing tools or
    models surface as a downgrade note plus an unchanged text passed to the
    next stage. The caller decides how to render the notes.
    """
    started = time.monotonic()
    active = _normalize_stages(stages)

    notes: list[str] = []
    pre: ScoreReport | None = None
    post: ScoreReport | None = None
    llm_used = False
    determ_log: list[Any] = []
    grammar_report: "GrammarReport | None" = None

    current = text

    if "prescan" in active:
        pre = prescan(current, profile)

    if "llm" in active:
        current, llm_used, note = _run_llm(current, profile, model)
        if note:
            notes.append(note)

    if "determ" in active:
        current, log, note = _run_determ(current, profile, seed)
        determ_log.extend(log)
        if note:
            notes.append(note)

    if "grammar" in active:
        grammar_report, note = _run_grammar(current, profile)
        if note:
            notes.append(note)

    if "postscan" in active:
        post = postscan(current, profile)

    # If only one of pre/post ran, mirror the value so callers always see a
    # populated ScoreReport. If neither ran, fall back to scoring once on the
    # un-mutated input/output so PipelineResult invariants hold.
    if pre is None and post is None:
        pre = prescan(text, profile)
        post = prescan(current, profile)
    elif pre is None:
        pre = post  # type: ignore[assignment]
    elif post is None:
        post = pre

    elapsed = time.monotonic() - started
    return PipelineResult(
        input=text,
        output=current,
        pre_score=pre,  # type: ignore[arg-type]
        post_score=post,  # type: ignore[arg-type]
        llm_used=llm_used,
        deterministic_log=determ_log,
        grammar=grammar_report,
        elapsed_seconds=elapsed,
        notes=notes,
    )


__all__ = ["PipelineResult", "TransformLog", "run_pipeline", "ALL_STAGES"]
