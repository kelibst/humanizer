"""FastAPI bridge daemon for the Google Docs add-in and the VS Code extension.

See ``plan/BRIDGE_CONTRACT.md`` for the locked v1.2 HTTP contract and
``plan/V1_3_CONTRACT.md`` for the v1.3 research-aid additions. Every route in
both contracts is implemented in this module.

The app is constructed via :func:`create_app` so tests can pass an explicit
``token`` and the production runner (see :mod:`runner`) can build it with the
on-disk persistent token.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..backends import list_available
from ..pipeline.runner import run_pipeline
from ..scoring.risk import ai_risk_score
from .auth import constant_time_compare, extract_bearer
from .helpers import _code_for_status
from .routes.benchmark import make_router as _make_benchmark_router
from .routes.citations_mgmt import make_router as _make_citations_mgmt_router
from .routes.core import make_router as _make_core_router
from .routes.research import make_router as _make_research_router
from .routes.review import make_router as _make_review_router
from .routes.streaming import make_router as _make_streaming_router
from .routes.zotero import make_router as _make_zotero_router
from .routes.advanced import make_router as _make_voice_diff_router

VERSION = "1.6.0"

ALLOWED_ORIGINS = ("https://docs.google.com", "https://script.google.com")

# Module-level executor reused by /v1/suggest and /v1/transform/stream.
_executor = ThreadPoolExecutor(max_workers=4)


def create_app(
    *,
    token: str,
    pipeline_runner: Callable[..., Any] | None = None,
    score_runner: Callable[..., Any] | None = None,
    available_backends: Callable[[], list[str]] | None = None,
    suggest_workers: int = 3,
) -> FastAPI:
    """Build the FastAPI app.

    All injection seams take callables so tests can monkeypatch them without
    importing heavy dependencies (Ollama, real LLM calls, etc.).
    """
    pipeline_runner = pipeline_runner or run_pipeline
    score_runner = score_runner or ai_risk_score
    available_backends = available_backends or list_available

    app = FastAPI(title="humanizer-bridge", version=VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ALLOWED_ORIGINS),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,
    )

    async def _require_token(request: Request) -> None:
        provided = extract_bearer(request.headers.get("Authorization"))
        if not provided or not constant_time_compare(provided, token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "unauthorised", "detail": "invalid or missing bearer token"},
            )

    auth_dep = Depends(_require_token)

    @app.exception_handler(HTTPException)
    async def _http_exc(_: Request, exc: HTTPException) -> JSONResponse:
        body = exc.detail
        if not isinstance(body, dict):
            body = {"error": _code_for_status(exc.status_code), "detail": str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": "internal", "detail": str(exc)},
        )

    app.include_router(
        _make_core_router(pipeline_runner, score_runner, available_backends, _executor, auth_dep)
    )
    app.include_router(_make_research_router(auth_dep))
    app.include_router(_make_benchmark_router(score_runner, auth_dep))
    app.include_router(_make_citations_mgmt_router(auth_dep))
    app.include_router(_make_review_router(score_runner, auth_dep))
    app.include_router(_make_streaming_router(pipeline_runner, _executor, auth_dep))
    app.include_router(_make_zotero_router(auth_dep))
    app.include_router(_make_voice_diff_router(auth_dep))

    return app


__all__ = ["VERSION", "ALLOWED_ORIGINS", "create_app"]
