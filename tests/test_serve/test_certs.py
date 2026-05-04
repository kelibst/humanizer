"""Self-signed cert generation."""
from __future__ import annotations

from sis_caro_humanizer.serve.certs import ensure_certs, trust_install_hint


def test_ensure_certs_generates_pair(tmp_path, monkeypatch):
    monkeypatch.setattr("sis_caro_humanizer.serve.certs.certs_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "sis_caro_humanizer.serve.certs.cert_path", lambda: tmp_path / "cert.pem"
    )
    monkeypatch.setattr(
        "sis_caro_humanizer.serve.certs.key_path", lambda: tmp_path / "key.pem"
    )
    paths = ensure_certs()
    assert paths.cert.exists()
    assert paths.key.exists()
    assert paths.generated is True
    cert_bytes = paths.cert.read_bytes()
    key_bytes = paths.key.read_bytes()
    assert b"BEGIN CERTIFICATE" in cert_bytes
    assert b"PRIVATE KEY" in key_bytes


def test_ensure_certs_reuses_existing(tmp_path, monkeypatch):
    monkeypatch.setattr("sis_caro_humanizer.serve.certs.certs_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "sis_caro_humanizer.serve.certs.cert_path", lambda: tmp_path / "cert.pem"
    )
    monkeypatch.setattr(
        "sis_caro_humanizer.serve.certs.key_path", lambda: tmp_path / "key.pem"
    )
    first = ensure_certs()
    second = ensure_certs()
    assert second.generated is False
    assert second.cert.read_bytes() == first.cert.read_bytes()
    assert second.key.read_bytes() == first.key.read_bytes()


def test_ensure_certs_rotate_regenerates(tmp_path, monkeypatch):
    monkeypatch.setattr("sis_caro_humanizer.serve.certs.certs_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "sis_caro_humanizer.serve.certs.cert_path", lambda: tmp_path / "cert.pem"
    )
    monkeypatch.setattr(
        "sis_caro_humanizer.serve.certs.key_path", lambda: tmp_path / "key.pem"
    )
    first = ensure_certs()
    first_bytes = first.cert.read_bytes()
    rotated = ensure_certs(regenerate=True)
    assert rotated.generated is True
    assert rotated.cert.read_bytes() != first_bytes


def test_trust_install_hint_mentions_cert(tmp_path):
    cert = tmp_path / "cert.pem"
    cert.write_bytes(b"x")
    hint = trust_install_hint(cert)
    assert str(cert) in hint
