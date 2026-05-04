from __future__ import annotations

import sys
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

APP_NAME = "humanizer"


def profiles_dir() -> Path:
    p = Path(user_config_dir(APP_NAME)) / "profiles"
    p.mkdir(parents=True, exist_ok=True)
    return p


def data_dir() -> Path:
    p = Path(user_data_dir(APP_NAME))
    p.mkdir(parents=True, exist_ok=True)
    return p


def profile_path(name: str) -> Path:
    return profiles_dir() / f"{name}.yaml"


def bundle_dir() -> Path:
    """Return the root directory for bundled read-only data.

    When running from a PyInstaller one-file binary, ``sys._MEIPASS`` points
    at the temporary extraction directory and we expect data to live at
    ``<_MEIPASS>/sis_caro_humanizer/...`` and ``<_MEIPASS>/vale_styles/...``.

    When running from a source checkout or an installed wheel, the package
    directory is the natural anchor; the repo root sits two levels above it.
    Callers that need package-relative paths should still use ``Path(__file__).
    parent``; ``bundle_dir()`` is for things that live at the *bundle* root
    (currently just the ``vale_styles/`` tree).
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    # repo root from src/sis_caro_humanizer/config.py
    return Path(__file__).resolve().parent.parent.parent


DEFAULT_MODEL = "gemma3:4b"
LLM_FAVORED_BUILTIN = (
    Path(__file__).parent / "scoring" / "llm_favored.txt"
)
