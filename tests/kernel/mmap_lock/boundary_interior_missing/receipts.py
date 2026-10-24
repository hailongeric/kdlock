#!/usr/bin/env python3
"""Both interior orientations, actual two-split neighbors and no table walk."""
from pathlib import Path
import re
import runpy
edge=runpy.run_path(str(Path(__file__).parents[1]/'boundary_edge/receipts.py'))
require,IDENT=edge['require'],edge['IDENT']
PAGE,PMD=4096,2<<20


def compare_native(a,b):
    require(a['interior_right']==b['interior_right'] and a['shape']==b['shape'] and a['mode']==b['mode'], 'error geometry/control differs')
    edge['compare_native'](a,b)


def compare_success(a,b):
    require(a['interior_right']==b['interior_right'], 'native boundary orientation differs')
    return dict(edge['compare_success'](a,b),interior_right=a['interior_right'])


def validate(row,log):
    result=edge['validate'](row,log,shared=True,shared_missing=True,interior=True)
    right,mode,native=row['interior_right'],row['mode'],row['native']
    require(right in (0,1), 'one declared boundary orientation required')
    near,far=(2,0) if right else (0,2)
    allowed=('middle-ru','middle-zu','middle-uu') if right else ('middle-ur','middle-uz','middle-uu')
    require(row['shape'] in allowed, 'missing target table cannot have populated near survivor')
    victim=0 if native else 1
    same=6 if right else 3
    for g,(o,w) in enumerate(zip(row['origins'],row['walks_before'])):
        if row['injection'] and not native and g==0:continue
        lo,hi,start,end=(o[k] for k in ('old_start','old_end','start','end'))
        boundary=(hi-1)//PMD*PMD
        require(lo==boundary-(1 if right else 2)*PAGE and start==lo+PAGE and end==lo+2*PAGE,
                'interior cut or boundary orientation differs')
        require(not ((row['masks'][g]|row['zero_masks'][g])&(1<<near)) and row['ptes_before'][g]['none']&same==same and not w['upper_none'],
                'target/near entries must be untouched with upper levels present')
        if mode=='table' and g==victim:
            require(w['leaf']&same==same and w['table_pfn'][1]>0, 'existing empty-table refusal was not constructed')
        else:require(w['pmd_none']&same==same and not w['table_pfn'][1] and not w['table_pfn'][near], 'target table absence not actually observed')
    removed=sum(not o['layouts'][1]['mapped'] for o in row['origins'])
    require(row['target_rechecks_accessed']==row['target_rechecks_written']==removed,
            'later near fault/write restored the removed target or was not rechecked')
    move=row['retention_change'];o=row['origins'][victim]
    if mode=='free-table':
        address=o['old_start']+(-2 if not right else 4)*PAGE
        require(move==dict(before_start=address,before_end=address+PAGE,before_zero=0,table_before=0,table_after=0,before_publication=1),
                'current outer-neighbor prerequisite loss not established')
    else:require(not any(move.values()), 'unexpected retaining-neighbor modification')
    pre=list(re.finditer('KD_MM_INTERIOR preflight '+IDENT+r' old_start=([0-9a-f]+) old_end=([0-9a-f]+) outer_floor=([0-9a-f]+) outer_ceiling=([0-9a-f]+) floor=([0-9a-f]+) ceiling=([0-9a-f]+) required_splits=2 no_table_walk=1',log))
    bounds=list(re.finditer('KD_MM_INTERIOR split_bounds '+IDENT+r' left_start=([0-9a-f]+) left_end=([0-9a-f]+) right_start=([0-9a-f]+) right_end=([0-9a-f]+) splits=2 tables_unchanged=1',log))
    done=list(re.finditer('KD_MM_BOUNDARY_INTERIOR_MISSING (?:done|error) '+IDENT,log))
    require(sorted(p.groups()[:6] for p in pre)==sorted(p.groups() for p in done), 'pre-split retention proof not bound to every remote body/error')
    expected_bounds=[] if row['injection']==1 else [p.groups() for p in done]
    require(sorted(p.groups()[:6] for p in bounds)==sorted(expected_bounds), 'second split bounds missing, duplicated or claimed after first-split failure')
    origins={str(o['tid']):(g,o) for g,o in enumerate(row['origins'])}
    for p in pre:
        r=p.groups();g,o=origins[r[2]];lo,hi,start,end=(o[k] for k in ('old_start','old_end','start','end'))
        floor=row['neighbors'][g][0]['end'];ceiling=row['neighbors'][g][1]['start']
        require(tuple(int(x,16) for x in r[6:])==(lo,hi,floor,ceiling,start,end), 'preflight used stale outer neighbors or edge-only bounds')
        require(floor>lo//PMD*PMD and ceiling<(hi-1)//PMD*PMD+PMD, 'both existing outer-neighbor guards remain mandatory')
        address=start//PMD*PMD
        if address<start:address+=PMD
        cap=end//PMD*PMD
        finish=end-PMD if end-1>cap-1 else end
        require(cap and address>finish-1, 'native free_pgd_range would enter a table')
        d=next(x for x in done if x.groups()==r[:6]);require(p.end()<d.start(), 'retention preflight ran after destructive completion')
        if row['injection']!=1:
            b=next(x for x in bounds if x.groups()[:6]==r[:6])
            require(tuple(int(x,16) for x in b.groups()[6:])==(lo,start,end,hi) and p.end()<b.start()<d.start(),
                    'actual post-split adjacent VMAs do not establish native floor/ceiling')
    require(not re.search(r'KD_MM_BOUNDARY_INTERIOR_(?:EMPTY|ZERO|PRIVATE)',log), 'unsupported interior target class executed')
    return dict(result,remote_interior_missing_removals=result['remote_boundary_removals'],two_split_retention_verified=True,
                interior_right=right,near_survivor_untouched_before_access=True,retained_outer_guards=True,
                existing_table_refused=mode in ('table','appear'),error_after_split=row['injection'])
