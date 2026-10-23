#!/usr/bin/env python3
"""Require empty-leaf input and real absent-target body receipts."""
from pathlib import Path
import runpy

common = runpy.run_path(str(Path(__file__).parents[1] / 'zero_target/receipts.py'))
SHAPES = {name: (target, mask, zero & ~(1 << target))
          for name, (target, mask, zero) in common['SHAPES'].items()}
compare_native = common['compare_native']
compare_success = common['compare_success']


def validate(row, log):
    return common['validate'](row, log, absent=True)
