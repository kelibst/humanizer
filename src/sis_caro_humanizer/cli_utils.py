"""Shared helper functions for the humanize CLI."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import typer

from .profile.loader import resolve_profile
from .profile.schema import Profile


def _load_profile_or(default: bool, name: str | None) -> Profile:
    """Resolve a profile, falling back to the bundled default."""
    # Import _console lazily to avoid a circular import (cli.py imports us).
    from .cli import _console

    if name:
        try:
            return resolve_profile(name)
        except FileNotFoundError as exc:
            _console.print(f"[red]profile error:[/red] {exc}")
            raise typer.Exit(code=2) from exc
    return resolve_profile("default_ghanaian")


def _read_input(path: Path) -> str:
    from .cli import _console

    if not path.exists():
        _console.print(f"[red]input not found:[/red] {path}")
        raise typer.Exit(code=2)
    if path.suffix.lower() == ".docx":
        try:
            from .docx_bridge import extract_text

            return extract_text(path)
        except ImportError as exc:
            _console.print(f"[red]docx error:[/red] {exc}")
            raise typer.Exit(code=2) from exc
    return path.read_text(encoding="utf-8")


def _to_jsonable(obj: Any) -> Any:
    """Best-effort dataclass / dict / list conversion for JSON output."""
    if is_dataclass(obj):
        return _to_jsonable(asdict(obj))
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    return obj
