#!/usr/bin/env python3
"""Negative controls bind both retained tables and the real queued read fault."""
import copy
import re
from pathlib import Path
import runpy
shared=runpy.run_path(str(Path(__file__).parents[1]/'boundary_resident/controls.py'))['check']


def check(row,log,validate):
    passed=shared(row,log,validate);mutations=[]
    r=copy.deepcopy(row);r['walks_before'][-1]['table_pfn'][1]=0
    mutations.append(('lost-shared-survivor-table',r,log))
    if 'KD_MM_BOUNDARY_SHARED_PRIVATE ' in log:
        mutations.append(('wrong-table-slot-partition',row,re.sub(r'target_table_mask=\d+','target_table_mask=0',log)))
        mutations.append(('old-geometry-receipt',row,log.replace('shared_geometry=1','shared_geometry=0')))
    if row['mode']=='change-near-zero':
        r=copy.deepcopy(row);r['change']['index']-=1
        mutations.append(('fault-touched-target-instead',r,log))
        r=copy.deepcopy(row);r['ptes_after'][0 if row['native'] else 1]['zero']&=~2
        mutations.append(('queued-zero-survivor-lost',r,log))
    for name,r,l in mutations:
        try:validate(r,l)
        except AssertionError:passed.append(name)
        else:raise AssertionError('corrupt evidence accepted: '+name)
    return passed
