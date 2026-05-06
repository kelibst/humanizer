"""Global pytest fixtures for the humanizer test suite.

The v1.4 perplexity feature talks to Ollama (or falls back to DistilGPT2).
Both paths are slow and network-dependent; for the entire test suite we
disable the feature by default. The dedicated perplexity tests
(:mod:`tests.test_perplexity`) override this on a per-test basis with their
own monkeypatched paths, so they continue to exercise both code paths.
"""
from __future__ import annotations

import os


def pytest_configure(config):  # noqa: D401 - hook
    # Disable perplexity in CI / local test runs unless an explicit opt-in
    # is set. Individual perplexity tests reset this in their own fixture.
    os.environ.setdefault("HUMANIZE_DISABLE_PERPLEXITY", "1")
