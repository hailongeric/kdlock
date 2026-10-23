#!/usr/bin/env python3
"""Reject corrupted geometry/retention evidence from the actual boundary run."""
import copy
import re
from pathlib import Path
import runpy
shared=runpy.run_path(str(Path(__file__).parents[1]/'zero_target/controls.py'))['check']


def check(row,log,validate):
    passed=shared(row,log,validate);mutations=[]
    for name,key,delta in [('wrong-upper-level','upper_none',1),('wrong-missing-leaf','pmd_none',1)]:
        r=copy.deepcopy(row);r['walks_before'][-1][key]^=delta;mutations.append((name,r,log))
    r=copy.deepcopy(row);r['origins'][-1]['old_end']+=4096;mutations.append(('widened-vma',r,log))
    r=copy.deepcopy(row);r['neighbors'][-1][0]['end']+=4096;mutations.append(('neighbor-moved',r,log))
    r=copy.deepcopy(row);r['walks_after'][-1]['parent_pfn'][0]+=1;mutations.append(('parent-replaced',r,log))
    r=copy.deepcopy(row);r['table_bytes_after']+=4096;mutations.append(('table-leak-or-extra-allocation',r,log))
    r=copy.deepcopy(row);r['walks_cleanup'][-1]['upper_none']=0;mutations.append(('cleanup-table-leak',r,log))
    r=copy.deepcopy(row);r['interval_cleanup_calls']-=1;mutations.append(('cleanup-entry-routing',r,log))
    if re.search(r'KD_MM_BOUNDARY(?:_EMPTY|_ZERO|_PRIVATE|_SHARED_PRIVATE|_SHARED_ZERO|_SHARED_EMPTY)? (?:done|error) ',log):
        mutations.append(('wrong-native-retention-bound',row,re.sub(r' floor=[0-9a-f]+',' floor=0',log)))
        mutations.append(('survivor-table-ownership',row,log.replace('target_owned=1','target_owned=0') if row.get('boundary_private_test',0) else log.replace('target_owned=0','target_owned=1')))
    for name,data,text in mutations:
        try:validate(data,text)
        except AssertionError:passed.append(name)
        else:raise AssertionError('corrupt evidence accepted: '+name)
    return passed
