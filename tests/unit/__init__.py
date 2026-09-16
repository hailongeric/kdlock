"""Shared import setup for grouped unit drivers and their reusable fixtures."""

import sys
from pathlib import Path


def configure_paths():
    # Drivers share extracted production-code fixtures across groups. Keep
    # their existing module names available through one explicit entry point.
    unit = Path(__file__).resolve().parent
    paths = [unit.parent, unit.parent / "protocols", unit.parent / "tools"]
    paths.extend(unit / group for group in (
        "admission", "codegen", "execution", "infrastructure", "mutex", "spin",
    ))
    for path in reversed(paths):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
