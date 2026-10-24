#!/usr/bin/env python3
"""Reuse exact ownership, table-lifetime and two-split corruption controls."""
from pathlib import Path
import runpy
check=runpy.run_path(str(Path(__file__).parents[1]/'boundary_interior_missing/controls.py'))['check']
