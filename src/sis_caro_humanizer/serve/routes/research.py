"""/v1/lint, /v1/checklist, /v1/readability, /v1/citations, /v1/refs routes."""
from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException

from ...research.checklist import analyse_sections
from ...research.citations import analyse_citations
from ...research.readability import compute as compute_readability
from ...research.refs_store import (
    load_refs,
    save_refs,
    upsert as upsert_ref,
)
from ..helpers import (
    _safe_resolve_profile,
    _synth_raw_apa,
    _to_jsonable,
    _try_update_markdown_refs,
)
from ..models.v13 import (
    ChecklistBody,
    CitationsBody,
    LintBody,
    ReadabilityBody,
    RefBody,
)
from ..models.v156 import GoogleDocsCitationsBody
from ..lint import run_lint


def make_router(auth_dep: Any) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/lint")
    async def lint(body: LintBody, _: None = auth_dep) -> dict[str, Any]:
        prof = _safe_resolve_profile(body.profile)
        spans, elapsed_ms = run_lint(body.text, profile=prof, include=body.include)
        return {
            "spans": [_to_jsonable(s) for s in spans],
            "elapsed_ms": elapsed_ms,
        }

    @router.post("/v1/checklist")
    async def checklist(body: ChecklistBody, _: None = auth_dep) -> dict[str, Any]:
        prof = _safe_resolve_profile(body.profile)
        sections = analyse_sections(body.text, prof)
        return {"sections": [_to_jsonable(s) for s in sections]}

    @router.post("/v1/readability")
    async def readability(body: ReadabilityBody, _: None = auth_dep) -> dict[str, Any]:
        prof = _safe_resolve_profile(body.profile)
        metrics, targets = compute_readability(body.text, prof)
        return {
            "metrics": _to_jsonable(metrics),
            "targets": _to_jsonable(targets),
        }

    @router.post("/v1/citations")
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

    @router.post("/v1/citations/google-docs")
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
        from ...research.citations import flat_to_paragraph_offset

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

    @router.get("/v1/refs")
    async def list_refs(workspace_root: str, _: None = auth_dep) -> dict[str, Any]:
        if not workspace_root:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_input", "detail": "workspace_root is required"},
            )
        refs = load_refs(workspace_root)
        return {"refs": [r.model_dump(mode="json") for r in refs]}

    @router.post("/v1/refs")
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

    @router.delete("/v1/refs/{ref_id}")
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

    return router
