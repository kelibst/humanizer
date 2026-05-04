"""End-to-end tests for the FastAPI bridge.

We use FastAPI's ``TestClient`` so no real network/uvicorn is involved. The
pipeline runner is monkeypatched in tests that need to exercise the LLM-error
fallback path; the rest let the real (deterministic-only) pipeline run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sis_caro_humanizer.pipeline.runner import ALL_STAGES, PipelineResult
from sis_caro_humanizer.scoring.risk import ScoreReport
from sis_caro_humanizer.serve.app import VERSION, create_app

TOKEN = "test-token"
HDRS = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client():
    app = create_app(token=TOKEN)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_health_requires_auth(client):
    r = client.get("/v1/health")
    assert r.status_code == 401
    body = r.json()
    assert body["error"] == "unauthorised"


def test_health_with_wrong_token(client):
    r = client.get("/v1/health", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_health_ok_shape(client):
    r = client.get("/v1/health", headers=HDRS)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["version"] == VERSION
    assert body["backends_available"] == ["ollama", "anthropic", "openai", "gemini"]
    assert isinstance(body["backends_configured"], list)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


def test_cors_preflight_for_docs_origin(client):
    r = client.options(
        "/v1/score",
        headers={
            "Origin": "https://docs.google.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == "https://docs.google.com"


def test_cors_blocks_unknown_origin(client):
    r = client.options(
        "/v1/score",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    # FastAPI returns 400 or no allow-origin header for unknown origins.
    assert r.headers.get("access-control-allow-origin") != "https://evil.example.com"


# ---------------------------------------------------------------------------
# /v1/profiles
# ---------------------------------------------------------------------------


def test_profiles_lists_default(client):
    r = client.get("/v1/profiles", headers=HDRS)
    assert r.status_code == 200
    body = r.json()
    assert "profiles" in body
    names = [p["name"] for p in body["profiles"]]
    assert "default_ghanaian" in names
    bundled = next(p for p in body["profiles"] if p["name"] == "default_ghanaian")
    assert bundled["dialect"] == "ghanaian"


# ---------------------------------------------------------------------------
# /v1/score
# ---------------------------------------------------------------------------


SAMPLE_HUMAN = "We looked at the survey results. Some patterns matter more than others."


def test_score_returns_report_shape(client):
    r = client.post(
        "/v1/score",
        json={"text": SAMPLE_HUMAN},
        headers=HDRS,
    )
    assert r.status_code == 200
    body = r.json()
    assert 0.0 <= body["score"] <= 1.0
    assert body["band"] in ("low", "medium", "high")
    assert isinstance(body["components"], list)
    assert all("name" in c and "value" in c and "weight" in c for c in body["components"])


def test_score_rejects_oversize_text(client):
    huge = "x" * 100_001
    r = client.post("/v1/score", json={"text": huge}, headers=HDRS)
    assert r.status_code == 422


def test_score_rejects_unknown_profile(client):
    r = client.post(
        "/v1/score",
        json={"text": SAMPLE_HUMAN, "profile": "no-such-profile"},
        headers=HDRS,
    )
    assert r.status_code == 400
    assert r.json()["error"] == "not_found"


# ---------------------------------------------------------------------------
# /v1/transform — uses real pipeline with LLM stage skipped
# ---------------------------------------------------------------------------


def test_transform_deterministic_only(client):
    r = client.post(
        "/v1/transform",
        json={
            "text": SAMPLE_HUMAN,
            "stages": ["prescan", "determ", "postscan"],
            "seed": 7,
        },
        headers=HDRS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["input"] == SAMPLE_HUMAN
    assert "output" in body
    assert body["llm_used"] is False
    assert isinstance(body["deterministic_log"], list)
    assert "pre_score" in body and "post_score" in body
    assert body["grammar"] is None
    assert body["elapsed_seconds"] >= 0


def test_transform_rejects_unknown_stage(client):
    r = client.post(
        "/v1/transform",
        json={"text": SAMPLE_HUMAN, "stages": ["prescan", "wat"]},
        headers=HDRS,
    )
    assert r.status_code == 422


def test_transform_rejects_unknown_backend(client):
    r = client.post(
        "/v1/transform",
        json={"text": SAMPLE_HUMAN, "backend": "claude-direct"},
        headers=HDRS,
    )
    assert r.status_code == 422


def test_transform_502_when_llm_unavailable(monkeypatch):
    """When the LLM stage runs but downgrades, return 502 backend_unavailable."""

    def fake_pipeline(text, profile, *, stages, model, seed):
        from sis_caro_humanizer.scoring.risk import ai_risk_score

        pre = ai_risk_score(text)
        return PipelineResult(
            input=text,
            output=text,
            pre_score=pre,
            post_score=pre,
            llm_used=False,
            deterministic_log=[],
            grammar=None,
            elapsed_seconds=0.001,
            notes=["llm unavailable: backend ollama not available"],
        )

    app = create_app(token=TOKEN, pipeline_runner=fake_pipeline)
    cli = TestClient(app)
    r = cli.post(
        "/v1/transform",
        json={"text": SAMPLE_HUMAN, "stages": ["llm", "determ"]},
        headers=HDRS,
    )
    assert r.status_code == 502
    body = r.json()
    assert body["error"] == "backend_unavailable"
    assert "llm" in body["detail"]


def test_transform_no_llm_request_no_502(monkeypatch):
    """If the user did not request the LLM stage, missing backend is fine."""

    def fake_pipeline(text, profile, *, stages, model, seed):
        from sis_caro_humanizer.scoring.risk import ai_risk_score

        pre = ai_risk_score(text)
        return PipelineResult(
            input=text,
            output=text,
            pre_score=pre,
            post_score=pre,
            llm_used=False,
            deterministic_log=[],
            grammar=None,
            elapsed_seconds=0.001,
            notes=[],
        )

    app = create_app(token=TOKEN, pipeline_runner=fake_pipeline)
    cli = TestClient(app)
    r = cli.post(
        "/v1/transform",
        json={"text": SAMPLE_HUMAN, "stages": ["prescan", "determ", "postscan"]},
        headers=HDRS,
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# /v1/suggest — uses fake pipeline so tests are fast and deterministic
# ---------------------------------------------------------------------------


def test_suggest_returns_n_candidates():
    @dataclass
    class _Score:
        score: float = 0.3
        raw_weighted_sum: float = 0.4
        components: list = field(default_factory=list)
        band: str = "low"

    def fake_pipeline(text, profile, *, stages, model, seed):
        return PipelineResult(
            input=text,
            output=f"{text}|seed={seed}",
            pre_score=_Score(0.7, band="high"),  # type: ignore[arg-type]
            post_score=_Score(0.3, band="low"),  # type: ignore[arg-type]
            llm_used=False,
            deterministic_log=[],
            grammar=None,
            elapsed_seconds=0.01,
            notes=[],
        )

    def fake_score(text, profile):
        return _Score(0.81, band="high")  # type: ignore[arg-type]

    app = create_app(token=TOKEN, pipeline_runner=fake_pipeline, score_runner=fake_score)
    cli = TestClient(app)
    r = cli.post(
        "/v1/suggest",
        json={"text": "x", "n": 3},
        headers=HDRS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["input_score"] == pytest.approx(0.81)
    assert len(body["candidates"]) == 3
    seeds = sorted(c["seed"] for c in body["candidates"])
    assert seeds == [1, 2, 3]
    assert all("score" in c and "elapsed_seconds" in c for c in body["candidates"])
    # Distinct seeds threaded through.
    outs = {c["text"] for c in body["candidates"]}
    assert len(outs) == 3


def test_suggest_caps_n_at_3(client):
    r = client.post("/v1/suggest", json={"text": "x", "n": 10}, headers=HDRS)
    assert r.status_code == 422


def test_suggest_rejects_oversize(client):
    big = "x" * 30_001
    r = client.post("/v1/suggest", json={"text": big, "n": 1}, headers=HDRS)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Backend override
# ---------------------------------------------------------------------------


def test_transform_backend_override_passed_through(monkeypatch):
    seen: dict[str, Any] = {}

    def fake_pipeline(text, profile, *, stages, model, seed):
        seen["backend"] = profile.backend
        seen["backend_config"] = dict(profile.backend_config)
        seen["model"] = model
        from sis_caro_humanizer.scoring.risk import ai_risk_score

        pre = ai_risk_score(text)
        return PipelineResult(
            input=text,
            output=text,
            pre_score=pre,
            post_score=pre,
            llm_used=False,
            deterministic_log=[],
            grammar=None,
            elapsed_seconds=0.0,
            notes=[],
        )

    app = create_app(token=TOKEN, pipeline_runner=fake_pipeline)
    cli = TestClient(app)
    r = cli.post(
        "/v1/transform",
        json={
            "text": SAMPLE_HUMAN,
            "stages": ["prescan"],
            "backend": "anthropic",
            "model": "claude-haiku-4-5",
        },
        headers=HDRS,
    )
    assert r.status_code == 200
    assert seen["backend"] == "anthropic"
    assert seen["model"] == "claude-haiku-4-5"
    assert seen["backend_config"]["model"] == "claude-haiku-4-5"
