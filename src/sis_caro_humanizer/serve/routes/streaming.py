"""/v1/transform/stream SSE streaming route."""
from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..helpers import (
    _apply_backend_override,
    _normalize_stages,
    _resolve_profile_or_default,
)
from ..models.v12 import TransformBody

# Sentinel for SSE stream termination (CONTRACT v1.5 §8).
_STREAM_DONE = object()


def make_router(
    pipeline_runner: Callable[..., Any],
    executor: ThreadPoolExecutor,
    auth_dep: Any,
) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/transform/stream")
    async def transform_stream(
        body: TransformBody, request: Request, _: None = auth_dep
    ) -> StreamingResponse:
        """Run the pipeline and stream StageEvents as Server-Sent Events.

        CONTRACT v1.5 §3.5 / §8:
        - Uses module-level _executor (ThreadPoolExecutor).
        - on_event callback uses asyncio.run_coroutine_threadsafe to push
          into an asyncio.Queue from the worker thread.
        - Sentinel _STREAM_DONE signals generator loop to stop.
        - Generator yields SSE frames; final 'done' event carries PipelineResult.
        """
        try:
            prof = _resolve_profile_or_default(body.profile)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "not_found", "detail": str(exc)},
            ) from exc
        prof = _apply_backend_override(prof, body.backend, body.model)

        stages = _normalize_stages(body.stages)
        loop = asyncio.get_event_loop()
        q: asyncio.Queue[Any] = asyncio.Queue()

        def _on_event(event: tuple) -> None:
            """Called from the worker thread; puts JSON-serialisable dict on queue."""
            kind = event[0]
            if kind == "stage_start":
                payload = {"type": "stage_start", "stage": event[1]}
            elif kind == "stage_done":
                payload = {"type": "stage_done", "stage": event[1], "elapsed_s": event[2]}
            elif kind == "stage_skipped":
                payload = {"type": "stage_skipped", "stage": event[1], "reason": event[2]}
            elif kind == "determ_step":
                payload = {"type": "determ_step", "step": event[1], "count": event[2]}
            else:
                return
            asyncio.run_coroutine_threadsafe(q.put(payload), loop)

        def _run_in_thread() -> Any:
            try:
                return pipeline_runner(
                    body.text,
                    prof,
                    stages=stages,
                    model=body.model,
                    seed=body.seed,
                    on_event=_on_event,
                )
            finally:
                asyncio.run_coroutine_threadsafe(q.put(_STREAM_DONE), loop)

        future = executor.submit(_run_in_thread)

        async def _generate():
            try:
                while True:
                    try:
                        item = await asyncio.wait_for(q.get(), timeout=120.0)
                    except asyncio.TimeoutError:
                        yield f"data: {json.dumps({'type': 'error', 'message': 'pipeline timeout'})}\n\n"
                        return
                    if item is _STREAM_DONE:
                        break
                    yield f"data: {json.dumps(item)}\n\n"

                # Await the future result and emit 'done' event.
                try:
                    result = future.result(timeout=5.0)
                    done_payload = {
                        "type": "done",
                        "output": result.output,
                        "pre_score": result.pre_score.score if result.pre_score else None,
                        "post_score": result.post_score.score if result.post_score else None,
                        "notes": list(result.notes),
                        "llm_used": result.llm_used,
                    }
                    yield f"data: {json.dumps(done_payload)}\n\n"
                except Exception as exc:
                    yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

        return StreamingResponse(
            _generate(),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return router
