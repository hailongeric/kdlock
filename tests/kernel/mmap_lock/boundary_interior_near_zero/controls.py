#!/usr/bin/env python3
"""Keep existing strict controls and bind the newly supported near survivor."""
import copy
from pathlib import Path
import runpy
base=runpy.run_path(str(Path(__file__).parents[1]/'boundary_interior_missing/controls.py'))['check']
def check(row,log,validate):
    passed=base(row,log,validate)
    victim=0 if row['native'] else 1
    near=2 if row['interior_right'] else 0
    changes=[]
    r=copy.deepcopy(row);r['ptes_before'][victim]['zero'] &= ~(1<<near)
    changes.append(('zero-near-input-unproven',r))
    r=copy.deepcopy(row);r['ptes_after'][victim]['none'] |= 1<<near
    changes.append(('near-survivor-mapping-lost',r))
    if row['mode']=='change-near-private':
        r=copy.deepcopy(row);r['change']['index']=victim*3+1
        changes.append(('near-change-misrouted-to-target',r))
    for name,r in changes:
        try:validate(r,log)
        except AssertionError:passed.append(name)
        else:raise AssertionError('accepted corrupted evidence: '+name)
    return passed
