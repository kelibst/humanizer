"""Tests for research.refs_store (CONTRACT v1.3 §3.1, §1.5–1.7)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sis_caro_humanizer.research.refs_store import (
    REFS_END_MARKER,
    REFS_START_MARKER,
    Reference,
    derive_id,
    load_refs,
    parse_apa_block,
    parse_orphan_key,
    regenerate_apa_block,
    save_refs,
    update_markdown_references_block,
    upsert,
)


def _ref(authors: list[str], year: int, title: str = "T", rid: str = "x") -> Reference:
    return Reference(
        id=rid,
        authors=authors,
        year=year,
        title=title,
        type="journal",
        raw_apa=f"{', '.join(authors)} ({year}). {title}.",
    )


# ---------------------------------------------------------------------------
# id derivation
# ---------------------------------------------------------------------------


def test_derive_id_basic_lastname_year():
    r = _ref(["Smith, J."], 2020)
    rid = derive_id(r.model_copy(update={"id": ""}), existing=[])
    assert rid == "smith_2020"


def test_derive_id_collision_suffix():
    r1 = _ref(["Smith, J."], 2020, rid="smith_2020")
    r2 = _ref(["Smith, K."], 2020)
    rid = derive_id(r2.model_copy(update={"id": ""}), existing=[r1])
    assert rid == "smith_2020a"
    # Three colliding records advance through suffixes.
    r3 = _ref(["Smith, L."], 2020, rid="smith_2020a")
    rid2 = derive_id(_ref(["Smith, M."], 2020).model_copy(update={"id": ""}), existing=[r1, r3])
    assert rid2 == "smith_2020b"


def test_derive_id_handles_first_first_authors():
    r = _ref(["John Smith"], 2020)
    rid = derive_id(r.model_copy(update={"id": ""}), existing=[])
    assert rid.startswith("smith_2020")


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------


def test_upsert_inserts_new():
    refs: list[Reference] = []
    new_refs, canonical = upsert(refs, _ref(["Smith, J."], 2020).model_copy(update={"id": ""}))
    assert canonical.id == "smith_2020"
    assert len(new_refs) == 1


def test_upsert_replaces_existing_by_id():
    r1 = _ref(["Smith, J."], 2020, title="Old", rid="smith_2020")
    refs = [r1]
    updated = _ref(["Smith, J."], 2020, title="New", rid="smith_2020")
    new_refs, canonical = upsert(refs, updated)
    assert len(new_refs) == 1
    assert new_refs[0].title == "New"
    assert canonical.id == "smith_2020"


def test_upsert_accepts_dict_payload():
    payload = {
        "authors": ["Smith, J."],
        "year": 2020,
        "title": "T",
        "type": "journal",
        "raw_apa": "Smith, J. (2020). T.",
    }
    new_refs, canonical = upsert([], payload)
    assert canonical.id == "smith_2020"
    assert len(new_refs) == 1


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_load_refs_missing_file_returns_empty(tmp_path: Path):
    assert load_refs(tmp_path) == []


def test_load_refs_lazy_does_not_create(tmp_path: Path):
    load_refs(tmp_path)
    assert not (tmp_path / "references.json").exists()


def test_save_then_load_round_trip(tmp_path: Path):
    refs = [_ref(["Smith, J."], 2020, rid="smith_2020"), _ref(["Doe, A."], 2019, rid="doe_2019")]
    save_refs(tmp_path, refs)
    out = load_refs(tmp_path)
    assert {r.id for r in out} == {"smith_2020", "doe_2019"}


def test_load_refs_skips_malformed(tmp_path: Path):
    (tmp_path / "references.json").write_text(
        json.dumps({"refs": [{"id": "x"}, {"id": "y", "authors": ["A"], "year": 2020, "title": "T", "type": "journal", "raw_apa": "x"}]}),
        encoding="utf-8",
    )
    out = load_refs(tmp_path)
    assert len(out) == 1
    assert out[0].id == "y"


# ---------------------------------------------------------------------------
# APA parse + regenerate
# ---------------------------------------------------------------------------


APA_BLOCK_DOC = """\
# Title

## References

- Smith, J., & Doe, A. (2020). On things. *J. Things*, 12(3), 45-67.
- Tan, B. (2018). Other things. *Other J.*, 1(1), 1-2.
"""


def test_parse_apa_block_extracts_records():
    refs = parse_apa_block(APA_BLOCK_DOC)
    assert len(refs) == 2
    assert any("Smith" in r.authors[0] for r in refs)
    assert any(r.year == 2018 for r in refs)


def test_parse_apa_block_marker_block_priority():
    text = (
        "## References\n\n"
        f"{REFS_START_MARKER}\n"
        "- Inside, M. (2021). Marker block.\n"
        f"{REFS_END_MARKER}\n"
        "\n"
        "- Outside, O. (1999). Should be ignored.\n"
    )
    refs = parse_apa_block(text)
    titles = [r.title for r in refs]
    assert "Marker block" in titles
    assert "Should be ignored" not in titles


def test_regenerate_sorts_by_lastname_year_title():
    refs = [
        _ref(["Tan, B."], 2018, title="Other things", rid="tan_2018"),
        _ref(["Smith, J."], 2020, title="On things", rid="smith_2020"),
        _ref(["Smith, J."], 2018, title="A first", rid="smith_2018"),
    ]
    block = regenerate_apa_block(refs)
    s_idx = block.index("Smith, J.")
    s2_idx = block.index("On things")
    t_idx = block.index("Tan, B.")
    assert s_idx < s2_idx < t_idx


def test_regenerate_uses_markers():
    refs = [_ref(["Smith, J."], 2020, rid="smith_2020")]
    block = regenerate_apa_block(refs)
    assert block.startswith(REFS_START_MARKER)
    assert block.endswith(REFS_END_MARKER)


# ---------------------------------------------------------------------------
# Marker-aware regenerate (full document update)
# ---------------------------------------------------------------------------


def test_update_markdown_references_block_inserts_when_no_heading():
    text = "# Title\n\nSome body text.\n"
    refs = [_ref(["Smith, J."], 2020, rid="smith_2020")]
    updated = update_markdown_references_block(text, refs)
    assert "## References" in updated
    assert REFS_START_MARKER in updated
    assert REFS_END_MARKER in updated


def test_update_markdown_references_block_replaces_marker_content():
    text = (
        "# Title\n\n"
        "Body.\n\n"
        "## References\n\n"
        f"{REFS_START_MARKER}\n"
        "- Old, X. (1900). Stale.\n"
        f"{REFS_END_MARKER}\n"
    )
    refs = [_ref(["Smith, J."], 2020, rid="smith_2020")]
    updated = update_markdown_references_block(text, refs)
    assert "Stale" not in updated
    assert "Smith" in updated


def test_update_markdown_references_block_inserts_markers_around_existing_list():
    text = (
        "# Title\n\n"
        "Body.\n\n"
        "## References\n\n"
        "- Some, Old. (1990). Pre-marker entry.\n"
    )
    refs = [_ref(["Smith, J."], 2020, rid="smith_2020")]
    updated = update_markdown_references_block(text, refs)
    assert REFS_START_MARKER in updated
    assert REFS_END_MARKER in updated
    assert "Smith" in updated


def test_round_trip_parse_then_regenerate():
    parsed = parse_apa_block(APA_BLOCK_DOC)
    block = regenerate_apa_block(parsed)
    parsed2 = parse_apa_block(
        "## References\n\n" + block + "\n"
    )
    titles_1 = sorted(r.title for r in parsed)
    titles_2 = sorted(r.title for r in parsed2)
    assert titles_1 == titles_2


# ---------------------------------------------------------------------------
# parse_orphan_key (CONTRACT v1.5 §1)
# ---------------------------------------------------------------------------


def test_parse_orphan_key_single_author():
    names, year = parse_orphan_key("(Smith, 2020)")
    assert names == ["Smith"]
    assert year == 2020


def test_parse_orphan_key_et_al():
    names, year = parse_orphan_key("(Smith et al., 2019)")
    assert names == ["Smith"]
    assert year == 2019


def test_parse_orphan_key_two_authors_ampersand():
    names, year = parse_orphan_key("(Smith & Doe, 2021)")
    assert names == ["Smith", "Doe"]
    assert year == 2021


def test_parse_orphan_key_page_suffix_stripped():
    names, year = parse_orphan_key("(Jones, 2018, p. 42)")
    assert names == ["Jones"]
    assert year == 2018


def test_parse_orphan_key_invalid_raises():
    with pytest.raises(ValueError):
        parse_orphan_key("not a citation")
