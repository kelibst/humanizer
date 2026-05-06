"""FastAPI bridge daemon for the Google Docs add-in and the VS Code extension.

See ``plan/BRIDGE_CONTRACT.md`` for the locked v1.2 HTTP contract and
``plan/V1_3_CONTRACT.md`` for the v1.3 research-aid additions. Every route in
both contracts is implemented in this module.

The app is constructed via :func:`create_app` so tests can pass an explicit
``token`` and the production runner (see :mod:`runner`) can build it with the
on-disk persistent token.
"""
from __future__ import annotations

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..backends import BACKEND_NAMES, BackendError, BackendUnavailable, get_backend, list_available
from ..pipeline.runner import ALL_STAGES, run_pipeline
from ..profile.loader import resolve_profile
from ..profile.schema import Profile
from ..research.checklist import analyse_sections
from ..research.citations import analyse_citations
from ..research.inspector import inspect_section
from ..research.prompts import list_templates as _list_templates
from ..research.prompts import render as _render_prompt
from ..research.readability import compute as compute_readability
from ..research.refs_store import (
    Reference,
    derive_id,
    load_refs,
    save_refs,
    update_markdown_references_block,
    upsert as upsert_ref,
)
from ..scoring.external import KNOWN_DETECTORS, DetectorUnavailable, get_detector
from ..scoring.risk import ai_risk_score
from .auth import constant_time_compare, extract_bearer
from .lint import LINT_CODES, run_lint

VERSION = "1.5.0"

# Module-level sentinel for SSE stream termination (CONTRACT v1.5 §8).
_STREAM_DONE = object()

# Module-level executor reused by /v1/suggest and /v1/transform/stream.
_executor = ThreadPoolExecutor(max_workers=4)

ALLOWED_ORIGINS = ("https://docs.google.com", "https://script.google.com")

MAX_TEXT_SCORE = 100_000
MAX_TEXT_TRANSFORM = 100_000
MAX_TEXT_SUGGEST = 30_000

# v1.3 — research-aid limits (CONTRACT v1.3 §7).
MAX_TEXT_LINT = 100_000
MAX_TEXT_CHECKLIST = 100_000
MAX_TEXT_READABILITY = 100_000
MAX_TEXT_CITATIONS = 100_000

# v1.4 — research / benchmark limits (CONTRACT v1.4 §9).
MAX_TEXT_PROMPT = 50_000
MAX_TEXT_INSPECT = 100_000
MAX_TEXT_REVIEWER = 200_000
MAX_TEXT_LLM_RUN = 200_000
MAX_TEXT_BENCHMARK = 100_000

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
# v1.3 request bodies (research aids)
# ---------------------------------------------------------------------------


class LintBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., max_length=MAX_TEXT_LINT)
    profile: str | None = None
    include: list[str] | None = None

    @field_validator("include")
    @classmethod
    def _check_include(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        for code in v:
            if code not in LINT_CODES:
                raise ValueError(f"unknown lint code {code!r}")
        return v


class ChecklistBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., max_length=MAX_TEXT_CHECKLIST)
    profile: str | None = None


class ReadabilityBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., max_length=MAX_TEXT_READABILITY)
    profile: str | None = None


class CitationsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., max_length=MAX_TEXT_CITATIONS)
    workspace_root: str = Field(..., min_length=1)
    profile: str | None = None


class RefBody(BaseModel):
    """``POST /v1/refs`` body. Accepts a partial Reference (id may be omitted).

    The shape mirrors :class:`Reference` but with a permissive ``id``: blank
    or absent is fine, the server fills it in.
    """

    model_config = ConfigDict(extra="forbid")
    workspace_root: str = Field(..., min_length=1)
    document_path: str | None = None
    id: str | None = None
    authors: list[str] = Field(min_length=1)
    year: int = Field(ge=1500, le=2100)
    title: str = Field(min_length=1)
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    type: str = Field(default="journal")
    raw_apa: str | None = None

    @field_validator("type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in ("journal", "book", "chapter", "web"):
            raise ValueError("type must be journal|book|chapter|web")
        return v


# ---------------------------------------------------------------------------
# v1.4 request bodies (CONTRACT v1.4 §1)
# ---------------------------------------------------------------------------


class RenderPromptBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_id: str = Field(..., min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)


class InspectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section_text: str = Field(..., max_length=MAX_TEXT_INSPECT)
    section_type: str = Field(..., min_length=1)


class ReviewerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_text: str = Field(..., max_length=MAX_TEXT_REVIEWER)
    persona: str = Field(...)

    @field_validator("persona")
    @classmethod
    def _check_persona(cls, v: str) -> str:
        if v not in ("r1", "r2"):
            raise ValueError("persona must be 'r1' or 'r2'")
        return v


class LlmRunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(..., max_length=MAX_TEXT_LLM_RUN)
    backend: str = Field(...)
    model: str | None = None

    @field_validator("backend")
    @classmethod
    def _check_backend(cls, v: str) -> str:
        if v not in BACKEND_NAMES:
            raise ValueError(f"unknown backend {v!r}")
        return v


class BenchmarkBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., max_length=MAX_TEXT_BENCHMARK)
    detectors: list[str] = Field(default_factory=list)
    profile: str | None = None

    @field_validator("detectors")
    @classmethod
    def _check_detectors(cls, v: list[str]) -> list[str]:
        for d in v:
            if d not in KNOWN_DETECTORS:
                raise ValueError(f"unknown detector {d!r}")
        return v


# ---------------------------------------------------------------------------
# v1.5 request bodies (CONTRACT v1.5 §3)
# ---------------------------------------------------------------------------


class ReviewImportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    docx_b64: str = Field(..., min_length=1)
    original_text: str
    workspace_root: str | None = None


class DoiLookupBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doi: str = Field(..., min_length=1)


class BibtexImportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bibtex_text: str = Field(..., min_length=1)
    workspace_root: str = Field(..., min_length=1)
    document_path: str | None = None


class BatchStubBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    orphan_keys: list[str] = Field(..., min_length=1)
    workspace_root: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# v1.6 request bodies (CONTRACT v1.6 §B2)
# ---------------------------------------------------------------------------


class GoogleDocsCitationsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paragraphs: list[str]
    workspace_root: str | None = None
    profile: str | None = None


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

    # ----------------------------------------------------------------------
    # v1.3 research-aid routes (CONTRACT v1.3 §1)
    # ----------------------------------------------------------------------

    @app.post("/v1/lint")
    async def lint(body: LintBody, _: None = auth_dep) -> dict[str, Any]:
        prof = _safe_resolve_profile(body.profile)
        spans, elapsed_ms = run_lint(body.text, profile=prof, include=body.include)
        return {
            "spans": [_to_jsonable(s) for s in spans],
            "elapsed_ms": elapsed_ms,
        }

    @app.post("/v1/checklist")
    async def checklist(body: ChecklistBody, _: None = auth_dep) -> dict[str, Any]:
        prof = _safe_resolve_profile(body.profile)
        sections = analyse_sections(body.text, prof)
        return {"sections": [_to_jsonable(s) for s in sections]}

    @app.post("/v1/readability")
    async def readability(body: ReadabilityBody, _: None = auth_dep) -> dict[str, Any]:
        prof = _safe_resolve_profile(body.profile)
        metrics, targets = compute_readability(body.text, prof)
        return {
            "metrics": _to_jsonable(metrics),
            "targets": _to_jsonable(targets),
        }

    @app.post("/v1/citations")
    async def citations(body: CitationsBody, _: None = auth_dep) -> dict[str, Any]:
        prof = _safe_resolve_profile(body.profile)
        try:
            refs = load_refs(body.workspace_root)
        except OSError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": str(exc)},
            ) from exc
        report = analyse_citations(body.text, refs, prof)
        return {
            "missing": [_to_jsonable(m) for m in report.missing],
            "orphans": [_to_jsonable(o) for o in report.orphans],
            "unused": [_to_jsonable(u) for u in report.unused],
        }

    @app.post("/v1/citations/google-docs")
    async def citations_google_docs(
        body: GoogleDocsCitationsBody, _: None = auth_dep
    ) -> dict[str, Any]:
        """Return citation findings with paragraph-indexed coordinates for Google Docs.

        The caller passes the document as a list of paragraph strings (matching
        ``DocumentApp.getBody().getParagraphs()``).  The response extends the
        flat character-offset data from ``/v1/citations`` with
        ``paragraph_idx`` and ``char_in_paragraph`` fields so the Apps Script
        add-in can highlight text without calling ``positionAt()``.
        """
        from ..research.citations import flat_to_paragraph_offset

        prof = _safe_resolve_profile(body.profile)
        flat_text = "\n\n".join(body.paragraphs)

        if body.workspace_root:
            try:
                refs = load_refs(body.workspace_root)
            except OSError as exc:
                raise HTTPException(
                    status_code=400,
                    detail={"error": "invalid_input", "detail": str(exc)},
                ) from exc
        else:
            refs = []

        report = analyse_citations(flat_text, refs, prof)

        def _with_coords(items: list[Any], has_span: bool = True) -> list[dict[str, Any]]:
            out = []
            for item in items:
                d = _to_jsonable(item)
                if has_span:
                    p_idx, c_idx = flat_to_paragraph_offset(
                        body.paragraphs, item.start
                    )
                    d["paragraph_idx"] = p_idx
                    d["char_in_paragraph"] = c_idx
                out.append(d)
            return out

        return {
            "missing": _with_coords(report.missing),
            "orphans": _with_coords(report.orphans),
            "unused": _with_coords(report.unused, has_span=False),
        }

    @app.get("/v1/refs")
    async def list_refs(workspace_root: str, _: None = auth_dep) -> dict[str, Any]:
        if not workspace_root:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": "workspace_root is required"},
            )
        refs = load_refs(workspace_root)
        return {"refs": [r.model_dump(mode="json") for r in refs]}

    @app.post("/v1/refs")
    async def create_ref(
        body: RefBody, _: None = auth_dep
    ) -> dict[str, Any]:
        try:
            existing = load_refs(body.workspace_root)
        except OSError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": str(exc)},
            ) from exc

        ref_payload = {
            "authors": body.authors,
            "year": body.year,
            "title": body.title,
            "venue": body.venue,
            "doi": body.doi,
            "url": body.url,
            "type": body.type,
            "raw_apa": body.raw_apa or _synth_raw_apa(body),
        }
        if body.id:
            ref_payload["id"] = body.id

        try:
            new_refs, canonical = upsert_ref(existing, ref_payload)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": str(exc)},
            ) from exc

        try:
            save_refs(body.workspace_root, new_refs)
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail={"error": "internal", "detail": str(exc)},
            ) from exc

        if body.document_path:
            _try_update_markdown_refs(body.document_path, new_refs)
        return canonical.model_dump(mode="json")

    @app.delete("/v1/refs/{ref_id}")
    async def delete_ref(
        ref_id: str,
        workspace_root: str,
        document_path: str | None = None,
        _: None = auth_dep,
    ) -> dict[str, Any]:
        if not workspace_root:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": "workspace_root is required"},
            )
        existing = load_refs(workspace_root)
        new_refs = [r for r in existing if r.id != ref_id]
        if len(new_refs) == len(existing):
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "detail": f"ref {ref_id!r} not found"},
            )
        try:
            save_refs(workspace_root, new_refs)
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail={"error": "internal", "detail": str(exc)},
            ) from exc
        if document_path:
            _try_update_markdown_refs(document_path, new_refs)
        return {"deleted": True}

    # ----------------------------------------------------------------------
    # v1.4 research-template + benchmark routes (CONTRACT v1.4 §1)
    # ----------------------------------------------------------------------

    @app.get("/v1/research/templates")
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

    @app.post("/v1/research/prompt")
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

    @app.post("/v1/research/inspect")
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

    @app.post("/v1/research/reviewer")
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

    @app.post("/v1/llm/run")
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

    @app.post("/v1/benchmark")
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

    # ------------------------------------------------------------------
    # v1.5 citation-management routes (CONTRACT v1.5 §3)
    # ------------------------------------------------------------------

    @app.post("/v1/refs/doi-lookup")
    async def doi_lookup_route(body: DoiLookupBody, _: None = auth_dep) -> dict[str, Any]:
        """Resolve a DOI via CrossRef and return metadata.

        Does NOT save to references.json — client calls POST /v1/refs to persist.
        """
        from ..research.doi import DoiLookupError, DoiNotFound, lookup_doi

        try:
            result = lookup_doi(body.doi)
        except DoiNotFound as exc:
            raise HTTPException(
                status_code=404,
                detail={"error": "doi_not_found", "detail": str(exc)},
            ) from exc
        except DoiLookupError as exc:
            raise HTTPException(
                status_code=502,
                detail={"error": "doi_lookup_error", "detail": str(exc)},
            ) from exc
        return result

    @app.post("/v1/refs/bibtex-import")
    async def bibtex_import_route(
        body: BibtexImportBody, _: None = auth_dep
    ) -> dict[str, Any]:
        """Parse BibTeX text and bulk-upsert into references.json.

        Collisions (same derived id) are silently skipped and counted.
        """
        from ..research.bibtex import parse_bibtex

        try:
            parsed = parse_bibtex(body.bibtex_text)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": str(exc)},
            ) from exc

        try:
            existing = load_refs(body.workspace_root)
        except OSError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": str(exc)},
            ) from exc

        existing_ids = {r.id for r in existing}
        imported_count = 0
        skipped_count = 0
        new_refs_list: list[Reference] = []

        current = list(existing)
        for ref in parsed:
            if ref.id in existing_ids:
                skipped_count += 1
                continue
            current, canonical = upsert_ref(current, ref)
            existing_ids.add(canonical.id)
            new_refs_list.append(canonical)
            imported_count += 1

        try:
            save_refs(body.workspace_root, current)
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail={"error": "internal", "detail": str(exc)},
            ) from exc

        if body.document_path:
            _try_update_markdown_refs(body.document_path, current)

        return {
            "imported": imported_count,
            "skipped": skipped_count,
            "refs": [r.model_dump(mode="json") for r in new_refs_list],
        }

    @app.get("/v1/refs/bibtex-export")
    async def bibtex_export_route(
        workspace_root: str, _: None = auth_dep
    ) -> PlainTextResponse:
        """Export all references as BibTeX.

        Returns Content-Disposition: attachment; filename="references.bib".
        """
        from ..research.bibtex import references_to_bibtex

        if not workspace_root:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": "workspace_root is required"},
            )
        refs = load_refs(workspace_root)
        if not refs:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "detail": "workspace_root not found or no refs"},
            )
        bib_text = references_to_bibtex(refs)
        return PlainTextResponse(
            content=bib_text,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="references.bib"'},
        )

    @app.post("/v1/refs/batch-stub")
    async def batch_stub_route(
        body: BatchStubBody, _: None = auth_dep
    ) -> dict[str, Any]:
        """Create stub References from orphan citation keys.

        Each key like '(Smith, 2020)' becomes a Reference with
        title='[TITLE UNKNOWN]' and raw_apa synthesised from parsed names/year.
        Collisions are silently skipped.
        """
        from ..research.refs_store import parse_orphan_key

        try:
            existing = load_refs(body.workspace_root)
        except OSError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": str(exc)},
            ) from exc

        existing_ids = {r.id for r in existing}
        created_count = 0
        skipped_count = 0
        created_refs: list[Reference] = []
        current = list(existing)

        parse_errors: list[str] = []
        for key in body.orphan_keys:
            try:
                last_names, year = parse_orphan_key(key)
            except ValueError as exc:
                parse_errors.append(str(exc))
                continue

            # Build APA stub author strings — we only have last names.
            stub_authors = [f"{name}, [INITIALS UNKNOWN]" for name in last_names]
            first_last = last_names[0] if last_names else "Unknown"
            raw_apa = f"{first_last}, [INITIALS UNKNOWN]. ({year}). [TITLE UNKNOWN]."

            ref_dict: dict[str, Any] = {
                "id": "placeholder",
                "authors": stub_authors,
                "year": year,
                "title": "[TITLE UNKNOWN]",
                "venue": None,
                "doi": None,
                "url": None,
                "type": "journal",
                "raw_apa": raw_apa,
            }
            try:
                ref_obj = Reference.model_validate(ref_dict)
            except (TypeError, ValueError) as exc:
                parse_errors.append(str(exc))
                continue

            # Derive id without "placeholder"
            real_id = derive_id(ref_obj.model_copy(update={"id": "tmp"}), existing=current)
            ref_obj = ref_obj.model_copy(update={"id": real_id})

            if real_id in existing_ids:
                skipped_count += 1
                continue

            current, canonical = upsert_ref(current, ref_obj)
            existing_ids.add(canonical.id)
            created_refs.append(canonical)
            created_count += 1

        if parse_errors and not created_refs and not skipped_count:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": "; ".join(parse_errors)},
            )

        try:
            save_refs(body.workspace_root, current)
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail={"error": "internal", "detail": str(exc)},
            ) from exc

        return {
            "created": created_count,
            "skipped": skipped_count,
            "refs": [r.model_dump(mode="json") for r in created_refs],
        }

    # ------------------------------------------------------------------
    # v1.6 reviewer round-trip route (CONTRACT v1.6 §A2)
    # ------------------------------------------------------------------

    @app.post("/v1/review-import")
    async def review_import(body: ReviewImportBody, _: None = auth_dep) -> dict[str, Any]:
        """Accept a lecturer-reviewed DOCX (base64-encoded), extract tracked
        changes and comments, diff against the original text, and score the
        accepted text.
        """
        import base64
        import tempfile
        import pathlib

        try:
            from ..docx_bridge import (  # type: ignore[import]
                accept_tracked_changes,
                diff_text_sections,
                extract_word_comments,
            )
        except ImportError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "dependency_missing",
                    "detail": f"python-docx is required: {exc}",
                },
            ) from exc

        try:
            docx_bytes = base64.b64decode(body.docx_b64)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": f"invalid base64: {exc}"},
            ) from exc

        tmp_path: pathlib.Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
                tmp.write(docx_bytes)
                tmp_path = pathlib.Path(tmp.name)

            try:
                accepted_text = accept_tracked_changes(tmp_path)
            except ImportError as exc:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "dependency_missing",
                        "detail": f"python-docx is required: {exc}",
                    },
                ) from exc
            except Exception as exc:
                raise HTTPException(
                    status_code=400,
                    detail={"error": "invalid_input", "detail": f"DOCX parse error: {exc}"},
                ) from exc

            try:
                comments = extract_word_comments(tmp_path)
            except Exception:  # noqa: BLE001 — comments extraction is best-effort
                comments = []

            diff_sections = diff_text_sections(body.original_text, accepted_text)

            report = score_runner(accepted_text)
            post_score = {"score": report.score, "band": report.band}

            return {
                "accepted_text": accepted_text,
                "diff_sections": diff_sections,
                "comments": comments,
                "post_score": post_score,
            }
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # v1.5 SSE streaming route (CONTRACT v1.5 §3.5, §8)
    # ------------------------------------------------------------------

    @app.post("/v1/transform/stream")
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

        future = _executor.submit(_run_in_thread)

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

    return app


def _safe_resolve_profile(name: str | None) -> Profile | None:
    """Resolve a profile name; on failure return ``None`` so research aids
    still work without a profile (targets just become null).

    The pre-v1.3 routes (``/v1/score``, ``/v1/transform``) raise 400 on
    unknown profile because they need profile-driven behaviour. The research
    aids prefer to degrade gracefully — a typo in the profile name should
    not block reading metrics.
    """
    if name is None:
        try:
            return resolve_profile("default_ghanaian")
        except FileNotFoundError:
            return None
    try:
        return resolve_profile(name)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "not_found", "detail": str(exc)},
        ) from exc


def _synth_raw_apa(body: "RefBody") -> str:
    authors = ", ".join(body.authors)
    line = f"{authors} ({body.year}). {body.title}."
    if body.venue:
        line += f" {body.venue}."
    return line


def _try_update_markdown_refs(document_path: str, refs: list[Reference]) -> None:
    """Best-effort regeneration of the markdown ``## References`` block.

    Failures (path missing, not writable, encoding issues) are swallowed
    silently — the route still succeeds because ``references.json`` is
    canonical.
    """
    try:
        path = Path(document_path)
        if not path.exists() or not path.is_file():
            return
        text = path.read_text(encoding="utf-8")
        new_text = update_markdown_references_block(text, refs)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
    except (OSError, UnicodeDecodeError, UnicodeEncodeError):
        return


def _code_for_status(code: int) -> str:
    if code == 401:
        return "unauthorised"
    if code == 400:
        return "invalid_input"
    if code == 403:
        return "external_disabled"
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
