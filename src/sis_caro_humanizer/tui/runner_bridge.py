"""Adapter between :func:`pipeline.runner.run_pipeline` and Textual screens.

The bridge has three jobs:

1. Run the (potentially seconds-long) pipeline on a worker thread so the
   event loop stays responsive.
2. Translate each :data:`StageEvent` into a Textual :class:`Message` and
   post it to the requesting screen, where it drives reactive widgets
   (the stage strip, the log pane).
3. Hand the final :class:`PipelineResult` back to the screen as one last
   message so the screen can render the diff and post-score gauge.

The screen *always* uses :func:`run_pipeline_in_worker` (never calls
``run_pipeline`` directly) so the cancellation and back-pressure semantics
stay identical across screens.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from textual.app import App
from textual.message import Message
from textual.widget import Widget
from textual.worker import Worker

from ..pipeline.runner import PipelineResult, run_pipeline
from ..profile.schema import Profile
from ..scoring.risk import ScoreReport, ai_risk_score


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


class PipelineEvent(Message):
    """Wraps one ``StageEvent`` tuple posted from the worker thread."""

    def __init__(self, event: tuple) -> None:
        super().__init__()
        self.event = event


class PipelineFinished(Message):
    """Posted exactly once when ``run_pipeline`` returns successfully."""

    def __init__(self, result: PipelineResult) -> None:
        super().__init__()
        self.result = result


class PipelineFailed(Message):
    """Posted when ``run_pipeline`` raised (only for unexpected errors —
    individual stage failures are notes, not exceptions)."""

    def __init__(self, error: BaseException) -> None:
        super().__init__()
        self.error = error


class ScoreFinished(Message):
    """Result of a synchronous-or-worker score call."""

    def __init__(self, score: ScoreReport) -> None:
        super().__init__()
        self.score = score


class ScoreFailed(Message):
    def __init__(self, error: BaseException) -> None:
        super().__init__()
        self.error = error


# ---------------------------------------------------------------------------
# Worker entry points
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransformRequest:
    text: str
    profile: Profile
    stages: tuple[str, ...]
    model: str | None = None
    seed: int | None = None


def _resolve_app(target: Widget | App) -> App:
    if isinstance(target, App):
        return target
    return target.app


def run_pipeline_in_worker(
    target: Widget | App,
    request: TransformRequest,
    *,
    worker_name: str = "humanizer-pipeline",
) -> Worker[PipelineResult]:
    """Kick off ``run_pipeline`` on a Textual worker thread.

    Returns the :class:`Worker` so the caller can cancel it. ``target`` is
    the widget that should receive ``PipelineEvent`` / ``PipelineFinished``
    / ``PipelineFailed`` messages — usually the screen that initiated the
    run.
    """
    app = _resolve_app(target)

    def _emit(event: tuple) -> None:
        # ``call_from_thread`` is safe from a worker thread; it queues the
        # message on the main loop. We post it onto ``target`` so the
        # message-handler lookup hits the screen, not the App.
        try:
            app.call_from_thread(target.post_message, PipelineEvent(event))
        except Exception:  # noqa: BLE001 - never crash the pipeline
            pass

    def _do_work() -> PipelineResult:
        try:
            result = run_pipeline(
                request.text,
                request.profile,
                stages=request.stages,
                model=request.model,
                seed=request.seed,
                on_event=_emit,
            )
        except Exception as exc:  # noqa: BLE001 - hand off to UI
            app.call_from_thread(target.post_message, PipelineFailed(exc))
            raise
        app.call_from_thread(target.post_message, PipelineFinished(result))
        return result

    return app.run_worker(  # type: ignore[return-value]
        _do_work,
        name=worker_name,
        thread=True,
        exclusive=True,
        group="pipeline",
    )


def run_score_in_worker(
    target: Widget | App,
    text: str,
    profile: Profile,
    *,
    worker_name: str = "humanizer-score",
) -> Worker[ScoreReport]:
    """Run :func:`ai_risk_score` off the UI thread."""
    app = _resolve_app(target)

    def _do_work() -> ScoreReport:
        try:
            score = ai_risk_score(text, profile)
        except Exception as exc:  # noqa: BLE001
            app.call_from_thread(target.post_message, ScoreFailed(exc))
            raise
        app.call_from_thread(target.post_message, ScoreFinished(score))
        return score

    return app.run_worker(  # type: ignore[return-value]
        _do_work,
        name=worker_name,
        thread=True,
        exclusive=True,
        group="score",
    )


__all__ = [
    "PipelineEvent",
    "PipelineFailed",
    "PipelineFinished",
    "ScoreFailed",
    "ScoreFinished",
    "TransformRequest",
    "run_pipeline_in_worker",
    "run_score_in_worker",
]


def _stages_default() -> Iterable[str]:  # pragma: no cover - tiny helper
    from ..pipeline.runner import ALL_STAGES

    return ALL_STAGES
