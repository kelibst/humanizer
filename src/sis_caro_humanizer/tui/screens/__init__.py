"""Screen classes for the humanizer TUI.

Each screen corresponds to one tab in the top bar (P/C/T/G/S) plus a
landing/home screen on launch. See ``plan/TUI_LAYOUT.md`` for the full spec.
"""
from __future__ import annotations

from .check import CheckScreen
from .grammar import GrammarScreen
from .home import HomeScreen
from .profiles import ProfilesScreen
from .settings import SettingsScreen
from .transform import TransformScreen

__all__ = [
    "CheckScreen",
    "GrammarScreen",
    "HomeScreen",
    "ProfilesScreen",
    "SettingsScreen",
    "TransformScreen",
]
