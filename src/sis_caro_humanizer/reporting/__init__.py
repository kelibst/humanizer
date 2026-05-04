"""Rich-based reporting helpers for the CLI. Library code does not import
from this package - it is strictly the presentation layer."""
from .diff import render_diff
from .report import render_check, render_grammar, render_transform

__all__ = ["render_check", "render_grammar", "render_transform", "render_diff"]
