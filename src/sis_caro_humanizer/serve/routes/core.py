"""/health, /profiles, /export/docx, /score, /transform, /suggest routes."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from ...backends import BACKEND_NAMES
from ...pipeline.runner import ALL_STAGES
from ..helpers import (
    _apply_backend_override,
    _list_profiles_payload,
    _normalize_stages,
    _resolve_profile_or_default,
    _serialise_pipeline_result,
    _to_jsonable,
)
from ..models.v12 import ScoreBody, SuggestBody, TransformBody
from ..models.v156 import ExportDocxBody, ExportPdfBody

VERSION = "1.5.0"


def make_router(
    pipeline_runner: Callable[..., Any],
    score_runner: Callable[..., Any],
    available_backends: Callable[[], list[str]],
    executor: ThreadPoolExecutor,
    auth_dep: Any,
) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/health")
    async def health(_: None = auth_dep) -> dict[str, Any]:
        configured = available_backends()
        return {
            "ok": True,
            "version": VERSION,
            "backends_available": list(BACKEND_NAMES),
            "backends_configured": configured,
        }

    @router.get("/v1/profiles")
    async def profiles(_: None = auth_dep) -> dict[str, Any]:
        return _list_profiles_payload()

    @router.post("/v1/export/docx")
    async def export_docx(body: ExportDocxBody, _: None = auth_dep) -> dict[str, Any]:
        """Write *text* as a new .docx at *output_path* using new_docx_from_markdown."""
        try:
            from ...docx_bridge import new_docx_from_markdown
        except ImportError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "dependency_missing", "detail": str(exc)},
            ) from exc
        try:
            new_docx_from_markdown(body.text, Path(body.output_path))
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"error": "export_failed", "detail": str(exc)},
            ) from exc
        return {"ok": True, "path": body.output_path}

    @router.post("/v1/export/pdf")
    async def export_pdf(body: ExportPdfBody, _: None = auth_dep) -> dict[str, Any]:
        """Write *text* as a linked PDF via LibreOffice or pandoc."""
        try:
            from ...docx_bridge import export_as_pdf
        except ImportError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "dependency_missing", "detail": str(exc)},
            ) from exc
        try:
            export_as_pdf(body.text, Path(body.output_path))
        except RuntimeError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "tool_missing", "detail": str(exc)},
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={"error": "export_failed", "detail": str(exc)},
            ) from exc
        return {"ok": True, "path": body.output_path}

    @router.post("/v1/score")
    async def score(body: ScoreBody, _: None = auth_dep) -> dict[str, Any]:
        try:
            prof = _resolve_profile_or_default(body.profile)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "not_found", "detail": str(exc)},
            ) from exc
        report = score_runner(body.text, prof)
        return _to_jsonable(report)

    @router.post("/v1/transform")
    async def transform(body: TransformBody, _: None = auth_dep) -> dict[str, Any]:
        try:
            prof = _resolve_profile_or_default(body.profile)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "not_found", "detail": str(exc)},
            ) from exc
        prof = _apply_backend_override(prof, body.backend, body.model)
        try:
            stages = _normalize_stages(body.stages)
            result = pipeline_runner(
                body.text,
                prof,
                stages=stages,
                model=body.model,
                seed=body.seed,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": str(exc)},
            ) from exc

        # If the runner reports the LLM stage failed AND it was requested,
        # surface that as 502 so the sidebar can fall back per BRIDGE_CONTRACT
        # §3.4. The runner already swallowed the exception into ``notes``.
        if "llm" in stages and not result.llm_used:
            llm_note = next(
                (n for n in result.notes if n.startswith("llm")),
                None,
            )
            # Only escalate hard backend errors; transient ollama-not-running is
            # ALSO a 502 per the contract because the sidebar needs to know to
            # retry without LLM.
            if llm_note:
                raise HTTPException(
                    status_code=502,
                    detail={
                        "error": "backend_unavailable",
                        "detail": llm_note,
                    },
                )

        return _serialise_pipeline_result(result)

    @router.post("/v1/suggest")
    async def suggest(body: SuggestBody, _: None = auth_dep) -> dict[str, Any]:
        try:
            prof = _resolve_profile_or_default(body.profile)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "not_found", "detail": str(exc)},
            ) from exc
        prof = _apply_backend_override(prof, body.backend, body.model)

        n = body.n
        seeds = list(range(1, n + 1))

        def _one(seed: int) -> dict[str, Any]:
            t0 = time.monotonic()
            res = pipeline_runner(
                body.text,
                prof,
                stages=ALL_STAGES,
                model=body.model,
                seed=seed,
            )
            elapsed = time.monotonic() - t0
            return {
                "text": res.output,
                "score": res.post_score.score if res.post_score else None,
                "seed": seed,
                "elapsed_seconds": elapsed,
            }

        suggest_workers = 3
        with ThreadPoolExecutor(max_workers=min(suggest_workers, max(1, n))) as ex:
            candidates = list(ex.map(_one, seeds))

        input_score = score_runner(body.text, prof).score
        return {"candidates": candidates, "input_score": input_score}

    return router
