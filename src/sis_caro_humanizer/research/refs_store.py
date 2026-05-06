"""``references.json`` store with APA-7 round-trip.

CONTRACT §3.1, §1.5, §1.6, §1.7. The store lives at
``{workspace_root}/references.json`` and is a JSON object of the shape::

    {"refs": [Reference, Reference, ...]}

We never write outside ``workspace_root``. The file is created lazily on
first ``POST /v1/refs``.

The markdown ``## References`` block uses HTML-comment markers so subsequent
``upsert`` / ``delete`` calls regenerate cleanly without touching content
outside the markers::

    ## References

    <!-- humanizer:refs:start -->
    - Smith, J., & Doe, A. (2020). On things. *J. Things*, 12(3), 45-67.
    <!-- humanizer:refs:end -->

If markers are absent, ``update_markdown_references_block`` inserts both
markers and replaces the existing list under the heading; if there is no
``## References`` heading at all, the heading + markers are appended at EOF.

Manual edits *between* the markers are overwritten on regeneration; this is
documented in ``plan/V1_3_STATE.md``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Pydantic model (CONTRACT §3.1)
# ---------------------------------------------------------------------------


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    authors: list[str] = Field(min_length=1)
    year: int = Field(ge=1500, le=2100)
    title: str = Field(min_length=1)
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    type: Literal["journal", "book", "chapter", "web"]
    raw_apa: str

    @field_validator("authors")
    @classmethod
    def _strip_authors(cls, v: list[str]) -> list[str]:
        out = [a.strip() for a in v if a and a.strip()]
        if not out:
            raise ValueError("at least one non-empty author required")
        return out


# ---------------------------------------------------------------------------
# Markers (CONTRACT §1.7)
# ---------------------------------------------------------------------------

REFS_START_MARKER = "<!-- humanizer:refs:start -->"
REFS_END_MARKER = "<!-- humanizer:refs:end -->"

_REFS_HEADING_RE = re.compile(
    r"(?im)^[ \t]*#{1,6}[ \t]+(?:references|bibliography|works\s+cited)\s*:?\s*$"
)


# ---------------------------------------------------------------------------
# id derivation (CONTRACT §1.6) — implementation moved to ref_ids.py
# ---------------------------------------------------------------------------

from .ref_ids import derive_id, _last_name_from_author, _suffix_chars  # noqa: F401


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _refs_file(workspace_root: str | Path) -> Path:
    return Path(workspace_root) / "references.json"


def load_refs(workspace_root: str | Path) -> list[Reference]:
    """Read ``{workspace_root}/references.json``; return [] if absent.

    Does NOT create the file (CONTRACT §1.5). Malformed entries are dropped
    silently — the caller can re-save to clean up.
    """
    path = _refs_file(workspace_root)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, dict):
        return []
    items = raw.get("refs", [])
    if not isinstance(items, list):
        return []
    out: list[Reference] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            out.append(Reference.model_validate(item))
        except (TypeError, ValueError):
            continue
    return out


def save_refs(workspace_root: str | Path, refs: list[Reference]) -> None:
    """Write ``references.json`` (creating ``workspace_root`` if needed)."""
    root = Path(workspace_root)
    root.mkdir(parents=True, exist_ok=True)
    path = _refs_file(root)
    payload = {"refs": [r.model_dump(mode="json") for r in refs]}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# upsert (CONTRACT §1.6)
# ---------------------------------------------------------------------------


def upsert(
    refs: list[Reference], ref: Reference | dict
) -> tuple[list[Reference], Reference]:
    """Insert or replace ``ref`` in ``refs`` by id; return (new_refs, canonical).

    If the input lacks an ``id``, one is derived. If an existing entry has the
    same id, it is replaced. The returned canonical record always has a
    populated ``id``.
    """
    # Accept dict for convenience in route handlers.
    if isinstance(ref, dict):
        candidate_dict = dict(ref)
        if not candidate_dict.get("id"):
            candidate_dict["id"] = "placeholder"  # validate first; replace below
        ref_obj = Reference.model_validate(candidate_dict)
        if candidate_dict.get("id") == "placeholder":
            # Force re-derivation
            ref_obj = ref_obj.model_copy(update={"id": ""})
    else:
        ref_obj = ref

    if not ref_obj.id:
        new_id = derive_id(ref_obj, existing=refs)
        ref_obj = ref_obj.model_copy(update={"id": new_id})

    out: list[Reference] = []
    replaced = False
    for r in refs:
        if r.id == ref_obj.id:
            out.append(ref_obj)
            replaced = True
        else:
            out.append(r)
    if not replaced:
        out.append(ref_obj)
    return out, ref_obj


# ---------------------------------------------------------------------------
# APA-7 round-trip
# ---------------------------------------------------------------------------

# Year-in-parens at the start of an APA reference: the canonical APA-7 form.
_APA_AUTHOR_YEAR_RE = re.compile(r"^(?P<authors>.+?)\s*\((?P<year>\d{4}[a-z]?)\)\.\s*(?P<rest>.*)")


def _split_authors(authors_field: str) -> list[str]:
    """Crude splitter: ``"Smith, J., & Doe, A."`` -> ["Smith, J.", "Doe, A."]."""
    s = authors_field.strip()
    s = re.sub(r"\s*&\s*", "; ", s)
    s = re.sub(r"\s+and\s+", "; ", s)
    # Now split on '; '. The remaining ', ' inside each chunk separates last
    # name from initials and stays intact.
    parts = [p.strip().rstrip(",.") for p in s.split(";")]
    return [p for p in parts if p]


def parse_apa_block(markdown_text: str) -> list[Reference]:
    """Parse a markdown ``## References`` block into ``Reference`` records.

    Tolerant of: bullet markers (``-``, ``*``, ``+``, numbered), surrounding
    blank lines, and content inside the marker block. Items that don't match
    APA-7 ``Author(s) (Year). Rest.`` are skipped silently — round-trip is
    "best-effort" per the brief.
    """
    text = markdown_text or ""

    # Prefer the marker block if it exists.
    block: str | None = None
    if REFS_START_MARKER in text and REFS_END_MARKER in text:
        try:
            start = text.index(REFS_START_MARKER) + len(REFS_START_MARKER)
            end = text.index(REFS_END_MARKER, start)
            block = text[start:end]
        except ValueError:
            block = None

    if block is None:
        # Fall back to the "## References" heading region.
        m = _REFS_HEADING_RE.search(text)
        if m:
            after = text[m.end():]
            # Stop at the next ATX heading.
            next_h = re.search(r"(?m)^[ \t]*#{1,6}[ \t]+\S", after)
            block = after[: next_h.start()] if next_h else after
        else:
            block = ""

    refs: list[Reference] = []
    seen_ids: list[Reference] = []
    for raw_line in block.split("\n"):
        line = raw_line.strip()
        if not line or line.startswith("<!--"):
            continue
        # Strip bullet markers.
        line = re.sub(r"^(?:[-*+]|\d+\.)\s+", "", line)
        if not line:
            continue
        # Drop simple emphasis markers around venue (``*J. Things*`` etc.).
        line_clean = re.sub(r"\*([^*]+)\*", r"\1", line)
        line_clean = line_clean.replace("_", "")
        m = _APA_AUTHOR_YEAR_RE.match(line_clean)
        if not m:
            continue
        authors = _split_authors(m.group("authors"))
        if not authors:
            continue
        year_raw = m.group("year")
        year_match = re.match(r"(\d{4})", year_raw)
        if not year_match:
            continue
        year = int(year_match.group(1))
        rest = m.group("rest").strip()
        # Title = up to the first ".  ".
        title_m = re.match(r"(.+?)\.\s*(.*)", rest)
        if title_m:
            title = title_m.group(1).strip()
            tail = title_m.group(2).strip()
        else:
            title = rest.rstrip(".")
            tail = ""
        # Venue = first chunk up to a comma or period in the tail.
        venue: str | None = None
        if tail:
            venue_m = re.match(r"(.+?)[,.]", tail)
            venue = (venue_m.group(1) if venue_m else tail).strip() or None

        ref_dict = {
            "authors": authors,
            "year": year,
            "title": title,
            "venue": venue,
            "type": "journal",
            "raw_apa": line,
        }
        try:
            tmp = Reference.model_validate({**ref_dict, "id": "placeholder"})
        except (TypeError, ValueError):
            continue
        ref_id = derive_id(tmp.model_copy(update={"id": ""}), existing=seen_ids)
        ref = tmp.model_copy(update={"id": ref_id})
        seen_ids.append(ref)
        refs.append(ref)
    return refs


def regenerate_apa_block(refs: list[Reference]) -> str:
    """Render ``refs`` as a markdown bullet list inside the marker block.

    Sorted alphabetically by first-author last name, then year ascending,
    then title. Each line is ``- {raw_apa}``; if ``raw_apa`` is empty we
    synthesise a minimal APA-7 string from authors/year/title/venue.
    """

    def _key(r: Reference) -> tuple[str, int, str]:
        last = _last_name_from_author(r.authors[0]) if r.authors else ""
        return (last, r.year, (r.title or "").lower())

    sorted_refs = sorted(refs, key=_key)
    lines = [REFS_START_MARKER]
    for r in sorted_refs:
        line = (r.raw_apa or "").strip()
        if not line:
            authors_str = ", ".join(r.authors)
            line = f"{authors_str} ({r.year}). {r.title}."
            if r.venue:
                line += f" {r.venue}."
        lines.append(f"- {line}")
    lines.append(REFS_END_MARKER)
    return "\n".join(lines)


def update_markdown_references_block(
    md_text: str, refs: list[Reference]
) -> str:
    """Return ``md_text`` with the ``## References`` block regenerated.

    Behaviour:
    - If both markers are present, replace the content between them.
    - Else if a ``## References`` heading exists, replace everything from the
      heading line to the next ATX heading (or EOF) with
      ``## References\\n\\n{block}\\n``.
    - Else, append a new ``\\n\\n## References\\n\\n{block}\\n`` to EOF.
    """
    block = regenerate_apa_block(refs)
    text = md_text or ""

    if REFS_START_MARKER in text and REFS_END_MARKER in text:
        s = text.index(REFS_START_MARKER)
        e = text.index(REFS_END_MARKER, s) + len(REFS_END_MARKER)
        return text[:s] + block + text[e:]

    m = _REFS_HEADING_RE.search(text)
    if m:
        head_start = m.start()
        # Use the next heading after the matched line as the boundary.
        after = text[m.end():]
        next_h = re.search(r"(?m)^[ \t]*#{1,6}[ \t]+\S", after)
        if next_h:
            head_end = m.end() + next_h.start()
            return text[:head_start] + "## References\n\n" + block + "\n\n" + text[head_end:]
        return text[:head_start] + "## References\n\n" + block + "\n"

    # No heading at all.
    sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    if not text:
        return f"## References\n\n{block}\n"
    return text + sep + f"\n## References\n\n{block}\n"


# ---------------------------------------------------------------------------
# Orphan-key parser (CONTRACT v1.5 §1) — implementation moved to citation_keys.py
# ---------------------------------------------------------------------------

from .citation_keys import parse_orphan_key  # noqa: F401


__all__ = [
    "REFS_END_MARKER",
    "REFS_START_MARKER",
    "Reference",
    "derive_id",
    "load_refs",
    "parse_apa_block",
    "parse_orphan_key",
    "regenerate_apa_block",
    "save_refs",
    "update_markdown_references_block",
    "upsert",
]
