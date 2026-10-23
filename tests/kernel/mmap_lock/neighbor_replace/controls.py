#!/usr/bin/env python3
"""Reject damaged real receipts; preserve all shared-path negative controls."""
from pathlib import Path
import copy
import re
import runpy
common=runpy.run_path(str(Path(__file__).parents[1]/'zero_target/controls.py'))


def check(row,log,validate):
    passed=common['check'](row,log,validate)
    mutations=[]
    for key,value in [('queued',0),('close_owner',0),('old_vma',row['neighbor_body']['new_vma']),('maps_closed',row['neighbor_body']['maps_closed']+1),('tables_closed',row['neighbor_body']['tables_closed']+4096),('reader_blocked',0),('close_pending',row['neighbor_body']['close_pending']+1)]:
        broken=copy.deepcopy(row);broken['neighbor_body'][key]=value
        mutations.append(('native-gate-'+key,broken,log))
    for key,field in [('neighbor_body','faults'),('neighbor_clean','page_refs'),('neighbor_clean','vmas')]:
        broken=copy.deepcopy(row);broken[key][field]+=1;mutations.append((key+'-'+field,broken,log))
    broken=copy.deepcopy(row);broken['neighbor_old_inaccessible']=0;mutations.append(('old-neighbor-accessible',broken,log))
    broken=copy.deepcopy(row);broken['neighbor_rechecks_accessed']+=1;mutations.append(('restored-target',broken,log))
    for tag in ('queued','retired'):
        altered=re.sub(r'^.*KD_MM_NEIGHBOR '+tag+r'[^\n]*\n?','',log,flags=re.M)
        mutations.append(('missing-native-'+tag,row,altered))
    for name,broken,altered in mutations:
        try:validate(broken,altered)
        except (AssertionError,ValueError,KeyError):passed.append(name)
        else:raise AssertionError('accepted corrupted evidence: '+name)
    return passed
