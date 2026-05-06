"""Global pytest fixtures for the humanizer test suite.

The v1.4 perplexity feature talks to Ollama (or falls back to DistilGPT2).
Both paths are slow and network-dependent; for the entire test suite we
disable the feature by default. The dedicated perplexity tests
(:mod:`tests.test_perplexity`) override this on a per-test basis with their
own monkeypatched paths, so they continue to exercise both code paths.

v1.5: adds ``@pytest.mark.slow`` marker for benchmark corpus tests. These run
only when ``--slow`` is passed on the command line or ``HUMANIZER_SLOW_TESTS=1``
is set in the environment.
"""
from __future__ import annotations

import os

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--slow",
        action="store_true",
        default=False,
        help="Run @pytest.mark.slow tests (benchmark corpus etc.).",
    )


def pytest_configure(config: pytest.Config) -> None:
    # Disable perplexity in CI / local test runs unless an explicit opt-in
    # is set. Individual perplexity tests reset this in their own fixture.
    os.environ.setdefault("HUMANIZE_DISABLE_PERPLEXITY", "1")
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (run only with --slow or HUMANIZER_SLOW_TESTS=1)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    slow_enabled = config.getoption("--slow", default=False) or bool(
        os.environ.get("HUMANIZER_SLOW_TESTS")
    )
    if slow_enabled:
        return  # run everything
    skip_slow = pytest.mark.skip(reason="pass --slow or set HUMANIZER_SLOW_TESTS=1")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
