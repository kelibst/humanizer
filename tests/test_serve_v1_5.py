"""End-to-end smoke tests for the v1.5 daemon routes (CONTRACT v1.5 §3).

All HTTP calls and pipeline calls are mocked so no network or Ollama is needed.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from sis_caro_humanizer.research.refs_store import Reference
from sis_caro_humanizer.serve.app import create_app

TOKEN = "test-token"
HDRS = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(token=TOKEN))


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> str:
    return str(tmp_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_ref(**kwargs) -> Reference:
    defaults = {
        "id": "smith_2020",
        "authors": ["Smith, J."],
        "year": 2020,
        "title": "Test Paper",
        "type": "journal",
        "raw_apa": "Smith, J. (2020). Test Paper.",
    }
    defaults.update(kwargs)
    return Reference(**defaults)


# ---------------------------------------------------------------------------
# POST /v1/refs/doi-lookup
# ---------------------------------------------------------------------------


def test_doi_lookup_requires_auth(client):
    r = client.post("/v1/refs/doi-lookup", json={"doi": "10.1000/xyz"})
    assert r.status_code == 401


def test_doi_lookup_not_found_returns_404(client):
    from sis_caro_humanizer.research.doi import DoiNotFound
    import sis_caro_humanizer.research.doi as doi_mod

    orig = doi_mod.lookup_doi
    doi_mod.lookup_doi = MagicMock(side_effect=DoiNotFound("not found"))
    try:
        r = client.post("/v1/refs/doi-lookup", json={"doi": "10.9999/missing"}, headers=HDRS)
    finally:
        doi_mod.lookup_doi = orig

    assert r.status_code == 404
    assert r.json()["error"] == "doi_not_found"


def test_doi_lookup_happy_path(client):
    import sis_caro_humanizer.research.doi as doi_mod

    fake_result = {
        "authors": ["Smith, J."],
        "year": 2020,
        "title": "A Paper",
        "venue": "BMJ",
        "doi": "10.1000/xyz",
        "type": "journal",
        "raw_apa": "Smith, J. (2020). A Paper. BMJ.",
    }
    orig = doi_mod.lookup_doi
    doi_mod.lookup_doi = MagicMock(return_value=fake_result)
    try:
        r = client.post("/v1/refs/doi-lookup", json={"doi": "10.1000/xyz"}, headers=HDRS)
    finally:
        doi_mod.lookup_doi = orig

    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "A Paper"
    assert body["year"] == 2020


def test_doi_lookup_502_on_lookup_error(client):
    from sis_caro_humanizer.research.doi import DoiLookupError
    import sis_caro_humanizer.research.doi as doi_mod

    orig = doi_mod.lookup_doi
    doi_mod.lookup_doi = MagicMock(side_effect=DoiLookupError("unreachable"))
    try:
        r = client.post("/v1/refs/doi-lookup", json={"doi": "10.1000/xyz"}, headers=HDRS)
    finally:
        doi_mod.lookup_doi = orig

    assert r.status_code == 502
    assert r.json()["error"] == "doi_lookup_error"


# ---------------------------------------------------------------------------
# POST /v1/refs/bibtex-import
# ---------------------------------------------------------------------------


_SIMPLE_BIB = """@article{smith20,
  author = {Smith, John},
  title = {A Test Paper},
  journal = {Journal of Tests},
  year = {2020},
}"""


def test_bibtex_import_requires_auth(client, tmp_workspace):
    r = client.post(
        "/v1/refs/bibtex-import",
        json={"bibtex_text": _SIMPLE_BIB, "workspace_root": tmp_workspace},
    )
    assert r.status_code == 401


def test_bibtex_import_one_entry(client, tmp_workspace):
    r = client.post(
        "/v1/refs/bibtex-import",
        json={"bibtex_text": _SIMPLE_BIB, "workspace_root": tmp_workspace},
        headers=HDRS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == 1
    assert body["skipped"] == 0
    assert len(body["refs"]) == 1
    # Verify saved to disk.
    refs_file = Path(tmp_workspace) / "references.json"
    assert refs_file.exists()


def test_bibtex_import_collision_skipped(client, tmp_workspace):
    # Import twice — second should be skipped.
    r1 = client.post(
        "/v1/refs/bibtex-import",
        json={"bibtex_text": _SIMPLE_BIB, "workspace_root": tmp_workspace},
        headers=HDRS,
    )
    assert r1.json()["imported"] == 1

    r2 = client.post(
        "/v1/refs/bibtex-import",
        json={"bibtex_text": _SIMPLE_BIB, "workspace_root": tmp_workspace},
        headers=HDRS,
    )
    body2 = r2.json()
    assert body2["skipped"] == 1
    assert body2["imported"] == 0


# ---------------------------------------------------------------------------
# GET /v1/refs/bibtex-export
# ---------------------------------------------------------------------------


def test_bibtex_export_requires_auth(client, tmp_workspace):
    r = client.get(f"/v1/refs/bibtex-export?workspace_root={tmp_workspace}")
    assert r.status_code == 401


def test_bibtex_export_no_refs_returns_404(client, tmp_workspace):
    r = client.get(
        f"/v1/refs/bibtex-export?workspace_root={tmp_workspace}",
        headers=HDRS,
    )
    assert r.status_code == 404


def test_bibtex_export_returns_bib_text(client, tmp_workspace):
    from sis_caro_humanizer.research.refs_store import save_refs

    save_refs(tmp_workspace, [_sample_ref()])
    r = client.get(
        f"/v1/refs/bibtex-export?workspace_root={tmp_workspace}",
        headers=HDRS,
    )
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    assert "references.bib" in r.headers["content-disposition"]
    assert "@article{smith_2020," in r.text


# ---------------------------------------------------------------------------
# POST /v1/refs/batch-stub
# ---------------------------------------------------------------------------


def test_batch_stub_requires_auth(client, tmp_workspace):
    r = client.post(
        "/v1/refs/batch-stub",
        json={"orphan_keys": ["(Smith, 2020)"], "workspace_root": tmp_workspace},
    )
    assert r.status_code == 401


def test_batch_stub_creates_stub_ref(client, tmp_workspace):
    r = client.post(
        "/v1/refs/batch-stub",
        json={"orphan_keys": ["(Smith, 2020)"], "workspace_root": tmp_workspace},
        headers=HDRS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 1
    assert body["skipped"] == 0
    ref = body["refs"][0]
    assert ref["title"] == "[TITLE UNKNOWN]"
    assert ref["year"] == 2020
    assert "Smith" in ref["authors"][0]


def test_batch_stub_multiple_keys(client, tmp_workspace):
    r = client.post(
        "/v1/refs/batch-stub",
        json={
            "orphan_keys": ["(Smith, 2020)", "(Jones et al., 2019)"],
            "workspace_root": tmp_workspace,
        },
        headers=HDRS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 2


def test_batch_stub_invalid_key_partial(client, tmp_workspace):
    """Mix of valid and invalid keys: valid ones succeed, invalid ones skipped."""
    r = client.post(
        "/v1/refs/batch-stub",
        json={
            "orphan_keys": ["(Smith, 2020)", "not a key"],
            "workspace_root": tmp_workspace,
        },
        headers=HDRS,
    )
    # Should succeed with 1 created, 1 parse error
    assert r.status_code == 200
    assert r.json()["created"] == 1


# ---------------------------------------------------------------------------
# POST /v1/transform/stream
# ---------------------------------------------------------------------------


def test_transform_stream_requires_auth(client):
    r = client.post("/v1/transform/stream", json={"text": "hello"})
    assert r.status_code == 401


def test_transform_stream_returns_sse(client):
    """Smoke: stream returns SSE frames containing 'done' event."""
    from sis_caro_humanizer.pipeline.runner import PipelineResult
    from sis_caro_humanizer.scoring.risk import ScoreReport, FeatureContribution

    def _fake_score(text, prof):
        return ScoreReport(
            score=0.5, raw_weighted_sum=0.5, components=[], band="medium"
        )

    fake_score = ScoreReport(score=0.3, raw_weighted_sum=0.3, components=[], band="low")
    fake_result = PipelineResult(
        input="hello",
        output="hello world",
        pre_score=fake_score,
        post_score=fake_score,
        llm_used=False,
        elapsed_seconds=0.01,
    )

    app = create_app(
        token=TOKEN,
        pipeline_runner=lambda *a, **kw: fake_result,
        score_runner=_fake_score,
    )
    tc = TestClient(app)
    r = tc.post(
        "/v1/transform/stream",
        json={"text": "hello", "stages": ["prescan", "postscan"]},
        headers=HDRS,
    )
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    # Parse all SSE frames
    frames = []
    for line in r.text.split("\n"):
        if line.startswith("data: "):
            frames.append(json.loads(line[6:]))
    types = [f["type"] for f in frames]
    assert "done" in types
    done = next(f for f in frames if f["type"] == "done")
    assert done["output"] == "hello world"
    assert done["llm_used"] is False
