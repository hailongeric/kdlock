#!/usr/bin/env python3
"""Retain common controls and reject missing/false two-split proof receipts."""
from pathlib import Path
import copy
import re
import runpy
common=runpy.run_path(str(Path(__file__).parents[1]/'zero_target/controls.py'))


def check(row,log,validate):
    passed=common['check'](row,log,validate);mutations=[]
    changed=copy.deepcopy(row);changed['interior_right']^=1;mutations.append(('wrong-boundary-orientation',changed,log))
    changed=copy.deepcopy(row);changed['target_rechecks_written']+=1;mutations.append(('restored-interior-target',changed,log))
    if 'KD_MM_INTERIOR preflight ' in log:
        mutations.append(('missing-two-split-preflight',row,re.sub(r'^.*KD_MM_INTERIOR preflight[^\n]*\n?','',log,flags=re.M)))
        mutations.append(('stale-outer-neighbor',row,re.sub(r'outer_floor=[0-9a-f]+','outer_floor=0',log)))
        mutations.append(('wrong-native-ceiling',row,re.sub(r' ceiling=[0-9a-f]+',' ceiling=0',log)))
    if 'KD_MM_INTERIOR split_bounds ' in log:
        mutations.append(('missing-second-split-bounds',row,re.sub(r'^.*KD_MM_INTERIOR split_bounds[^\n]*\n?','',log,flags=re.M)))
        mutations.append(('lost-right-survivor',row,re.sub(r'right_start=[0-9a-f]+','right_start=0',log)))
    for name,broken,altered in mutations:
        try:validate(broken,altered)
        except (AssertionError,ValueError,KeyError):passed.append(name)
        else:raise AssertionError('accepted corrupted evidence: '+name)
    return passed
