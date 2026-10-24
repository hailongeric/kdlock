#!/usr/bin/env python3
"""Native zero teardown with exact private-near identity and retirement."""
from pathlib import Path
import runpy
base=runpy.run_path(str(Path(__file__).parents[1]/'boundary_interior_near_private/receipts.py'))
compare_native,compare_success=base['compare_native'],base['compare_success']
def validate(row,log):return base['validate'](row,log,zero=True)
