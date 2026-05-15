"""v1.5 / v1.6 request body models."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class GoogleDocsCitationsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paragraphs: list[str]
    workspace_root: str | None = None
    profile: str | None = None
    cite_style: Literal["apa", "mla", "chicago"] = "apa"


class ExportDocxBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    output_path: str


class ExportPdfBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    output_path: str


# ---------------------------------------------------------------------------
# Phase 3 — Zotero + Citation Styles
# ---------------------------------------------------------------------------


class ZoteroImportBody(BaseModel):
    """POST /v1/zotero/import — pull items from a Zotero collection."""

    model_config = ConfigDict(extra="forbid")
    collection_key: str = Field(..., min_length=1)
    workspace_root: str = Field(..., min_length=1)
    document_path: str | None = None
    user_id: str = "0"
    limit: int = Field(default=100, ge=1, le=100)


class CitationsStyleBody(BaseModel):
    """POST /v1/citations/export — render references in a given style."""

    model_config = ConfigDict(extra="forbid")
    workspace_root: str = Field(..., min_length=1)
    style: Literal["apa", "mla", "chicago"] = "apa"


# ---------------------------------------------------------------------------
# Phase 4 — Voice Diff
# ---------------------------------------------------------------------------


class VoiceDiffBody(BaseModel):
    """POST /v1/research/voice-diff — cross-section voice consistency analysis."""

    model_config = ConfigDict(extra="forbid")
    text: str = Field(..., min_length=1)
    profile: str | None = None
