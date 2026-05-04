"""Boot the bridge daemon with the persistent token + TLS cert.

Used by the ``humanize serve`` CLI sub-command. Splits cleanly so tests can
import :func:`build_serve_config` without actually starting uvicorn.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from .app import VERSION, create_app
from .auth import load_or_create_token, token_path
from .certs import CertPaths, ensure_certs, trust_install_hint


@dataclass
class ServeConfig:
    host: str
    port: int
    tls: bool
    token: str
    token_path: Path
    cert_paths: CertPaths | None
    trust_hint: str | None


def build_serve_config(
    *,
    host: str = "127.0.0.1",
    port: int = 9999,
    tls: bool = True,
    rotate_token: bool = False,
    rotate_cert: bool = False,
) -> ServeConfig:
    """Resolve token + (if TLS) certificate paths, generating them as needed."""
    token = load_or_create_token(regenerate=rotate_token)
    cert_paths: CertPaths | None = None
    trust_hint: str | None = None
    if tls:
        cert_paths = ensure_certs(host="localhost", regenerate=rotate_cert)
        trust_hint = trust_install_hint(cert_paths.cert)
    return ServeConfig(
        host=host,
        port=port,
        tls=tls,
        token=token,
        token_path=token_path(),
        cert_paths=cert_paths,
        trust_hint=trust_hint,
    )


def render_startup_banner(cfg: ServeConfig) -> str:
    """Build the multi-line banner printed to stderr at startup."""
    scheme = "https" if cfg.tls else "http"
    lines = [
        f"humanize-bridge v{VERSION}",
        f"  listening on  {scheme}://{cfg.host}:{cfg.port}",
        f"  bearer token  {cfg.token}",
        f"  token file    {cfg.token_path}",
    ]
    if cfg.cert_paths is not None:
        lines.append(f"  cert          {cfg.cert_paths.cert}")
        lines.append(f"  key           {cfg.cert_paths.key}")
        if cfg.cert_paths.generated:
            lines.append("  (cert was just generated; trust it once with the command below)")
        if cfg.trust_hint:
            lines.append("")
            lines.append(f"  trust install: {cfg.trust_hint}")
    else:
        lines.append("  TLS disabled (--no-tls). The Google Docs sidebar will not connect")
        lines.append("  to a non-TLS bridge; use --no-tls only for local debugging.")
    lines.append("")
    lines.append("  Press Ctrl+C to stop.")
    return "\n".join(lines)


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 9999,
    tls: bool = True,
    rotate_token: bool = False,
    rotate_cert: bool = False,
    print_banner: bool = True,
) -> None:
    """Foreground-blocking call: build the app, print the banner, run uvicorn."""
    import uvicorn

    cfg = build_serve_config(
        host=host,
        port=port,
        tls=tls,
        rotate_token=rotate_token,
        rotate_cert=rotate_cert,
    )
    if print_banner:
        sys.stderr.write(render_startup_banner(cfg) + "\n")
        sys.stderr.flush()

    app = create_app(token=cfg.token)

    kwargs: dict = {
        "host": cfg.host,
        "port": cfg.port,
        "log_level": "warning",
        "access_log": False,
    }
    if cfg.tls and cfg.cert_paths is not None:
        kwargs["ssl_certfile"] = str(cfg.cert_paths.cert)
        kwargs["ssl_keyfile"] = str(cfg.cert_paths.key)

    uvicorn.run(app, **kwargs)


__all__ = ["ServeConfig", "build_serve_config", "render_startup_banner", "serve"]
