"""Stage 4: pipeline-facing re-export of :func:`grammar.runner.run_grammar`."""
from __future__ import annotations

from ..grammar.runner import run_grammar

__all__ = ["run_grammar"]
