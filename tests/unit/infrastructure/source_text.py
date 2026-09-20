"""Read one C translation unit for extraction fixtures, expanding private .inc files.

This is source inspection, not a C preprocessor: normal headers and #if branches
stay literal so the existing production-body fixtures retain their own stubs.
Only explicitly quoted .inc files are expanded, relative to the including file.
"""
import re
from pathlib import Path


def read_source(path, active=()):
    """Preserve declaration order and reject include cycles or missing fragments."""
    path = Path(path).resolve()
    if path in active:
        raise ValueError(f"recursive implementation include: {path}")
    source = path.read_text()
    return re.sub(
        r'^#include "([^"\n]+\.inc)"\s*$',
        lambda match: read_source(path.parent / match[1], (*active, path)),
        source, flags=re.MULTILINE,
    )


ROOT = Path(__file__).resolve().parents[3]


def without_includes(source):
    """Leave preprocessing branches intact for production-body fixtures."""
    return re.sub(r'^#include [<"].*$', "", source, flags=re.MULTILINE)
