"""HTTPS bridge daemon for the Google Docs add-in (and future Word/Pages plugins).

Public surface used by the CLI:

* :func:`runner.serve` — foreground-blocking entry point.
* :func:`runner.build_serve_config` — resolve token + cert without booting.
* :func:`app.create_app` — FastAPI app factory (used by tests).
"""
from .app import VERSION, create_app
from .runner import ServeConfig, build_serve_config, render_startup_banner, serve

__all__ = [
    "VERSION",
    "ServeConfig",
    "build_serve_config",
    "create_app",
    "render_startup_banner",
    "serve",
]
