"""Token persistence and bearer-header parsing."""
from __future__ import annotations

import os

from sis_caro_humanizer.serve.auth import (
    constant_time_compare,
    extract_bearer,
    load_or_create_token,
    token_path,
)


def test_load_or_create_token_persists(tmp_path, monkeypatch):
    fake_dir = tmp_path / "humanizer" / "serve"
    monkeypatch.setattr(
        "sis_caro_humanizer.serve.auth.serve_dir", lambda: fake_dir or fake_dir.mkdir(parents=True)
    )
    fake_dir.mkdir(parents=True, exist_ok=True)
    t1 = load_or_create_token()
    assert t1
    t2 = load_or_create_token()
    assert t1 == t2  # second call returns persisted token


def test_load_or_create_token_rotate(tmp_path, monkeypatch):
    fake_dir = tmp_path / "humanizer" / "serve"
    fake_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("sis_caro_humanizer.serve.auth.serve_dir", lambda: fake_dir)
    t1 = load_or_create_token()
    t2 = load_or_create_token(regenerate=True)
    assert t1 != t2


def test_token_file_permissions(tmp_path, monkeypatch):
    fake_dir = tmp_path / "humanizer" / "serve"
    fake_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("sis_caro_humanizer.serve.auth.serve_dir", lambda: fake_dir)
    load_or_create_token()
    p = fake_dir / "token"
    assert p.exists()
    if hasattr(os, "stat"):
        mode = p.stat().st_mode & 0o777
        # On posix the file should be 0o600; on systems where chmod silently
        # noops we just check it is at least readable.
        if os.name == "posix":
            assert mode == 0o600


def test_extract_bearer_normal():
    assert extract_bearer("Bearer abc") == "abc"
    assert extract_bearer("bearer abc") == "abc"


def test_extract_bearer_handles_garbage():
    assert extract_bearer(None) is None
    assert extract_bearer("") is None
    assert extract_bearer("Token abc") is None
    assert extract_bearer("Bearer") is None
    assert extract_bearer("Bearer ") is None


def test_constant_time_compare_correctness():
    assert constant_time_compare("abc", "abc") is True
    assert constant_time_compare("abc", "abd") is False
