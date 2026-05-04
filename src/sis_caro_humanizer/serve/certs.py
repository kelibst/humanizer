"""Self-signed TLS certificate management for the bridge daemon.

The Google Docs sidebar runs at ``https://docs.google.com``; mixed-content
rules forbid it from talking to a non-TLS local daemon. A self-signed cert is
acceptable as long as the user trusts it once at the OS level — we print a
one-liner at startup explaining how.

Certificates live under ``~/.config/humanizer/certs/{cert.pem, key.pem}`` and
are regenerated on demand (``--rotate-cert``) or automatically when expired.
"""
from __future__ import annotations

import datetime
import platform
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_dir

from ..config import APP_NAME

CERT_FILENAME = "cert.pem"
KEY_FILENAME = "key.pem"
DEFAULT_VALID_DAYS = 365


def certs_dir() -> Path:
    p = Path(user_config_dir(APP_NAME)) / "certs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def cert_path() -> Path:
    return certs_dir() / CERT_FILENAME


def key_path() -> Path:
    return certs_dir() / KEY_FILENAME


@dataclass
class CertPaths:
    cert: Path
    key: Path
    generated: bool   # True if we generated a new cert this call


def _generate_self_signed(host: str, days: int) -> tuple[bytes, bytes]:
    """Return (cert_pem, key_pem) for a new self-signed cert valid for ``days``.

    ``host`` is included as both the CN and a SubjectAlternativeName so the
    sidebar's ``https://localhost:9999`` URL validates without warnings (after
    the user trusts the cert).
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, host),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "humanizer-local-bridge"),
        ]
    )
    san_entries = [x509.DNSName(host)]
    # Localhost gets both DNS and IP entries so https://127.0.0.1 also works.
    if host in ("localhost", "127.0.0.1"):
        san_entries = [x509.DNSName("localhost")]
        try:
            import ipaddress

            san_entries.append(x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")))
            san_entries.append(x509.IPAddress(ipaddress.IPv6Address("::1")))
        except Exception:
            pass

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        .sign(private_key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return cert_pem, key_pem


def _is_expired(cert_file: Path) -> bool:
    try:
        from cryptography import x509
    except ImportError:  # pragma: no cover - dep is in pyproject
        return False
    try:
        data = cert_file.read_bytes()
    except OSError:
        return True
    try:
        cert = x509.load_pem_x509_certificate(data)
    except Exception:
        return True
    not_after = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after
    if not_after.tzinfo is None:
        not_after = not_after.replace(tzinfo=datetime.timezone.utc)
    return datetime.datetime.now(datetime.timezone.utc) >= not_after


def ensure_certs(
    *,
    host: str = "localhost",
    valid_days: int = DEFAULT_VALID_DAYS,
    regenerate: bool = False,
) -> CertPaths:
    """Make sure cert+key exist and are unexpired; generate if not.

    ``regenerate=True`` forces a fresh pair regardless of state.
    """
    c = cert_path()
    k = key_path()
    if not regenerate and c.exists() and k.exists() and not _is_expired(c):
        return CertPaths(cert=c, key=k, generated=False)
    cert_pem, key_pem = _generate_self_signed(host, valid_days)
    c.write_bytes(cert_pem)
    k.write_bytes(key_pem)
    try:
        import os

        os.chmod(k, 0o600)
    except OSError:  # pragma: no cover - best effort
        pass
    return CertPaths(cert=c, key=k, generated=True)


def trust_install_hint(cert: Path) -> str:
    """Return a one-line OS-specific instruction for trusting the cert.

    Printed at startup. We intentionally avoid running anything ourselves —
    trust installs need root or keychain prompts.
    """
    system = platform.system()
    if system == "Darwin":
        return (
            f"sudo security add-trusted-cert -d -r trustRoot "
            f"-k /Library/Keychains/System.keychain {cert}"
        )
    if system == "Linux":
        return (
            f"sudo cp {cert} /usr/local/share/ca-certificates/humanizer-bridge.crt "
            f"&& sudo update-ca-certificates"
        )
    if system == "Windows":  # pragma: no cover - documented only
        return f'certutil -addstore -f "ROOT" "{cert}"'
    return f"# Trust this cert in your OS keychain: {cert}"


__all__ = [
    "CertPaths",
    "cert_path",
    "certs_dir",
    "ensure_certs",
    "key_path",
    "trust_install_hint",
]
