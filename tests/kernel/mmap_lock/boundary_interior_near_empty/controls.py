#!/usr/bin/env python3
"""Preserve exact zero-survivor, ownership, refusal and two-split controls."""
from pathlib import Path
import runpy
check=runpy.run_path(str(Path(__file__).parents[1]/'boundary_interior_near_zero/controls.py'))['check']
