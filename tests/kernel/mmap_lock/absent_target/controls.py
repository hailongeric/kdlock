#!/usr/bin/env python3
"""Use the shared negative controls on actual absent-target evidence."""
from pathlib import Path
import runpy

check = runpy.run_path(str(Path(__file__).parents[1] / 'zero_target/controls.py'))['check']
