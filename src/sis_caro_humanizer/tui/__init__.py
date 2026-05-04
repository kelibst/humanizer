"""Textual TUI for the humanizer (v1.2 Track B).

Public entry point: :class:`HumanizerApp` (:mod:`sis_caro_humanizer.tui.app`).

The TUI is a *wrapper* around the existing pipeline; all heavy lifting still
goes through :func:`sis_caro_humanizer.pipeline.runner.run_pipeline`. The
runner_bridge module shuttles work onto a worker thread and forwards
``on_event`` callbacks to Textual messages.
"""
from __future__ import annotations

from .app import HumanizerApp

__all__ = ["HumanizerApp"]
