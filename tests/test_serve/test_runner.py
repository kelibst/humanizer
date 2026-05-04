"""Tests for the serve config builder + startup banner."""
from __future__ import annotations

from sis_caro_humanizer.serve.runner import build_serve_config, render_startup_banner


def test_build_serve_config_with_tls(tmp_path, monkeypatch):
    fake_certs = tmp_path / "certs"
    fake_serve = tmp_path / "serve"
    monkeypatch.setattr("sis_caro_humanizer.serve.certs.certs_dir", lambda: fake_certs)
    monkeypatch.setattr(
        "sis_caro_humanizer.serve.certs.cert_path", lambda: fake_certs / "cert.pem"
    )
    monkeypatch.setattr(
        "sis_caro_humanizer.serve.certs.key_path", lambda: fake_certs / "key.pem"
    )
    monkeypatch.setattr("sis_caro_humanizer.serve.auth.serve_dir", lambda: fake_serve)
    fake_certs.mkdir(parents=True, exist_ok=True)
    fake_serve.mkdir(parents=True, exist_ok=True)

    cfg = build_serve_config(host="127.0.0.1", port=12345, tls=True)
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 12345
    assert cfg.tls is True
    assert cfg.token
    assert cfg.cert_paths is not None
    assert cfg.cert_paths.cert.exists()
    assert cfg.cert_paths.key.exists()
    assert cfg.trust_hint and str(cfg.cert_paths.cert) in cfg.trust_hint


def test_build_serve_config_no_tls(tmp_path, monkeypatch):
    fake_serve = tmp_path / "serve"
    monkeypatch.setattr("sis_caro_humanizer.serve.auth.serve_dir", lambda: fake_serve)
    fake_serve.mkdir(parents=True, exist_ok=True)

    cfg = build_serve_config(tls=False)
    assert cfg.tls is False
    assert cfg.cert_paths is None
    assert cfg.trust_hint is None


def test_render_startup_banner_includes_token_and_cert(tmp_path, monkeypatch):
    fake_certs = tmp_path / "certs"
    fake_serve = tmp_path / "serve"
    monkeypatch.setattr("sis_caro_humanizer.serve.certs.certs_dir", lambda: fake_certs)
    monkeypatch.setattr(
        "sis_caro_humanizer.serve.certs.cert_path", lambda: fake_certs / "cert.pem"
    )
    monkeypatch.setattr(
        "sis_caro_humanizer.serve.certs.key_path", lambda: fake_certs / "key.pem"
    )
    monkeypatch.setattr("sis_caro_humanizer.serve.auth.serve_dir", lambda: fake_serve)
    fake_certs.mkdir(parents=True, exist_ok=True)
    fake_serve.mkdir(parents=True, exist_ok=True)

    cfg = build_serve_config(port=9999)
    banner = render_startup_banner(cfg)
    assert "humanize-bridge" in banner
    assert cfg.token in banner
    assert "9999" in banner
    assert "https://" in banner
    assert "trust install" in banner.lower()
    assert str(cfg.cert_paths.cert) in banner
