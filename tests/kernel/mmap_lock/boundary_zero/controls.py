#!/usr/bin/env python3
"""Reject corrupted zero-PTE ownership, table identity and error preservation."""
import copy
import re
from pathlib import Path
import runpy
shared=runpy.run_path(str(Path(__file__).parents[1]/'boundary_empty/controls.py'))['check']

def check(row,log,validate):
    passed=shared(row,log,validate);mutations=[]
    if 'KD_MM_BOUNDARY_ZERO ' in log or 'KD_MM_BOUNDARY_SHARED_ZERO ' in log:
        mutations.append(('wrong-target-table-identity',row,re.sub(r'target_table_pfn=[0-9a-f]+','target_table_pfn=0',log)))
        mutations.append(('missing-shared-zero-identity',row,re.sub(r'zero_pfn=[0-9a-f]+','zero_pfn=0',log)))
        mutations.append(('shared-zero-owned',row,log.replace('zero_owned=0','zero_owned=1')))
        mutations.append(('target-zero-unproven',row,log.replace('target_zero=1','target_zero=0')))
        if row['injection']:
            mutations.append(('zero-target-cleared-on-error',row,log.replace('target_pte_none=0','target_pte_none=1')))
    if row['changing']:
        r=copy.deepcopy(row);r['change']['before_zero']=0
        mutations.append(('transition-was-not-zero',r,log))
    for name,r,l in mutations:
        try:validate(r,l)
        except AssertionError:passed.append(name)
        else:raise AssertionError('corrupt evidence accepted: '+name)
    return passed
