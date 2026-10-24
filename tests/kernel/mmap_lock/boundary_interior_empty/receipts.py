#!/usr/bin/env python3
"""Empty target table plus the unchanged, exact two-split interior proof."""
from pathlib import Path
import runpy
base=runpy.run_path(str(Path(__file__).parents[1]/'boundary_interior_missing/receipts.py'))
compare_native,compare_success=base['compare_native'],base['compare_success']
def validate(row,log):
    return base['validate'](row,log,empty=True)
