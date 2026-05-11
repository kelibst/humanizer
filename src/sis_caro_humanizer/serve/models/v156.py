"""v1.5 / v1.6 request body models."""
from __future__ import annotations

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


class ExportDocxBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    output_path: str


class ExportPdfBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    output_path: str
