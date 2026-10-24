#!/usr/bin/env python3
"""Reject false target ownership, teardown, rollback and queued-change evidence."""
from pathlib import Path
import copy
import re
import runpy

common=runpy.run_path(str(Path(__file__).parents[1]/'boundary_interior_missing/controls.py'))['check']


def check(row,log,validate):
    passed=common(row,log,validate);mutations=[]
    if 'KD_MM_BOUNDARY_INTERIOR_PRIVATE ' in log:
        for name,pattern,replacement in (
            ('wrong-target-table',r'target_table_pfn=[0-9a-f]+','target_table_pfn=0'),
            ('wrong-original-target-page',r'target_pfn=[0-9a-f]+','target_pfn=0'),
            ('lost-temporary-reference',r'refs_after=\d+','refs_after=0'),
            ('duplicate-target-release',r'target_put=1','target_put=2')):
            mutations.append((name,row,re.sub(pattern,replacement,log)))
        name,key=('error-destroyed-target','target_preserved') if row['injection'] else ('release-before-tlb','tlb_complete')
        mutations.append((name,row,log.replace(key+'=1',key+'=0')))
    if 'KD_MM_INTERIOR_TARGET rollback ' in log:
        mutations.append(('missing-target-rollback',row,re.sub(r'^.*KD_MM_INTERIOR_TARGET rollback[^\n]*\n?','',log,flags=re.M)))
        mutations.append(('rollback-lost-reference',row,log.replace('refs_held=3','refs_held=2')))
        mutations.append(('rollback-duplicate-release',row,log.replace('target_put=1','target_put=2')))
    if row['mode'] in ('change-busy','change-far-busy'):
        for field in ('pfn','locked','refs'):
            r=copy.deepcopy(row);r['change']['page'][0][field]+=1
            mutations.append(('busy-change-'+field,r,log))
    if row['mode']=='change-near-zero':
        for field in ('zero_pfn','index','after_private'):
            r=copy.deepcopy(row);r['change'][field]+=1;mutations.append(('near-zero-'+field,r,log))
    for name,data,text in mutations:
        try:validate(data,text)
        except (AssertionError,ValueError,KeyError):passed.append(name)
        else:raise AssertionError('accepted corrupted evidence: '+name)
    return passed
