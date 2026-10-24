#!/usr/bin/env python3
"""Preserve common controls; reject missing private-near identity/retirement."""
import copy
from pathlib import Path
import re
import runpy
common=runpy.run_path(str(Path(__file__).parents[1]/'boundary_interior_missing/controls.py'))['check']
def check(row,log,validate):
    passed=common(row,log,validate);mutations=[]
    r=copy.deepcopy(row);r['near_private_write_checks']+=1;mutations.append(('missing-private-near-write',r,log))
    if 'KD_MM_INTERIOR_NEAR_PRIVATE kept ' in log:
        mutations.append(('missing-private-near-retirement',row,re.sub(r'^.*KD_MM_INTERIOR_NEAR_PRIVATE kept[^\n]*\n?','',log,flags=re.M)))
        mutations.append(('private-near-reference-leak',row,log.replace('refs_after=3 mapcount=1 pte_same=1','refs_after=4 mapcount=1 pte_same=1')))
        mutations.append(('private-near-pte-modified',row,log.replace('mapcount=1 pte_same=1','mapcount=1 pte_same=0')))
    if 'KD_MM_INTERIOR_NEAR_PRIVATE rollback ' in log:
        mutations.append(('missing-private-near-rollback',row,re.sub(r'^.*KD_MM_INTERIOR_NEAR_PRIVATE rollback[^\n]*\n?','',log,flags=re.M)))
    if row['changing']:
        r=copy.deepcopy(row);r['change']['index']=(r['change']['index']+1)%(r['groups']*3);mutations.append(('changed-wrong-slot',r,log))
    for name,data,text in mutations:
        try:validate(data,text)
        except (AssertionError,ValueError,KeyError):passed.append(name)
        else:raise AssertionError('accepted corrupted evidence: '+name)
    return passed
