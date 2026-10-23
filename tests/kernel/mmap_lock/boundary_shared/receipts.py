#!/usr/bin/env python3
"""Exact split-table geometry and queued near-survivor read-fault evidence."""
from pathlib import Path
import re
import runpy

resident=runpy.run_path(str(Path(__file__).parents[1]/'boundary_resident/receipts.py'))
require,IDENT=resident['require'],resident['IDENT']
compare_native,compare_success=resident['compare_native'],resident['compare_success']


def validate(row,log):
    result=resident['validate'](row,log,shared=True)
    native,target=row['native'],row['slice'];victim=0 if native else 1
    for g,o in enumerate(row['origins']):
        if row['injection'] and not native and g==0:continue
        lo=o['old_start'];w=row['walks_before'][g]
        boundary=(lo+12287)//(2<<20)*(2<<20)
        require(lo==boundary-(4096 if target else 8192) and w['table_pfn'][1]==w['table_pfn'][target]>0,
                'near survivor does not share the original target table')
        other=0 if target else 2
        require(not w['table_pfn'][other] or w['table_pfn'][other]!=w['table_pfn'][target], 'far survivor table aliases target')
    pattern=r'KD_MM_TEST absent_change mm=([0-9a-f]+) index=(\d+) actor=(\d+) pending=(\d+) readers=(\d+) admission=(-?\d+) mode=1 before_none=1 after_zero=1 after_private=0 table_before=([0-9a-f]+) table_after=([0-9a-f]+) anon_before=([0-9a-f]+) anon_after=([0-9a-f]+) zero_pfn=([0-9a-f]+) private_pfn=0 result=0'
    transitions=list(re.finditer(pattern,log));changed=row['mode']=='change-near-zero'
    require(len(transitions)==changed, 'near-survivor transition missing/duplicate')
    if changed:
        o=row['origins'][victim];c,m=row['change'],row['change_more'];r=transitions[0].groups()
        table=row['walks_before'][victim]['table_pfn'][target]
        require(row['changing_zero'] and all(mask==(1<<target) for mask in row['masks']) and not any(row['zero_masks']) and
                c['index']==victim*3+1 and c['done']==1 and c['result']==c['before_zero']==c['after_private']==0 and
                c['zero_pfn']>0 and not c['page'] and c['actor']>0 and c['pending']==(0 if native else 3) and
                c['readers']==(1 if native else 2) and (native or c['admission']==-1), 'queued survivor change owns a page or ran at the wrong point')
        require(m==dict(mode=1,before_none=1,after_zero=1,table_before=table,table_after=table,
                       anon_before=o['original_anon'],anon_after=o['original_anon']), 'queued read changed table or ancestry')
        require(int(r[0],16)==row['mm'] and tuple(map(int,r[1:6]))==(c['index'],c['actor'],c['pending'],c['readers'],c['admission']) and
                tuple(int(x,16) for x in r[6:])==(table,table,o['original_anon'],o['original_anon'],c['zero_pfn']), 'read-fault receipt not bound to original table and mm')
        require(row['ptes_before'][victim]['none']&2 and row['ptes_after'][victim]['zero']&2, 'shared-table zero survivor not preserved')
        require(c['actor']==o['tid'] if native else all(c['actor']!=x['tid'] for x in row['origins']), 'wrong local reader')
        if not native:
            body=next((match for match in re.finditer('KD_MM_BOUNDARY_SHARED_PRIVATE done '+IDENT,log) if match.group(3)==str(o['tid'])),None)
            require(body and transitions[0].end()<body.start(), 'body did not revalidate after the real survivor read fault')
    result['controlled_shared_survivor_zero']=changed
    result['remote_shared_removals']=result['remote_private_boundary_removals']
    return result
