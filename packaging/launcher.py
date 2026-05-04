"""PyInstaller entry point.

Executing ``src/sis_caro_humanizer/cli.py`` directly would treat it as a
top-level script and break its relative imports. This shim imports the CLI
through its package path and invokes it.
"""
from sis_caro_humanizer.cli import main


if __name__ == "__main__":
    main()
