#!/usr/bin/env python3
"""Reuse strict zero teardown, survivor-hold and queued-state corruption checks."""
from pathlib import Path
import runpy
check=runpy.run_path(str(Path(__file__).parents[1]/'boundary_interior_near_private/controls.py'))['check']
