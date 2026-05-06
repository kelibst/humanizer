"""BibTeX parser and serialiser for humanizer v1.5.

CONTRACT v1.5 §1, §10.

Public API:
    parse_bibtex(text)              -> list[Reference]
    reference_to_bibtex(ref)        -> str
    references_to_bibtex(refs)      -> str

Parsing is entirely regex-based — no external BibTeX library.
"""
from __future__ import annotations

import re
from typing import Any

from .refs_store import Reference, derive_id

# ---------------------------------------------------------------------------
# LaTeX character escaping (CONTRACT §10)
# ---------------------------------------------------------------------------

# Characters that must be escaped in BibTeX string values.
# We do NOT double-escape if the string already contains a backslash-escaped form.
_LATEX_ESC: list[tuple[str, str]] = [
    ("\\", "\\textbackslash{}"),  # must be first
    ("{", "\\{"),
    ("}", "\\}"),
    ("%", "\\%"),
    ("_", "\\_"),
    ("&", "\\&"),
    ("#", "\\#"),
    ("~", "\\textasciitilde{}"),
    ("^", "\\textasciicircum{}"),
]


def _latex_escape(s: str) -> str:
    """Escape special LaTeX characters in *s*.

    Skips strings that already look pre-escaped (contain a backslash).
    """
    if "\\" in s:
        # Already (partially) escaped – return as-is to avoid double-escaping.
        return s
    for char, replacement in _LATEX_ESC:
        s = s.replace(char, replacement)
    return s


# ---------------------------------------------------------------------------
# BibTeX entry-type → Reference type mapping (CONTRACT §10)
# ---------------------------------------------------------------------------

_TYPE_MAP: dict[str, str] = {
    "article": "journal",
    "book": "book",
    "incollection": "chapter",
    "inbook": "chapter",
    "inproceedings": "journal",
    "conference": "journal",
    "misc": "web",
    "techreport": "web",
    "mastersthesis": "web",
    "phdthesis": "web",
    "unpublished": "web",
    "manual": "web",
    "booklet": "web",
    "proceedings": "journal",
    "online": "web",
    "www": "web",
    "electronic": "web",
    "patent": "web",
    "standard": "web",
    "report": "web",
    "collection": "book",
}


def _bibtex_type(entry_type: str) -> str:
    return _TYPE_MAP.get(entry_type.lower(), "web")


# ---------------------------------------------------------------------------
# BibTeX entry parser
# ---------------------------------------------------------------------------

# Matches the opening of a BibTeX entry: @TYPE{KEY,
# Also allows @TYPE{KEY} (no fields) or @TYPE(KEY, ...
_ENTRY_START_RE = re.compile(
    r"@(?P<type>[A-Za-z]+)\s*[{(]\s*(?P<key>[^,\s}()]+)\s*,?",
    re.IGNORECASE,
)

# Matches a field: key = {value} or key = "value" or key = number
_FIELD_RE = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z0-9_\-]*)\s*=\s*"
    r"(?:"
    r'\{(?P<brace>[^{}]*(?:\{[^{}]*\}[^{}]*)*)\}'    # {value} — simplified, one level deep
    r'|"(?P<dquote>[^"]*)"'                           # "value"
    r'|(?P<bare>\d+)'                                 # bare number (year)
    r")",
    re.DOTALL,
)


def _strip_braces(s: str) -> str:
    """Remove outer/inner LaTeX brace groups used for capitalisation etc."""
    # Remove {X} capitalisation guards: {Smith} → Smith
    return re.sub(r"\{([^{}]*)\}", r"\1", s)


def _split_authors_bibtex(author_field: str) -> list[str]:
    """Split BibTeX author field on ' and ' (case-insensitive).

    Converts 'Last, First' → 'Last, F.' (APA style).
    Handles 'First Last' order too.
    """
    author_field = _strip_braces(author_field).strip()
    # BibTeX uses ' and ' as separator (semicolon not used here)
    parts = re.split(r"\s+and\s+", author_field, flags=re.IGNORECASE)
    out: list[str] = []
    for part in parts:
        part = part.strip().strip(",").strip()
        if not part:
            continue
        out.append(_bibtex_author_to_apa(part))
    return out


def _bibtex_author_to_apa(author: str) -> str:
    """Convert a single BibTeX author to APA 'Last, F.' format."""
    author = author.strip()
    if "," in author:
        # Last, First [Middle]
        last, _, rest = author.partition(",")
        last = last.strip()
        rest = rest.strip()
        if rest:
            initials = ".".join(p[0] for p in rest.split() if p) + "."
            return f"{last}, {initials}"
        return last
    else:
        # First [Middle] Last
        parts = author.split()
        if len(parts) == 1:
            return parts[0]
        last = parts[-1]
        first_parts = parts[:-1]
        initials = ".".join(p[0] for p in first_parts if p) + "."
        return f"{last}, {initials}"


def _extract_year_field(fields: dict[str, str]) -> int | None:
    """Extract year from BibTeX fields dict."""
    year_str = fields.get("year", "").strip()
    if year_str:
        m = re.search(r"\d{4}", year_str)
        if m:
            try:
                return int(m.group())
            except ValueError:
                pass
    # Fallback: date field (ISO: 2020-01-15 → 2020)
    date_str = fields.get("date", "").strip()
    if date_str:
        m = re.search(r"\d{4}", date_str)
        if m:
            try:
                return int(m.group())
            except ValueError:
                pass
    return None


def _extract_venue_field(fields: dict[str, str]) -> str | None:
    """Extract venue from BibTeX fields, following CONTRACT §10 priority."""
    for key in ("journal", "booktitle", "publisher", "howpublished", "school"):
        val = fields.get(key, "").strip()
        val = _strip_braces(val)
        if val:
            return val
    return None


def _build_raw_apa_from_fields(
    authors: list[str], year: int | None, title: str, venue: str | None
) -> str:
    """Build a minimal APA-7 citation string from parsed fields."""
    if len(authors) > 2:
        author_str = f"{authors[0]}, et al."
    elif len(authors) == 2:
        author_str = f"{authors[0]}, & {authors[1]}"
    elif authors:
        author_str = authors[0]
    else:
        author_str = "Unknown"
    year_str = str(year) if year else "n.d."
    line = f"{author_str} ({year_str}). {title}."
    if venue:
        line += f" {venue}."
    return line


def _parse_entry_body(body: str) -> dict[str, str]:
    """Extract all field=value pairs from the body of a BibTeX entry."""
    fields: dict[str, str] = {}
    for m in _FIELD_RE.finditer(body):
        name = m.group("name").lower()
        val = m.group("brace") or m.group("dquote") or m.group("bare") or ""
        fields[name] = val.strip()
    return fields


def parse_bibtex(text: str) -> list[Reference]:
    """Parse *text* (BibTeX format) and return a list of :class:`~refs_store.Reference`.

    Entries that cannot be parsed (missing author/year/title) are silently
    skipped. The parser is regex-based with no external dependencies.
    """
    refs: list[Reference] = []
    seen: list[Reference] = []

    # Find all @TYPE{KEY, positions
    for entry_match in _ENTRY_START_RE.finditer(text):
        entry_type = entry_match.group("type")
        # Skip non-entry types like @string, @preamble, @comment
        if entry_type.lower() in ("string", "preamble", "comment"):
            continue

        # Extract the body: from the char after the opening brace to the
        # matching close brace. We track brace depth.
        start = entry_match.end()
        depth = 1
        i = start
        while i < len(text) and depth > 0:
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            i += 1
        body = text[start : i - 1]

        fields = _parse_entry_body(body)

        # Required fields
        author_raw = fields.get("author", "").strip()
        title_raw = _strip_braces(fields.get("title", "").strip())

        if not author_raw or not title_raw:
            continue

        authors = _split_authors_bibtex(author_raw)
        if not authors:
            continue

        year = _extract_year_field(fields)
        if year is None:
            continue

        venue = _extract_venue_field(fields)
        doi = fields.get("doi", "").strip() or None
        url = fields.get("url", "").strip() or None
        ref_type = _bibtex_type(entry_type)
        raw_apa = _build_raw_apa_from_fields(authors, year, title_raw, venue)

        try:
            tmp = Reference(
                id="placeholder",
                authors=authors,
                year=year,
                title=title_raw,
                venue=venue,
                doi=doi,
                url=url,
                type=ref_type,  # type: ignore[arg-type]
                raw_apa=raw_apa,
            )
        except (TypeError, ValueError):
            continue

        ref_id = derive_id(tmp.model_copy(update={"id": ""}), existing=seen)
        ref = tmp.model_copy(update={"id": ref_id})
        seen.append(ref)
        refs.append(ref)

    return refs


# ---------------------------------------------------------------------------
# Serialiser
# ---------------------------------------------------------------------------

_BIBTEX_TYPE_MAP: dict[str, str] = {
    "journal": "article",
    "book": "book",
    "chapter": "incollection",
    "web": "misc",
}


def reference_to_bibtex(ref: Reference) -> str:
    """Serialise a single :class:`~refs_store.Reference` to BibTeX format.

    LaTeX special characters in string values are escaped.
    """
    bib_type = _BIBTEX_TYPE_MAP.get(ref.type, "misc")
    key = ref.id

    def _field(name: str, value: str | None) -> str | None:
        if not value:
            return None
        return f"  {name} = {{{_latex_escape(value)}}}"

    # Reconstruct author in BibTeX 'Last, First and Last, First' format
    # from APA 'Last, F.' — we just join with ' and '
    author_str = " and ".join(ref.authors)

    lines = [f"@{bib_type}{{{key},"]
    field_pairs: list[tuple[str, Any]] = [
        ("author", author_str),
        ("title", ref.title),
        ("year", str(ref.year)),
        ("journal" if ref.type == "journal" else "booktitle" if ref.type in ("chapter", "journal") else "publisher", ref.venue),
        ("doi", ref.doi),
        ("url", ref.url),
    ]

    for fname, fval in field_pairs:
        line = _field(fname, str(fval) if fval is not None else None)
        if line:
            lines.append(line + ",")

    # Trim trailing comma on last field
    if len(lines) > 1:
        lines[-1] = lines[-1].rstrip(",")

    lines.append("}")
    return "\n".join(lines)


def references_to_bibtex(refs: list[Reference]) -> str:
    """Serialise a list of :class:`~refs_store.Reference` to a BibTeX string.

    Entries are separated by a blank line. Sorted alphabetically by id.
    """
    sorted_refs = sorted(refs, key=lambda r: r.id.lower())
    return "\n\n".join(reference_to_bibtex(r) for r in sorted_refs)


__all__ = [
    "parse_bibtex",
    "reference_to_bibtex",
    "references_to_bibtex",
]
