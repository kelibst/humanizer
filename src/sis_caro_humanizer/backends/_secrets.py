"""Resolve API keys for hosted backends.

Resolution order (per ``BACKEND_CONTRACT.md`` §2):

    explicit ``config["api_key"]`` → env var → ``~/.config/humanizer/secrets.toml``

The secrets file is a flat TOML mapping of ``ENV_VAR_NAME = "value"``::

    ANTHROPIC_API_KEY = "sk-ant-..."
    OPENAI_API_KEY    = "sk-..."
    GEMINI_API_KEY    = "AI..."

It is read once and cached. A missing file is fine; a malformed file is logged
to the runner notes (caller's responsibility) and treated as empty.
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import APP_NAME

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - fallback for older interpreters
    import tomli as tomllib  # type: ignore


def secrets_path() -> Path:
    from platformdirs import user_config_dir

    return Path(user_config_dir(APP_NAME)) / "secrets.toml"


@lru_cache(maxsize=1)
def _load_secrets_file() -> dict[str, str]:
    p = secrets_path()
    if not p.exists():
        return {}
    try:
        with p.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception:
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, (str, int, float))}


def reset_cache() -> None:
    """Clear the cached secrets file (used by tests)."""
    _load_secrets_file.cache_clear()


def resolve_api_key(env_var: str, config: dict[str, Any] | None = None) -> str | None:
    """Return the configured API key for ``env_var`` or ``None``.

    Lookup order:
      1. ``config["api_key"]`` if truthy.
      2. ``os.environ[env_var]`` if truthy.
      3. ``secrets.toml[env_var]`` if present.
    """
    if config:
        explicit = config.get("api_key")
        if explicit:
            return str(explicit)
    env = os.environ.get(env_var)
    if env:
        return env
    file_map = _load_secrets_file()
    return file_map.get(env_var)


__all__ = ["resolve_api_key", "secrets_path", "reset_cache"]
