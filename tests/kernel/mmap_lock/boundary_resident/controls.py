#!/usr/bin/env python3
"""Reject corrupted target identity, temporary references and release ordering."""
import copy
import re
from pathlib import Path
import runpy
shared=runpy.run_path(str(Path(__file__).parents[1]/'boundary_empty/controls.py'))['check']


def check(row,log,validate):
    passed=shared(row,log,validate);mutations=[]
    if 'KD_MM_BOUNDARY_PRIVATE ' in log:
        for name,pattern,replacement in (
            ('wrong-target-table',r'target_table_pfn=[0-9a-f]+','target_table_pfn=0'),
            ('wrong-original-target-page',r'target_pfn=[0-9a-f]+','target_pfn=0'),
            ('lost-temporary-reference',r'refs_after=\d+','refs_after=0'),
            ('duplicate-target-release',r'target_put=1','target_put=2')):
            mutations.append((name,row,re.sub(pattern,replacement,log)))
        if row['injection']:
            mutations.append(('error-destroyed-target',row,log.replace('target_preserved=1','target_preserved=0')))
        else:
            mutations.append(('release-before-tlb',row,log.replace('tlb_complete=1','tlb_complete=0')))
    if row['mode']=='change-busy':
        for name,key,value in [('target-was-not-busy','locked',0),('control-added-a-reference','refs',3)]:
            r=copy.deepcopy(row);r['change']['page'][0][key]=value;mutations.append((name,r,log))
    for name,r,l in mutations:
        try:validate(r,l)
        except AssertionError:passed.append(name)
        else:raise AssertionError('corrupt evidence accepted: '+name)
    return passed
