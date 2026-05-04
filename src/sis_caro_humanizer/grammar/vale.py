"""Vale wrapper.

Shells out to ``vale --output=JSON --no-exit`` against a temp file with the
input text and the bundled style folder. If the ``vale`` binary is not on PATH
we report ``missing`` and contribute no issues.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..config import bundle_dir
from .types import GrammarIssue, ToolStatus

# When installed via wheel, Hatch copies vale_styles/ to
# ``sis_caro_humanizer/_data/vale_styles``. In an editable install we fall back
# to the source-tree copy two levels up from this file's package root. When
# running inside a PyInstaller one-file bundle, ``bundle_dir()`` resolves to
# ``sys._MEIPASS`` and we look for ``vale_styles/`` at the bundle root.
_PKG_ROOT = Path(__file__).resolve().parent.parent
_BUNDLED_DATA = _PKG_ROOT / "_data" / "vale_styles"
_REPO_ROOT_FALLBACK = _PKG_ROOT.parent.parent / "vale_styles"


def _find_styles_dir() -> Path | None:
    candidates = (
        _BUNDLED_DATA,
        bundle_dir() / "vale_styles",
        _REPO_ROOT_FALLBACK,
    )
    for cand in candidates:
        if (cand / ".vale.ini").exists():
            return cand
    return None


def _binary() -> str | None:
    return shutil.which("vale")


def check(text: str) -> tuple[list[GrammarIssue], ToolStatus]:
    if not text.strip():
        return [], "ok"
    binary = _binary()
    if not binary:
        return [], "missing"
    styles_dir = _find_styles_dir()
    if styles_dir is None:
        return [], "missing"

    with tempfile.TemporaryDirectory() as td:
        # Vale picks the style by file extension; .md guarantees our [*.{md,txt}]
        # pattern catches it.
        tmp = Path(td) / "input.md"
        tmp.write_text(text, encoding="utf-8")
        cfg = styles_dir / ".vale.ini"
        try:
            proc = subprocess.run(
                [binary, "--output=JSON", "--no-exit", f"--config={cfg}", str(tmp)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return [], "error"

        stdout = proc.stdout.strip()
        if not stdout:
            return [], "ok"
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return [], "error"

    # Vale JSON shape: {"<filename>": [ {Line, Span, Match, Check, Severity, Message, Action: {Params: [...]} }, ... ]}
    issues: list[GrammarIssue] = []
    line_starts = _line_starts(text)
    for _path, entries in payload.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            line = int(entry.get("Line", 1) or 1)
            span = entry.get("Span") or [0, 0]
            try:
                start_col = int(span[0])
                end_col = int(span[1])
            except (TypeError, ValueError, IndexError):
                start_col = end_col = 0
            offset = line_starts.get(line, 0) + max(0, start_col - 1)
            length = max(0, end_col - start_col + 1) if end_col >= start_col else 0
            check_id = str(entry.get("Check", "") or "")
            message = str(entry.get("Message", "") or "")
            action = entry.get("Action") or {}
            params = action.get("Params") if isinstance(action, dict) else []
            suggestions = [str(p) for p in (params or [])][:5]
            issues.append(
                GrammarIssue(
                    tool="vale",
                    rule_id=check_id,
                    message=message,
                    offset=offset,
                    length=length,
                    suggestions=suggestions,
                )
            )
    return issues, "ok"


def _line_starts(text: str) -> dict[int, int]:
    """Map 1-based line number -> byte offset of that line's start."""
    starts = {1: 0}
    pos = 0
    line = 1
    for ch in text:
        pos += 1
        if ch == "\n":
            line += 1
            starts[line] = pos
    return starts
