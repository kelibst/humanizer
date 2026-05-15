"""Phase 3: Zotero local-API routes + citation style export.

Routes added
------------
* GET  /v1/zotero/status      — is Zotero running?
* GET  /v1/zotero/collections — list Zotero collections
* POST /v1/zotero/import      — pull a collection into references.json
* POST /v1/citations/export   — render references.json in apa/mla/chicago
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException

from ..helpers import _try_update_markdown_refs
from ..models.v156 import CitationsStyleBody, ZoteroImportBody


def make_router(auth_dep: Any) -> APIRouter:
    router = APIRouter()

    # ------------------------------------------------------------------
    # GET /v1/zotero/status
    # ------------------------------------------------------------------

    @router.get("/v1/zotero/status")
    async def zotero_status(_: None = auth_dep) -> dict[str, Any]:
        """Check whether the Zotero local API is running on port 23119."""
        from ...research.zotero import is_running
        running = is_running()
        return {"running": running, "url": "http://localhost:23119/api"}

    # ------------------------------------------------------------------
    # GET /v1/zotero/collections
    # ------------------------------------------------------------------

    @router.get("/v1/zotero/collections")
    async def zotero_collections(
        user_id: str = "0",
        _: None = auth_dep,
    ) -> dict[str, Any]:
        """List collections in the local Zotero library."""
        from ...research.zotero import ZoteroUnavailable, list_collections
        try:
            cols = list_collections(user_id=user_id)
        except ZoteroUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail={"error": "zotero_unavailable", "detail": str(exc)},
            ) from exc
        return {"collections": cols}

    # ------------------------------------------------------------------
    # POST /v1/zotero/import
    # ------------------------------------------------------------------

    @router.post("/v1/zotero/import")
    async def zotero_import(
        body: ZoteroImportBody, _: None = auth_dep
    ) -> dict[str, Any]:
        """Pull items from a Zotero collection and merge into references.json."""
        from ...research.zotero import (
            ZoteroError,
            ZoteroUnavailable,
            import_collection,
        )
        from ...research.refs_store import load_refs, save_refs, upsert

        try:
            new_refs = import_collection(
                body.collection_key,
                user_id=body.user_id,
                limit=body.limit,
            )
        except ZoteroUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail={"error": "zotero_unavailable", "detail": str(exc)},
            ) from exc
        except ZoteroError as exc:
            raise HTTPException(
                status_code=502,
                detail={"error": "zotero_error", "detail": str(exc)},
            ) from exc

        existing = load_refs(body.workspace_root)
        merged = list(existing)
        imported_count = 0
        skipped_count = 0
        for ref in new_refs:
            if any(r.id == ref.id for r in merged):
                skipped_count += 1
                continue
            merged, _ = upsert(merged, ref)
            imported_count += 1

        save_refs(body.workspace_root, merged)

        if body.document_path and imported_count > 0:
            _try_update_markdown_refs(body.document_path, merged)

        return {
            "imported": imported_count,
            "skipped": skipped_count,
            "total_in_store": len(merged),
        }

    # ------------------------------------------------------------------
    # POST /v1/citations/export
    # ------------------------------------------------------------------

    @router.post("/v1/citations/export")
    async def citations_export(
        body: CitationsStyleBody, _: None = auth_dep
    ) -> dict[str, Any]:
        """Render all references in the workspace as a bullet list in the requested style.

        Returns ``{style, markdown}`` where ``markdown`` is a newline-separated
        bullet list ready to paste into a ``## References`` section.
        """
        from ...research.refs_store import load_refs
        from ...research.cite_styles import regenerate_block

        refs = load_refs(body.workspace_root)
        if not refs:
            raise HTTPException(
                status_code=404,
                detail={"error": "no_refs", "detail": "No references found in workspace."},
            )
        markdown = regenerate_block(refs, style=body.style)
        return {"style": body.style, "markdown": markdown}

    return router
