# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the humanize CLI.

Build a single-file Linux binary so colleagues without a Python toolchain can
still run the humanizer:

    .venv/bin/pip install pyinstaller
    .venv/bin/pyinstaller packaging/pyinstaller.spec --clean --noconfirm
    # binary lands at dist/humanize

The spec lives under ``packaging/`` but PyInstaller runs it from the project
root, so all relative paths are resolved against the repo root.
"""
from __future__ import annotations

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

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

# ---------------------------------------------------------------------------
# Hidden imports
# ---------------------------------------------------------------------------
# These are imported lazily (inside functions or behind try/except) and so
# PyInstaller's static analysis sometimes misses them. Spell them out.
hiddenimports = [
    "ollama",
    "language_tool_python",
    "proselint",
    "pydantic",
    "yaml",
    "regex",
]


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
    excludes=[],
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
