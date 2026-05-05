# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the humanize CLI.

Build a single-file Linux binary so colleagues without a Python toolchain can
still run the humanizer:

    .venv/bin/pip install pyinstaller
    .venv/bin/pyinstaller packaging/pyinstaller.spec --clean --noconfirm
    # binary lands at dist/humanize

The spec lives under ``packaging/`` but PyInstaller runs it from the project
root, so all relative paths are resolved against the repo root.

v1.2 expanded the surface area: the binary now also ships the Textual TUI
(``humanize`` no-args), the FastAPI ``humanize serve`` HTTPS bridge daemon,
and the four backend adapters (ollama / anthropic / openai / gemini). Each of
those packages has lazy imports / Rust extensions / package data that
PyInstaller's static analysis misses; they are spelled out below.
"""
from __future__ import annotations

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# PyInstaller invokes the spec with ``exec`` from the working directory. The
# project root (which is the cwd when run as instructed) is what we anchor to.
ROOT = Path.cwd()
SRC = ROOT / "src" / "sis_caro_humanizer"

# ---------------------------------------------------------------------------
# Bundled read-only data
# ---------------------------------------------------------------------------
# Each tuple is (source_path_on_disk, destination_inside_bundle).
# Destinations match what the package code expects at runtime:
#   - profile YAML and llm_favored.txt are loaded via ``Path(__file__).parent``
#     inside their respective sub-packages, so they must sit at
#     ``sis_caro_humanizer/<subpkg>/`` inside the bundle.
#   - the vale_styles tree is looked up via ``config.bundle_dir() /
#     "vale_styles"`` which resolves to ``sys._MEIPASS`` at runtime, so the
#     destination is just ``vale_styles``.
datas = [
    (str(SRC / "profile" / "default_ghanaian.yaml"), "sis_caro_humanizer/profile"),
    (str(SRC / "scoring" / "llm_favored.txt"), "sis_caro_humanizer/scoring"),
    (str(ROOT / "vale_styles"), "vale_styles"),
]
# proselint ships its own ``config/default.json``; language_tool_python ships
# JAR resolver helpers. Both are loaded via ``pkg_resources`` / direct file
# reads at runtime, which PyInstaller's static analysis misses.
datas += collect_data_files("proselint")
datas += collect_data_files("language_tool_python")
# Textual ships default CSS, fonts, and template files as package data; without
# this PyInstaller bundles only the .py files and the TUI crashes at launch
# with "Could not load default stylesheet".
datas += collect_data_files("textual")
# Anthropic and OpenAI SDKs ship JSON schemas / model lists as package data
# loaded by ``importlib.resources`` calls that PyInstaller cannot follow
# statically.
datas += collect_data_files("anthropic")
datas += collect_data_files("openai")
datas += collect_data_files("docx")
# NOTE: ``addons/google-docs/`` is intentionally NOT bundled — the Apps Script
# add-in is a separately distributable artefact (see addons/google-docs/README.md
# and the "Install the Google Docs add-in" section of top-level README.md).
# Likewise, runtime-generated files at ``~/.config/humanizer/certs/`` and
# ``~/.config/humanizer/serve/token`` are produced on first ``humanize serve``
# invocation and must not be baked into the binary.

# ---------------------------------------------------------------------------
# Hidden imports
# ---------------------------------------------------------------------------
# These are imported lazily (inside functions or behind try/except) and so
# PyInstaller's static analysis sometimes misses them. Spell them out.
hiddenimports = [
    # Original (v1.0 / v1.1) deps.
    "ollama",
    "language_tool_python",
    "proselint",
    "pydantic",
    "yaml",
    "regex",
    # Textual TUI + its markdown / linkify chain (Agent B v1.2 round 1).
    "textual",
    "markdown_it",
    "linkify_it",
    "mdit_py_plugins",
    "uc_micro",
    # FastAPI bridge daemon stack (Agent A v1.2 round 1).
    "fastapi",
    "starlette",
    "uvicorn",
    "httpx",
    "httptools",
    "h11",
    "websockets",
    # cryptography ships a Rust extension that PyInstaller misses without an
    # explicit hint.
    "cryptography",
    "cryptography.hazmat.bindings._rust",
    # Hosted-LLM SDKs (Agent A v1.2 round 1).
    "anthropic",
    "openai",
    "google.generativeai",
    # python-docx .docx support (Agent B v1.2).
    "docx",
    "lxml",
    "lxml.etree",
]
hiddenimports += collect_submodules("docx")
# Pull in every submodule of our own package so lazy ``importlib`` calls
# (e.g. the stage3 deterministic loader, the backends registry, the TUI
# screen routing) all resolve at runtime.
hiddenimports += collect_submodules("sis_caro_humanizer")


# Entry point: ``packaging/launcher.py`` is a one-line shim around
# ``sis_caro_humanizer.cli.main``. We can't point Analysis at
# ``src/sis_caro_humanizer/cli.py`` directly because PyInstaller would treat it
# as a top-level script and break its package-relative imports.
a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",      # huge GUI/data-science dep, pulled in transitively, unused by humanize
        "PIL",             # imaging — same story
        "Pillow",
        "gi",              # GTK Python bindings — unused, but matplotlib's backend-probe drags it in
        "tkinter",         # also probed by matplotlib
        "_tkinter",
        "PyQt5", "PyQt6", "PySide2", "PySide6",  # GUI toolkits matplotlib probes
        "wx",
        "IPython", "jupyter_client", "notebook",  # often transitive via openai/anthropic, unused
        "pytest",          # dev-only
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="humanize",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
