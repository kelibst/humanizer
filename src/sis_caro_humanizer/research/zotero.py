"""Zotero local-API integration (Phase 3).

Zotero exposes a REST API on ``http://localhost:23119/api/`` when running.
This module wraps the minimal subset needed by the humanizer daemon:

* :func:`is_running`    — quick HEAD request to verify Zotero is up.
* :func:`list_collections` — GET collections for the local library.
* :func:`import_collection` — pull items from a collection and convert
  them to :class:`~sis_caro_humanizer.research.refs_store.Reference` records.

All HTTP calls use ``urllib.request`` so there is no third-party HTTP
dependency.

Environment
-----------
``ZOTERO_API_KEY`` — optional; required for Zotero cloud sync.  For the
*local* Zotero instance (the daemon on 23119) requests work without a key
but the key is forwarded if set.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .refs_store import Reference

ZOTERO_BASE = "http://localhost:23119/api"
_TIMEOUT = 4.0  # seconds; Zotero is local so 4 s is generous


class ZoteroUnavailable(Exception):
    """Raised when the Zotero local API is not reachable."""


class ZoteroError(Exception):
    """Raised for API errors (4xx / 5xx) from Zotero."""


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _headers() -> dict[str, str]:
    hdrs: dict[str, str] = {
        "Accept": "application/json",
        "Zotero-API-Version": "3",
    }
    key = os.environ.get("ZOTERO_API_KEY", "").strip()
    if key:
        hdrs["Zotero-API-Key"] = key
    return hdrs


def _get(path: str) -> Any:
    url = f"{ZOTERO_BASE}{path}"
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise ZoteroUnavailable(
            f"Zotero local API not reachable at {ZOTERO_BASE}: {exc.reason}"
        ) from exc
    except urllib.error.HTTPError as exc:
        raise ZoteroError(f"Zotero API error {exc.code}: {exc.reason}") from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_running() -> bool:
    """Return True if the Zotero local API is responding."""
    try:
        _get("/users/0/items?limit=1")
        return True
    except (ZoteroUnavailable, ZoteroError):
        return False


def list_collections(user_id: str = "0") -> list[dict[str, Any]]:
    """Return a list of ``{key, name, parent_key}`` dicts for the local library.

    Parameters
    ----------
    user_id:
        Zotero user ID.  Defaults to ``"0"`` which Zotero's local API accepts
        as the currently logged-in user.

    Returns
    -------
    list of dicts with ``key`` (str), ``name`` (str), ``parent_key`` (str|None).
    """
    raw = _get(f"/users/{user_id}/collections")
    out: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        data = item.get("data", {}) if isinstance(item, dict) else {}
        out.append(
            {
                "key": item.get("key", ""),
                "name": data.get("name", ""),
                "parent_key": data.get("parentCollection") or None,
            }
        )
    return out


def _zotero_item_to_reference(item: dict[str, Any]) -> Reference | None:
    """Convert a Zotero item dict to a :class:`Reference`.

    Returns ``None`` for note/attachment items and items missing required fields.
    """
    data = item.get("data", {})
    item_type = data.get("itemType", "")
    if item_type in ("note", "attachment"):
        return None

    creators = data.get("creators", [])
    authors: list[str] = []
    for c in creators:
        creator_type = c.get("creatorType", "")
        if creator_type not in ("author", "editor", ""):
            continue
        last = c.get("lastName", "").strip()
        first = c.get("firstName", "").strip()
        if last and first:
            authors.append(f"{last}, {first[0]}.")
        elif last:
            authors.append(last)
        elif first:
            authors.append(first)
    if not authors:
        authors = ["[Unknown]"]

    year_raw = data.get("date", "")
    year_match = __import__("re").search(r"\d{4}", year_raw)
    year = int(year_match.group()) if year_match else 0
    if year < 1500 or year > 2100:
        return None

    title = data.get("title", "").strip()
    if not title:
        return None

    venue = (
        data.get("publicationTitle")
        or data.get("publisher")
        or data.get("bookTitle")
        or data.get("websiteTitle")
        or ""
    ).strip() or None

    doi = (data.get("DOI") or "").strip() or None
    url = (data.get("url") or "").strip() or None

    # Map Zotero itemType → our Literal type
    _TYPE_MAP = {
        "journalArticle": "journal",
        "book": "book",
        "bookSection": "chapter",
        "webpage": "web",
        "conferencePaper": "journal",  # approximate
        "report": "web",
        "thesis": "book",
    }
    ref_type = _TYPE_MAP.get(item_type, "web")

    # Synthesise a minimal APA-7 string
    if len(authors) > 5:
        author_str = ", ".join(authors[:5]) + ", ... " + authors[-1]
    elif len(authors) > 2:
        author_str = ", ".join(authors[:-1]) + ", & " + authors[-1]
    elif len(authors) == 2:
        author_str = authors[0] + " & " + authors[1]
    else:
        author_str = authors[0]

    raw_apa = f"{author_str} ({year}). {title}."
    if venue:
        raw_apa += f" {venue}."
    if doi:
        raw_apa += f" https://doi.org/{doi}"

    try:
        from .refs_store import Reference as _Ref, derive_id
        tmp = _Ref.model_validate(
            {
                "id": "placeholder",
                "authors": authors,
                "year": year,
                "title": title,
                "venue": venue,
                "doi": doi,
                "url": url,
                "type": ref_type,
                "raw_apa": raw_apa,
            }
        )
        new_id = derive_id(tmp.model_copy(update={"id": ""}), existing=[])
        return tmp.model_copy(update={"id": new_id})
    except (TypeError, ValueError):
        return None


def import_collection(
    collection_key: str,
    *,
    user_id: str = "0",
    limit: int = 100,
) -> list[Reference]:
    """Pull items from a Zotero collection and convert to Reference records.

    Parameters
    ----------
    collection_key:
        Zotero collection key (e.g. ``"ABCD1234"``).
    user_id:
        Zotero user ID (default ``"0"`` for local library).
    limit:
        Max items to retrieve (Zotero max per request is 100).

    Returns
    -------
    List of valid :class:`Reference` records (invalid items silently skipped).
    """
    raw = _get(
        f"/users/{user_id}/collections/{collection_key}/items"
        f"?itemType=-attachment&limit={min(limit, 100)}"
    )
    if not isinstance(raw, list):
        return []
    refs: list[Reference] = []
    for item in raw:
        ref = _zotero_item_to_reference(item)
        if ref is not None:
            refs.append(ref)
    return refs


__all__ = [
    "ZOTERO_BASE",
    "ZoteroError",
    "ZoteroUnavailable",
    "import_collection",
    "is_running",
    "list_collections",
]
