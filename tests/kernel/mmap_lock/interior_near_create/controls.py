#!/usr/bin/env python3
"""Preserve earlier corruption controls and reject wrong creation/hold evidence."""
from pathlib import Path
import copy
import re
import runpy
common=runpy.run_path(str(Path(__file__).parents[1]/'boundary_interior_near_private/controls.py'))['check']


def check(row,log,validate):
    passed=common(row,log,validate);mutations=[]
    for field in ('from_zero','outcome','index'):
        r=copy.deepcopy(row);r['near_create'][field]+=1;mutations.append(('near-create-'+field,r,log))
    for field in ('before_none','table_after','anon_after'):
        r=copy.deepcopy(row);r['change_more'][field]+=1;mutations.append(('near-create-'+field,r,log))
    for field in ('pfn','refs','maps','locked'):
        r=copy.deepcopy(row);r['change']['page'][0][field]+=1;mutations.append(('near-create-page-'+field,r,log))
    mutations.append(('missing-native-creation',row,re.sub(r'^.*KD_MM_TEST near_create[^\n]*\n?','',log,flags=re.M)))
    for name,data,text in mutations:
        try:validate(data,text)
        except (AssertionError,ValueError,KeyError):passed.append(name)
        else:raise AssertionError('accepted corrupted evidence: '+name)
    return passed
