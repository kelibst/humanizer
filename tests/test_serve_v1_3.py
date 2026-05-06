"""End-to-end smoke tests for the v1.3 research-aid routes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sis_caro_humanizer.serve.app import create_app

TOKEN = "test-token"
HDRS = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(token=TOKEN))


# ---------------------------------------------------------------------------
# Auth — every new route requires a bearer token (BRIDGE_CONTRACT §2)
# ---------------------------------------------------------------------------


def test_lint_requires_auth(client):
    r = client.post("/v1/lint", json={"text": "x"})
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorised"


def test_checklist_requires_auth(client):
    r = client.post("/v1/checklist", json={"text": "x"})
    assert r.status_code == 401


def test_readability_requires_auth(client):
    r = client.post("/v1/readability", json={"text": "x"})
    assert r.status_code == 401


def test_citations_requires_auth(client, tmp_path):
    r = client.post(
        "/v1/citations",
        json={"text": "x", "workspace_root": str(tmp_path)},
    )
    assert r.status_code == 401


def test_refs_get_requires_auth(client, tmp_path):
    r = client.get("/v1/refs", params={"workspace_root": str(tmp_path)})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# /v1/lint
# ---------------------------------------------------------------------------


def test_lint_returns_spans_for_llm_vocab(client):
    text = "We delve into the multifaceted tapestry of stakeholder dynamics."
    r = client.post("/v1/lint", json={"text": text}, headers=HDRS)
    assert r.status_code == 200
    body = r.json()
    assert "spans" in body
    assert "elapsed_ms" in body
    codes = {s["code"] for s in body["spans"]}
    assert "llm-vocab" in codes


def test_lint_rejects_unknown_code(client):
    r = client.post(
        "/v1/lint",
        json={"text": "x", "include": ["bogus"]},
        headers=HDRS,
    )
    assert r.status_code == 422


def test_lint_can_filter_by_include(client):
    text = "We delve into things. The studies show 70% improvement."
    r = client.post(
        "/v1/lint",
        json={"text": text, "include": ["llm-vocab"]},
        headers=HDRS,
    )
    assert r.status_code == 200
    spans = r.json()["spans"]
    codes = {s["code"] for s in spans}
    assert codes <= {"llm-vocab"}


# ---------------------------------------------------------------------------
# /v1/checklist
# ---------------------------------------------------------------------------


def test_checklist_returns_sections(client):
    text = """\
# Title

## Introduction

Despite three decades of research, the problem remains unclear. There is
little research on this. This study aims to investigate the issue. The
remainder of this chapter is organised as follows.
"""
    r = client.post("/v1/checklist", json={"text": text}, headers=HDRS)
    assert r.status_code == 200
    sections = r.json()["sections"]
    intro = next(s for s in sections if s["heading"] == "Introduction")
    assert intro["type"] == "introduction"
    assert intro["score"].endswith("/5")


# ---------------------------------------------------------------------------
# /v1/readability
# ---------------------------------------------------------------------------


def test_readability_metrics_present(client):
    text = "The cat sat. The dog ran. Birds fly high above the trees."
    r = client.post("/v1/readability", json={"text": text}, headers=HDRS)
    assert r.status_code == 200
    body = r.json()
    assert "metrics" in body
    assert "targets" in body
    m = body["metrics"]
    assert m["sentence_count"] == 3
    assert m["word_count"] > 0


# ---------------------------------------------------------------------------
# /v1/citations
# ---------------------------------------------------------------------------


def test_citations_with_empty_workspace(client, tmp_path):
    r = client.post(
        "/v1/citations",
        json={"text": "Studies show 60% improvement.", "workspace_root": str(tmp_path)},
        headers=HDRS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["missing"]
    assert body["unused"] == []


def test_citations_with_existing_refs(client, tmp_path):
    refs_path = tmp_path / "references.json"
    refs_path.write_text(
        json.dumps(
            {
                "refs": [
                    {
                        "id": "smith_2020",
                        "authors": ["Smith, J."],
                        "year": 2020,
                        "title": "On things",
                        "type": "journal",
                        "raw_apa": "Smith, J. (2020). On things.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    text = "Approximately 70% of patients improved (Smith, 2020)."
    r = client.post(
        "/v1/citations",
        json={"text": text, "workspace_root": str(tmp_path)},
        headers=HDRS,
    )
    assert r.status_code == 200
    body = r.json()
    # No orphans (cite resolves), no unused (cited), and the claim is
    # supported by the proximate citation, so missing should be empty too.
    assert body["orphans"] == []
    assert body["unused"] == []


# ---------------------------------------------------------------------------
# /v1/refs CRUD
# ---------------------------------------------------------------------------


def test_refs_get_empty_workspace(client, tmp_path):
    r = client.get(
        "/v1/refs",
        params={"workspace_root": str(tmp_path)},
        headers=HDRS,
    )
    assert r.status_code == 200
    assert r.json() == {"refs": []}
    # Important: the route must NOT create the file lazily on GET.
    assert not (tmp_path / "references.json").exists()


def test_refs_post_creates_and_persists(client, tmp_path):
    body = {
        "workspace_root": str(tmp_path),
        "authors": ["Smith, J."],
        "year": 2020,
        "title": "On things",
        "type": "journal",
    }
    r = client.post("/v1/refs", json=body, headers=HDRS)
    assert r.status_code == 200
    canonical = r.json()
    assert canonical["id"] == "smith_2020"
    assert (tmp_path / "references.json").exists()


def test_refs_post_with_document_path_updates_markdown(client, tmp_path):
    doc_path = tmp_path / "draft.md"
    doc_path.write_text("# Title\n\nBody.\n", encoding="utf-8")
    body = {
        "workspace_root": str(tmp_path),
        "document_path": str(doc_path),
        "authors": ["Smith, J."],
        "year": 2020,
        "title": "On things",
        "type": "journal",
    }
    r = client.post("/v1/refs", json=body, headers=HDRS)
    assert r.status_code == 200
    new_text = doc_path.read_text(encoding="utf-8")
    assert "## References" in new_text
    assert "humanizer:refs:start" in new_text


def test_refs_delete_404_when_id_missing(client, tmp_path):
    r = client.delete(
        "/v1/refs/nope",
        params={"workspace_root": str(tmp_path)},
        headers=HDRS,
    )
    assert r.status_code == 404
    assert r.json()["error"] == "not_found"


def test_refs_delete_removes_existing(client, tmp_path):
    # Seed a refs file.
    refs_path = tmp_path / "references.json"
    refs_path.write_text(
        json.dumps(
            {
                "refs": [
                    {
                        "id": "smith_2020",
                        "authors": ["Smith, J."],
                        "year": 2020,
                        "title": "T",
                        "type": "journal",
                        "raw_apa": "Smith, J. (2020). T.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    r = client.delete(
        "/v1/refs/smith_2020",
        params={"workspace_root": str(tmp_path)},
        headers=HDRS,
    )
    assert r.status_code == 200
    assert r.json() == {"deleted": True}
    raw = json.loads(refs_path.read_text(encoding="utf-8"))
    assert raw["refs"] == []


def test_refs_post_invalid_payload_400_or_422(client, tmp_path):
    # Missing required fields → Pydantic raises 422.
    r = client.post(
        "/v1/refs",
        json={"workspace_root": str(tmp_path)},
        headers=HDRS,
    )
    assert r.status_code == 422
