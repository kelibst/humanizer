"""/v1/refs/doi-lookup, /v1/refs/bibtex-import, /v1/refs/bibtex-export,
/v1/refs/batch-stub routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from ...research.refs_store import (
    Reference,
    derive_id,
    load_refs,
    save_refs,
    upsert as upsert_ref,
)
from ..helpers import _try_update_markdown_refs
from ..models.v156 import BatchStubBody, BibtexImportBody, DoiLookupBody


def make_router(auth_dep: Any) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/refs/doi-lookup")
    async def doi_lookup_route(body: DoiLookupBody, _: None = auth_dep) -> dict[str, Any]:
        """Resolve a DOI via CrossRef and return metadata.

        Does NOT save to references.json — client calls POST /v1/refs to persist.
        """
        from ...research.doi import DoiLookupError, DoiNotFound, lookup_doi

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

    @router.post("/v1/refs/bibtex-import")
    async def bibtex_import_route(
        body: BibtexImportBody, _: None = auth_dep
    ) -> dict[str, Any]:
        """Parse BibTeX text and bulk-upsert into references.json.

        Collisions (same derived id) are silently skipped and counted.
        """
        from ...research.bibtex import parse_bibtex

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

    @router.get("/v1/refs/bibtex-export")
    async def bibtex_export_route(
        workspace_root: str, _: None = auth_dep
    ) -> PlainTextResponse:
        """Export all references as BibTeX.

        Returns Content-Disposition: attachment; filename="references.bib".
        """
        from ...research.bibtex import references_to_bibtex

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

    @router.post("/v1/refs/batch-stub")
    async def batch_stub_route(
        body: BatchStubBody, _: None = auth_dep
    ) -> dict[str, Any]:
        """Create stub References from orphan citation keys.

        Each key like '(Smith, 2020)' becomes a Reference with
        title='[TITLE UNKNOWN]' and raw_apa synthesised from parsed names/year.
        Collisions are silently skipped.
        """
        from ...research.refs_store import parse_orphan_key

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

    return router
