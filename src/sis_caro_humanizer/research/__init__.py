"""Research aids package — section completeness, citations, references, readability.

Built for v1.3 (Track B). Modules here are pure / deterministic and never call an
LLM. They are consumed by the new ``/v1/lint``, ``/v1/checklist``, ``/v1/readability``,
``/v1/citations``, ``/v1/refs`` daemon routes and by the VS Code extension's
sidebar panels.

Public re-exports are intentionally narrow — see each submodule for the full API.
"""
from __future__ import annotations

from .checklist import ChecklistComponent, ChecklistSection, analyse_sections
from .citations import (
    CitationsReport,
    MissingCitation,
    OrphanCitation,
    UnusedReference,
    analyse_citations,
)
from .readability import ReadabilityMetrics, TargetCheck, TargetChecks, compute
from .refs_store import (
    Reference,
    derive_id,
    load_refs,
    parse_apa_block,
    regenerate_apa_block,
    save_refs,
    update_markdown_references_block,
    upsert,
)

__all__ = [
    # checklist
    "ChecklistSection",
    "ChecklistComponent",
    "analyse_sections",
    # citations
    "CitationsReport",
    "MissingCitation",
    "OrphanCitation",
    "UnusedReference",
    "analyse_citations",
    # readability
    "ReadabilityMetrics",
    "TargetCheck",
    "TargetChecks",
    "compute",
    # refs_store
    "Reference",
    "derive_id",
    "load_refs",
    "parse_apa_block",
    "regenerate_apa_block",
    "save_refs",
    "update_markdown_references_block",
    "upsert",
]
