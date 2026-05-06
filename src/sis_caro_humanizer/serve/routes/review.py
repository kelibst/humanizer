"""/v1/review-import route."""
from __future__ import annotations

import pathlib
import tempfile
from typing import Any, Callable

from fastapi import APIRouter, HTTPException

from ..models.v156 import ReviewImportBody


def make_router(
    score_runner: Callable[..., Any],
    auth_dep: Any,
) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/review-import")
    async def review_import(body: ReviewImportBody, _: None = auth_dep) -> dict[str, Any]:
        """Accept a lecturer-reviewed DOCX (base64-encoded), extract tracked
        changes and comments, diff against the original text, and score the
        accepted text.
        """
        import base64

        try:
            from ...docx_bridge import (  # type: ignore[import]
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

    return router
