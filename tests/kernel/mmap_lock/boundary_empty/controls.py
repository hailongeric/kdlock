#!/usr/bin/env python3
"""Corrupt actual empty-boundary receipts; never replace live body evidence."""
import copy
import re
from pathlib import Path
import runpy
shared=runpy.run_path(str(Path(__file__).parents[1]/'boundary_edge/controls.py'))['check']

def check(row,log,validate):
    passed=shared(row,log,validate);mutations=[]
    if 'KD_MM_BOUNDARY_EMPTY ' in log:
        mutations.append(('wrong-target-table-identity',row,re.sub(r'target_table_pfn=[0-9a-f]+','target_table_pfn=0',log)))
        mutations.append(('populated-target-accepted',row,log.replace('target_pte_none=1','target_pte_none=0')))
    if row['mode']=='free-table':
        r=copy.deepcopy(row);r['retention_change']['before_end']+=4096
        mutations.append(('retention-change-unbound',r,log))
    if row['mode']=='change-private':
        r=copy.deepcopy(row);r['change']['page'][0]['pfn']+=1
        mutations.append(('wrong-transition-page-reference',r,log))
    for name,r,l in mutations:
        try:validate(r,l)
        except AssertionError:passed.append(name)
        else:raise AssertionError('corrupt evidence accepted: '+name)
    return passed
