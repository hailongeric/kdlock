#!/usr/bin/env python3
"""Corrupt observed empty-leaf state, table partition and transition ownership."""
import copy
import re
from pathlib import Path
import runpy
shared=runpy.run_path(str(Path(__file__).parents[1]/'boundary_empty/controls.py'))['check']


def check(row,log,validate):
    passed=shared(row,log,validate);mutations=[]
    r=copy.deepcopy(row);r['walks_before'][-1]['table_pfn'][1]=0
    mutations.append(('near-survivor-table-lost',r,log))
    if 'KD_MM_BOUNDARY_SHARED_EMPTY ' in log:
        mutations.append(('wrong-table-slot-partition',row,re.sub(r'target_table_mask=\d+','target_table_mask=0',log)))
        mutations.append(('wrong-shared-geometry',row,log.replace('shared_geometry=1','shared_geometry=0')))
        mutations.append(('empty-target-claimed-zero',row,log.replace('target_zero=0','target_zero=1')))
        mutations.append(('empty-target-owned-zero',row,log.replace('zero_owned=0','zero_owned=1')))
    if row['changing']:
        r=copy.deepcopy(row);r['change_more']['before_none']=0
        mutations.append(('transition-not-from-empty-leaf',r,log))
        if row['mode']=='change-zero':
            r=copy.deepcopy(row);r['change']['zero_pfn']+=1
            mutations.append(('changed-zero-identity',r,log))
            if not row['native']:mutations.append(('changed-zero-tlb-incomplete',row,log.replace('zero_tlb_complete=1','zero_tlb_complete=0')))
        else:
            for name,key,value in [('lost-new-private-reference','refs',1),('wrong-new-page-lock','locked',not row['change']['page'][0]['locked'])]:
                r=copy.deepcopy(row);r['change']['page'][0][key]=value;mutations.append((name,r,log))
            if not row['native'] and row['mode']=='change-private':
                mutations.append(('changed-private-hold-leak',row,re.sub(r'refs_after=\d+','refs_after=0',log)))
                mutations.append(('changed-private-tlb-incomplete',row,log.replace('tlb_complete=1 shared_geometry','tlb_complete=0 shared_geometry')))
    for name,r,l in mutations:
        try:validate(r,l)
        except AssertionError:passed.append(name)
        else:raise AssertionError('corrupt evidence accepted: '+name)
    return passed
