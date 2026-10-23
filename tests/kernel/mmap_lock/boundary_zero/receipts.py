#!/usr/bin/env python3
"""Boundary zero targets require their own table-retention and body receipts."""
from pathlib import Path
import runpy
edge=runpy.run_path(str(Path(__file__).parents[1]/'boundary_edge/receipts.py'))
compare_native,compare_success=edge['compare_native'],edge['compare_success']

def validate(row,log):
    return edge['validate'](row,log,zero=True)
