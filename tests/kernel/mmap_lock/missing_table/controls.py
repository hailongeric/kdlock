#!/usr/bin/env python3
"""Corrupt actual missing-table evidence without manufacturing pass fixtures."""
import copy
from pathlib import Path
import runpy

shared = runpy.run_path(str(Path(__file__).parents[1] / 'zero_target/controls.py'))['check']


def check(row, log, validate):
    passed = shared(row, log, validate)
    mutations = []
    for name, field in [('upper-level-missing', 'upper_none'), ('leaf-not-missing', 'pmd_none')]:
        r = copy.deepcopy(row); g = 1 if row['injection'] and not row['native'] else 0
        r['walks_before'][g][field] ^= 1
        mutations.append((name, r, log))
    r = copy.deepcopy(row); r['anchors'][0] = r['origins'][0]['old_start'] - 8192
    mutations.append(('anchor-shares-missing-table', r, log))
    r = copy.deepcopy(row); r['walks_after'][0]['parent_pfn'][0] += 1
    mutations.append(('upper-table-replaced', r, log))
    r = copy.deepcopy(row); r['table_bytes_after'] += 4096
    mutations.append(('unexpected-table-allocation', r, log))
    r = copy.deepcopy(row); r['walks_cleanup'][0]['upper_none'] = 0
    mutations.append(('table-cleanup-leak', r, log))
    for name, data, text in mutations:
        try: validate(data, text)
        except AssertionError: passed.append(name)
        else: raise AssertionError('corrupt evidence accepted: '+name)
    return passed
