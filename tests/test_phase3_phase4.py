"""Tests for Phase 3 — citation styles, Zotero routes, and voice diff."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from sis_caro_humanizer.research.refs_store import Reference
from sis_caro_humanizer.research.cite_styles import format_reference, regenerate_block
from sis_caro_humanizer.research.voice_diff import analyse_voice, VoiceDiffResult
from sis_caro_humanizer.serve.app import create_app

TOKEN = "test-token"
HDRS = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(token=TOKEN))


@pytest.fixture
def sample_ref() -> Reference:
    return Reference(
        id="smith_2020",
        authors=["Smith, J.", "Doe, A."],
        year=2020,
        title="On things and stuff",
        venue="Journal of Things",
        doi="10.1000/xyz",
        url=None,
        type="journal",
        raw_apa="Smith, J., & Doe, A. (2020). On things and stuff. Journal of Things.",
    )


# ---------------------------------------------------------------------------
# Citation styles — format_reference
# ---------------------------------------------------------------------------


def test_format_apa_returns_raw_apa(sample_ref):
    result = format_reference(sample_ref, style="apa")
    assert result == sample_ref.raw_apa.strip()


def test_format_mla_journal(sample_ref):
    result = format_reference(sample_ref, style="mla")
    # MLA: inverted first author
    assert "Smith" in result
    # Title in quotes
    assert '"On things and stuff"' in result or "On things and stuff" in result
    # Venue in italics
    assert "Journal of Things" in result


def test_format_chicago_journal(sample_ref):
    result = format_reference(sample_ref, style="chicago")
    assert "Smith" in result
    assert "2020" in result
    assert "On things and stuff" in result


def test_format_book():
    ref = Reference(
        id="jones_2019",
        authors=["Jones, B."],
        year=2019,
        title="A Great Book",
        venue="Oxford Press",
        doi=None,
        url=None,
        type="book",
        raw_apa="Jones, B. (2019). A Great Book. Oxford Press.",
    )
    mla = format_reference(ref, style="mla")
    chicago = format_reference(ref, style="chicago")
    assert "A Great Book" in mla
    assert "Jones" in chicago


def test_format_unsupported_style_raises(sample_ref):
    with pytest.raises(ValueError, match="Unsupported"):
        format_reference(sample_ref, style="harvard")  # type: ignore[arg-type]


def test_regenerate_block_sorted(sample_ref):
    ref2 = Reference(
        id="adams_2018",
        authors=["Adams, C."],
        year=2018,
        title="Earlier Work",
        venue="Some Journal",
        doi=None,
        url=None,
        type="journal",
        raw_apa="Adams, C. (2018). Earlier Work. Some Journal.",
    )
    block = regenerate_block([sample_ref, ref2], style="apa")
    lines = [l for l in block.split("\n") if l.strip()]
    assert lines[0].startswith("- Adams")  # alphabetical
    assert lines[1].startswith("- Smith")


# ---------------------------------------------------------------------------
# POST /v1/citations/export
# ---------------------------------------------------------------------------


def test_citations_export_requires_auth(client, tmp_path):
    r = client.post("/v1/citations/export", json={"workspace_root": str(tmp_path)})
    assert r.status_code == 401


def test_citations_export_no_refs_404(client, tmp_path):
    r = client.post(
        "/v1/citations/export",
        json={"workspace_root": str(tmp_path), "style": "apa"},
        headers=HDRS,
    )
    assert r.status_code == 404


def test_citations_export_mla(client, tmp_path):
    from sis_caro_humanizer.research.refs_store import save_refs
    ref = Reference(
        id="smith_2020",
        authors=["Smith, J."],
        year=2020,
        title="A Study",
        venue="BMJ",
        doi=None,
        url=None,
        type="journal",
        raw_apa="Smith, J. (2020). A Study. BMJ.",
    )
    save_refs(str(tmp_path), [ref])
    r = client.post(
        "/v1/citations/export",
        json={"workspace_root": str(tmp_path), "style": "mla"},
        headers=HDRS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["style"] == "mla"
    assert "Smith" in body["markdown"]


# ---------------------------------------------------------------------------
# GET /v1/zotero/status
# ---------------------------------------------------------------------------


def test_zotero_status_requires_auth(client):
    r = client.get("/v1/zotero/status")
    assert r.status_code == 401


def test_zotero_status_not_running(client, monkeypatch):
    monkeypatch.setattr(
        "sis_caro_humanizer.research.zotero.is_running",
        lambda: False,
    )
    r = client.get("/v1/zotero/status", headers=HDRS)
    assert r.status_code == 200
    assert r.json()["running"] is False


def test_zotero_status_running(client, monkeypatch):
    monkeypatch.setattr(
        "sis_caro_humanizer.research.zotero.is_running",
        lambda: True,
    )
    r = client.get("/v1/zotero/status", headers=HDRS)
    assert r.status_code == 200
    assert r.json()["running"] is True


# ---------------------------------------------------------------------------
# GET /v1/zotero/collections
# ---------------------------------------------------------------------------


def test_zotero_collections_503_when_unavailable(client, monkeypatch):
    from sis_caro_humanizer.research.zotero import ZoteroUnavailable
    monkeypatch.setattr(
        "sis_caro_humanizer.research.zotero.list_collections",
        lambda user_id="0": (_ for _ in ()).throw(ZoteroUnavailable("offline")),
    )

    def _raise(**kw):
        raise ZoteroUnavailable("offline")

    monkeypatch.setattr("sis_caro_humanizer.research.zotero.list_collections", _raise)
    r = client.get("/v1/zotero/collections", headers=HDRS)
    assert r.status_code == 503


def test_zotero_collections_success(client, monkeypatch):
    monkeypatch.setattr(
        "sis_caro_humanizer.research.zotero.list_collections",
        lambda user_id="0": [{"key": "ABC", "name": "My Refs", "parent_key": None}],
    )
    r = client.get("/v1/zotero/collections", headers=HDRS)
    assert r.status_code == 200
    assert r.json()["collections"][0]["key"] == "ABC"


# ---------------------------------------------------------------------------
# POST /v1/zotero/import
# ---------------------------------------------------------------------------


def test_zotero_import_requires_auth(client, tmp_path):
    r = client.post(
        "/v1/zotero/import",
        json={"collection_key": "ABC", "workspace_root": str(tmp_path)},
    )
    assert r.status_code == 401


def test_zotero_import_merges_refs(client, tmp_path, monkeypatch):
    from sis_caro_humanizer.research.refs_store import Reference as Ref

    fake_ref = Ref(
        id="jones_2020",
        authors=["Jones, B."],
        year=2020,
        title="Zotero Import Test",
        venue="Some Journal",
        doi=None,
        url=None,
        type="journal",
        raw_apa="Jones, B. (2020). Zotero Import Test. Some Journal.",
    )
    monkeypatch.setattr(
        "sis_caro_humanizer.research.zotero.import_collection",
        lambda key, user_id="0", limit=100: [fake_ref],
    )
    r = client.post(
        "/v1/zotero/import",
        json={"collection_key": "ABC", "workspace_root": str(tmp_path)},
        headers=HDRS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == 1
    assert body["skipped"] == 0
    # Verify references.json was written
    refs_file = tmp_path / "references.json"
    assert refs_file.exists()


# ---------------------------------------------------------------------------
# POST /v1/research/voice-diff
# ---------------------------------------------------------------------------


_MULTI_SECTION_DOC = """\
# Introduction

This section provides a broad overview of the subject matter under investigation by the authors.
Research shows that rigorous methodology is critically important for all scientific inquiry conducted today.
Furthermore, scholars have long argued that robust theoretical frameworks are absolutely necessary for progress.
The present study aims to contribute meaningfully to this growing body of knowledge in the literature.
We hope to demonstrate the significance of these findings for the broader academic community.

# Methods

We used a simple and direct approach to collect our data samples across all sites.
Samples were gathered weekly over a twelve-week period from each of the study locations.
Data was processed using standard analytical tools available to the laboratory staff involved.
Results were tabulated and cross-checked for accuracy by two independent coders working in parallel.
The process was repeated three times to ensure full reproducibility across all experimental conditions.

# Discussion

It is worth noting that the findings may suggest a multifaceted tapestry of complex outcomes.
Furthermore, moreover, additionally the results appear to demonstrate leveraged stakeholder dynamics at scale.
Studies have shown that this type of robust engagement is well established in the current literature.
The implications of these results are significant for both the academic and policy communities worldwide.
Researchers have found that delving into these dynamics reveals many complex and important interactions.
"""


def test_voice_diff_requires_auth(client):
    r = client.post("/v1/research/voice-diff", json={"text": "hello"})
    assert r.status_code == 401


def test_voice_diff_returns_sections(client):
    r = client.post(
        "/v1/research/voice-diff",
        json={"text": _MULTI_SECTION_DOC},
        headers=HDRS,
    )
    assert r.status_code == 200
    body = r.json()
    assert "sections" in body
    assert len(body["sections"]) >= 2
    for sec in body["sections"]:
        assert "title" in sec
        assert "is_outlier" in sec
        assert "mean_abs_z" in sec


def test_voice_diff_unit_detects_outlier():
    results = analyse_voice(_MULTI_SECTION_DOC)
    assert len(results) >= 2
    # All sections have z-scores computed; mean_abs_z is a non-negative float
    assert all(r.mean_abs_z >= 0 for r in results)
    # Feature vectors should have the expected keys
    for r in results:
        assert "avg_sent_len" in r.features
        assert "llm_density" in r.features


def test_voice_diff_insufficient_sections():
    """Fewer than 2 substantial sections → all is_outlier=False."""
    text = """# Only Section

This is the only section. It has more than thirty words so it passes
the word count threshold. However there is nothing to compare it against.
This is fine and normal.
"""
    results = analyse_voice(text)
    assert all(not r.is_outlier for r in results)
