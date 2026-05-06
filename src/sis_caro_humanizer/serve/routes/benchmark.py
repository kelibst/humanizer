"""/v1/research/templates, /v1/research/prompt, /v1/research/inspect,
/v1/research/reviewer, /v1/llm/run, /v1/benchmark routes."""
from __future__ import annotations

import time
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request

from ...backends import BackendError, BackendUnavailable, get_backend
from ...research.inspector import inspect_section
from ...research.prompts import list_templates as _list_templates
from ...research.prompts import render as _render_prompt
from ...scoring.external import DetectorUnavailable, get_detector
from ..helpers import _resolve_profile_or_default
from ..models.v14 import (
    BenchmarkBody,
    InspectBody,
    LlmRunBody,
    MAX_TEXT_PROMPT,
    RenderPromptBody,
    ReviewerBody,
)


def make_router(
    score_runner: Callable[..., Any],
    auth_dep: Any,
) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/research/templates")
    async def list_templates_route(_: None = auth_dep) -> dict[str, Any]:
        templates = _list_templates()
        return {
            "templates": [
                {
                    "id": t.id,
                    "name": t.name,
                    "description": t.description,
                    "fields": [
                        {"name": f.name, "type": f.type, "required": f.required}
                        for f in t.fields
                    ],
                }
                for t in templates
            ]
        }

    @router.post("/v1/research/prompt")
    async def render_prompt_route(body: RenderPromptBody, _: None = auth_dep) -> dict[str, Any]:
        if len(body.template_id) > 200:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": "template_id too long"},
            )
        # Body cap on the rendered context payload (CONTRACT §9 — 50 KB).
        ctx_size = sum(
            len(str(k)) + len(str(v)) for k, v in (body.context or {}).items()
        )
        if ctx_size > MAX_TEXT_PROMPT:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": "context exceeds 50 KB"},
            )
        try:
            prompt = _render_prompt(body.template_id, body.context or {})
        except KeyError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": str(exc)},
            ) from exc
        return {"prompt": prompt, "char_count": len(prompt)}

    @router.post("/v1/research/inspect")
    async def inspect_route(body: InspectBody, _: None = auth_dep) -> dict[str, Any]:
        try:
            findings = inspect_section(body.section_text, body.section_type)
        except KeyError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": str(exc)},
            ) from exc
        return {
            "findings": [
                {
                    "name": f.name,
                    "issue": f.issue,
                    "suggestion": f.suggestion,
                    "prompt": f.prompt,
                }
                for f in findings
            ]
        }

    @router.post("/v1/research/reviewer")
    async def reviewer_route(body: ReviewerBody, _: None = auth_dep) -> dict[str, Any]:
        template_id = (
            "reviewer_1_methodology" if body.persona == "r1" else "reviewer_2_framing"
        )
        try:
            prompt = _render_prompt(template_id, {"full_text": body.full_text})
        except KeyError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": str(exc)},
            ) from exc
        return {"prompt": prompt}

    @router.post("/v1/llm/run")
    async def llm_run_route(body: LlmRunBody, _: None = auth_dep) -> dict[str, Any]:
        try:
            backend = get_backend(body.backend)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": str(exc)},
            ) from exc
        if not backend.is_available():
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "backend_unavailable",
                    "detail": f"backend {body.backend!r} is not configured / reachable",
                },
            )
        t0 = time.monotonic()
        try:
            output = backend.rewrite(
                body.prompt,
                system="",
                model=body.model,
                timeout=120.0,
            )
        except (BackendUnavailable, BackendError) as exc:
            raise HTTPException(
                status_code=502,
                detail={"error": "backend_unavailable", "detail": str(exc)},
            ) from exc
        elapsed = time.monotonic() - t0
        return {"output": output, "elapsed_seconds": elapsed}

    @router.post("/v1/benchmark")
    async def benchmark_route(
        body: BenchmarkBody, request: Request, _: None = auth_dep
    ) -> dict[str, Any]:
        external_header = request.headers.get("X-External-Benchmark", "").strip().lower()
        external_enabled = external_header == "yes"
        if not external_enabled and body.detectors:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "external_disabled",
                    "detail": "set header X-External-Benchmark: yes to enable external detectors",
                },
            )

        # Local humanizer score.
        try:
            prof = _resolve_profile_or_default(body.profile)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "not_found", "detail": str(exc)},
            ) from exc
        report = score_runner(body.text, prof)
        humanizer_payload = {"score": report.score, "band": report.band}

        external_rows: list[dict[str, Any]] = []
        if external_enabled:
            for name in body.detectors:
                row: dict[str, Any] = {"detector": name}
                t0 = time.monotonic()
                try:
                    detector = get_detector(name)
                    result = detector.detect(body.text, timeout=8.0)
                    row["score"] = result.score
                    row["band"] = result.band
                    row["confidence"] = result.confidence
                    row["elapsed_ms"] = int((time.monotonic() - t0) * 1000)
                except DetectorUnavailable as exc:
                    row["error"] = str(exc)
                except KeyError as exc:
                    row["error"] = f"unknown_detector: {exc}"
                except Exception as exc:  # noqa: BLE001 - best-effort
                    row["error"] = f"internal: {exc}"
                external_rows.append(row)

        return {"humanizer": humanizer_payload, "external": external_rows}

    return router
