#!/usr/bin/env python3
"""Reject fabricated table absence, near ownership and post-fault access claims."""
import copy
import re
from pathlib import Path
import runpy
shared=runpy.run_path(str(Path(__file__).parents[1]/'boundary_empty/controls.py'))['check']


def check(row,log,validate):
    passed=shared(row,log,validate);mutations=[]
    for name,key in [('target-access-restored','target_rechecks_accessed'),('target-write-restored','target_rechecks_written')]:
        r=copy.deepcopy(row);r[key]+=1;mutations.append((name,r,log))
    r=copy.deepcopy(row);r['walks_before'][-1]['table_pfn'][1]=1
    mutations.append(('near-table-fabricated',r,log))
    if 'KD_MM_BOUNDARY_SHARED_MISSING ' in log:
        mutations.append(('wrong-table-slot-partition',row,re.sub(r'target_table_mask=\d+','target_table_mask=0',log)))
        mutations.append(('wrong-shared-geometry',row,log.replace('shared_geometry=1','shared_geometry=0')))
        mutations.append(('missing-table-claimed-pte',row,log.replace('target_pte_none=0','target_pte_none=1')))
        mutations.append(('missing-table-fabricated-identity',row,log.replace('target_table_pfn=0','target_table_pfn=1')))
    if row['changing']:
        r=copy.deepcopy(row);r['change_more']['before_none']=1
        mutations.append(('transition-not-from-missing-table',r,log))
        r=copy.deepcopy(row);r['change']['index']+=1
        mutations.append(('wrong-target-or-near-fault',r,log))
        if row['changing_zero']:
            r=copy.deepcopy(row);r['change']['zero_pfn']+=1
            mutations.append(('changed-zero-identity',r,log))
        else:
            for name,key,value in [('lost-new-private-reference','refs',1),('wrong-new-page-lock','locked',not row['change']['page'][0]['locked'])]:
                r=copy.deepcopy(row);r['change']['page'][0][key]=value;mutations.append((name,r,log))
        if not row['native'] and row['mode']=='appear-private':
            mutations.append(('changed-private-hold-leak',row,re.sub(r'refs_after=\d+','refs_after=0',log)))
            mutations.append(('changed-private-tlb-incomplete',row,log.replace('tlb_complete=1 shared_geometry','tlb_complete=0 shared_geometry')))
        if not row['native'] and row['mode']=='appear-zero':
            mutations.append(('changed-zero-tlb-incomplete',row,log.replace('zero_tlb_complete=1','zero_tlb_complete=0')))
    for name,r,l in mutations:
        try:validate(r,l)
        except AssertionError:passed.append(name)
        else:raise AssertionError('corrupt evidence accepted: '+name)
    return passed
