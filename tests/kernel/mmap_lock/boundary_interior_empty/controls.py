#!/usr/bin/env python3
"""Reuse all exact receipt and two-split corruption checks."""
from pathlib import Path
import runpy
check=runpy.run_path(str(Path(__file__).parents[1]/'boundary_interior_missing/controls.py'))['check']
