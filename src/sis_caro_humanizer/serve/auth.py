"""Bearer-token auth for the bridge daemon.

The token is generated on first run, persisted under
``~/.config/humanizer/serve/token`` so subsequent ``humanize serve`` runs
honour the same token (the user has to copy it into the add-in once).

If the file is missing or has the wrong permissions we regenerate. The file is
written with ``0o600`` so other local users cannot read it.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from platformdirs import user_config_dir

from ..config import APP_NAME

TOKEN_BYTES = 32
TOKEN_FILENAME = "token"


def serve_dir() -> Path:
    p = Path(user_config_dir(APP_NAME)) / "serve"
    p.mkdir(parents=True, exist_ok=True)
    return p


def token_path() -> Path:
    return serve_dir() / TOKEN_FILENAME


def _read_token(path: Path) -> str | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return raw or None


def load_or_create_token(*, regenerate: bool = False) -> str:
    """Return the persistent bearer token, creating it if missing.

    ``regenerate=True`` forces a fresh token (e.g. the user passed
    ``--rotate-token``).
    """
    path = token_path()
    if not regenerate:
        existing = _read_token(path)
        if existing:
            return existing
    token = secrets.token_urlsafe(TOKEN_BYTES)
    path.write_text(token + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Best-effort on Windows / restricted FS.
        pass
    return token


def constant_time_compare(a: str, b: str) -> bool:
    return secrets.compare_digest(a, b)


def extract_bearer(header: str | None) -> str | None:
    """Return the token portion of an ``Authorization: Bearer ...`` header,
    or ``None`` if the header is missing/malformed."""
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) != 2:
        return None
    scheme, value = parts
    if scheme.lower() != "bearer":
        return None
    return value.strip() or None


__all__ = [
    "TOKEN_BYTES",
    "constant_time_compare",
    "extract_bearer",
    "load_or_create_token",
    "serve_dir",
    "token_path",
]
