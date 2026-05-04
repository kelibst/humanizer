"""FastAPI bridge daemon for the Google Docs add-in.

See ``plan/BRIDGE_CONTRACT.md`` for the locked HTTP contract. Every route
described there is implemented in this module.

The app is constructed via :func:`create_app` so tests can pass an explicit
``token`` and the production runner (see :mod:`runner`) can build it with the
on-disk persistent token.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, is_dataclass
from typing import Any, Callable, Iterable

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..backends import BACKEND_NAMES, list_available
from ..pipeline.runner import ALL_STAGES, run_pipeline
from ..profile.loader import resolve_profile
from ..profile.schema import Profile
from ..scoring.risk import ai_risk_score
from .auth import constant_time_compare, extract_bearer

VERSION = "1.2.0"

ALLOWED_ORIGINS = ("https://docs.google.com", "https://script.google.com")

MAX_TEXT_SCORE = 100_000
MAX_TEXT_TRANSFORM = 100_000
MAX_TEXT_SUGGEST = 30_000

VALID_STAGES = set(ALL_STAGES) | {"all"}


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class ScoreBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., max_length=MAX_TEXT_SCORE)
    profile: str | None = None


class TransformBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., max_length=MAX_TEXT_TRANSFORM)
    profile: str | None = None
    stages: list[str] | None = None
    backend: str | None = None
    model: str | None = None
    seed: int | None = None

    @field_validator("stages")
    @classmethod
    def _check_stages(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        for s in v:
            if s not in VALID_STAGES:
                raise ValueError(f"unknown stage {s!r}")
        return v

    @field_validator("backend")
    @classmethod
    def _check_backend(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in BACKEND_NAMES:
            raise ValueError(f"unknown backend {v!r}")
        return v


class SuggestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., max_length=MAX_TEXT_SUGGEST)
    profile: str | None = None
    n: int = Field(default=3, ge=1, le=3)
    backend: str | None = None
    model: str | None = None

    @field_validator("backend")
    @classmethod
    def _check_backend(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in BACKEND_NAMES:
            raise ValueError(f"unknown backend {v!r}")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return _to_jsonable(asdict(obj))
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    return obj


def _resolve_profile_or_default(name: str | None) -> Profile:
    return resolve_profile(name or "default_ghanaian")


def _list_profiles_payload() -> dict[str, Any]:
    """Discover all available profiles (XDG dir + bundled default)."""
    from ..config import profiles_dir
    from ..profile.loader import BUNDLED_DEFAULT, resolve_profile as _resolve

    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Bundled default first.
    try:
        bundled = _resolve("default_ghanaian")
        out.append(
            {
                "name": bundled.profile_name,
                "dialect": bundled.dialect,
                "is_bundled": True,
            }
        )
        seen.add(bundled.profile_name)
    except Exception:  # pragma: no cover
        pass

    pdir = profiles_dir()
    for path in sorted(pdir.glob("*.yaml")):
        try:
            from ..profile.schema import load_profile

            prof = load_profile(path)
        except Exception:
            continue
        if prof.profile_name in seen:
            # User-saved override of the bundled name; mark as not-bundled.
            for entry in out:
                if entry["name"] == prof.profile_name:
                    entry["is_bundled"] = False
                    entry["dialect"] = prof.dialect
            continue
        out.append(
            {
                "name": prof.profile_name,
                "dialect": prof.dialect,
                "is_bundled": False,
            }
        )
        seen.add(prof.profile_name)
    return {"profiles": out}


def _normalize_stages(raw: Iterable[str] | None) -> tuple[str, ...]:
    if not raw:
        return ALL_STAGES
    seq = list(raw)
    if seq == ["all"]:
        return ALL_STAGES
    return tuple(seq)


def _apply_backend_override(profile: Profile, backend: str | None, model: str | None) -> Profile:
    """Return a profile with ``backend``/``model`` overridden if requested."""
    if backend is None and model is None:
        return profile
    updates: dict[str, Any] = {}
    if backend is not None:
        updates["backend"] = backend
    if model is not None:
        new_cfg = dict(profile.backend_config)
        new_cfg["model"] = model
        updates["backend_config"] = new_cfg
    return profile.model_copy(update=updates)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


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

    @app.get("/v1/health")
    async def health(_: None = auth_dep) -> dict[str, Any]:
        configured = available_backends()
        return {
            "ok": True,
            "version": VERSION,
            "backends_available": list(BACKEND_NAMES),
            "backends_configured": configured,
        }

    @app.get("/v1/profiles")
    async def profiles(_: None = auth_dep) -> dict[str, Any]:
        return _list_profiles_payload()

    @app.post("/v1/score")
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

    @app.post("/v1/transform")
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

    @app.post("/v1/suggest")
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

        with ThreadPoolExecutor(max_workers=min(suggest_workers, max(1, n))) as ex:
            candidates = list(ex.map(_one, seeds))

        input_score = score_runner(body.text, prof).score
        return {"candidates": candidates, "input_score": input_score}

    return app


def _code_for_status(code: int) -> str:
    if code == 401:
        return "unauthorised"
    if code == 400:
        return "invalid_input"
    if code == 404:
        return "not_found"
    if code == 502:
        return "backend_unavailable"
    return "internal"


def _serialise_pipeline_result(result: Any) -> dict[str, Any]:
    """Convert a :class:`PipelineResult` to the BRIDGE_CONTRACT §3.4 shape."""
    return {
        "input": result.input,
        "output": result.output,
        "pre_score": _to_jsonable(result.pre_score),
        "post_score": _to_jsonable(result.post_score),
        "llm_used": result.llm_used,
        "deterministic_log": [_to_jsonable(item) for item in result.deterministic_log],
        "grammar": _to_jsonable(result.grammar) if result.grammar is not None else None,
        "elapsed_seconds": result.elapsed_seconds,
        "notes": list(result.notes),
    }


__all__ = ["VERSION", "ALLOWED_ORIGINS", "create_app"]
