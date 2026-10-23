#!/usr/bin/env python3
"""Shared-zero boundary completion and controlled transition to an owned page."""
from pathlib import Path
import re
import runpy
edge=runpy.run_path(str(Path(__file__).parents[1]/'boundary_edge/receipts.py'))
require,IDENT=edge['require'],edge['IDENT']
compare_native,compare_success=edge['compare_native'],edge['compare_success']


def validate(row,log):
    result=edge['validate'](row,log,zero=True,shared=True)
    mode,native,target=row['mode'],row['native'],row['slice']
    changed=mode in ('change-private','change-private-busy');busy=mode=='change-private-busy'
    pattern=(r'KD_MM_TEST shared_zero_change mm=([0-9a-f]+) index=(\d+) actor=(\d+) pending=(\d+) readers=(\d+) admission=(-?\d+) mode=(\d+)'
             r' before_zero=1 after_private=1 table_before=([0-9a-f]+) table_after=([0-9a-f]+) anon_before=([0-9a-f]+) anon_after=([0-9a-f]+)'
             r' zero_pfn=([0-9a-f]+) private_pfn=([0-9a-f]+) refs=(\d+) mapcount=(\d+) locked=(\d+) result=0')
    transitions=list(re.finditer(pattern,log))
    require(len(transitions)==changed, 'controlled zero/private transition missing or duplicate')
    if changed:
        g=0 if native else 1;o=row['origins'][g];c,m=row['change'],row['change_more'];r=transitions[0].groups()
        require(c['done']==c['before_zero']==c['after_private']==1 and c['result']==0 and len(c['page'])==1 and
                c['index']==g*3+target and c['pending']==(0 if native else 2 if busy else 3) and
                c['readers']==(1 if native else 2) and (native or c['admission']==-1), 'transition not before locked execution')
        p=c['page'][0];table=row['walks_before'][g]['table_pfn'][target]
        require(not any(row['masks']) and all(z==(1<<target) for z in row['zero_masks']) and
                m['mode']==(12 if busy else 11) and m['before_none']==m['after_zero']==m['anon_before']==0 and
                m['table_before']==m['table_after']==table>0 and m['anon_after']>0,
                'unexpected initial state or changed table identity')
        require(p['address']==o['start'] and p['pfn']>0 and p['pfn']!=c['zero_pfn']>0 and p['maps']==1 and
                p['refs']==2 and p['hash']>0 and p['charged_same'] and p['locked']==busy, 'new private reference/lock is not exact')
        require(int(r[0],16)==row['mm'] and tuple(map(int,r[1:7]))==
                (c['index'],c['actor'],c['pending'],c['readers'],c['admission'],m['mode']) and
                tuple(int(v,16) for v in r[7:13])==(table,table,0,m['anon_after'],c['zero_pfn'],p['pfn']) and
                tuple(map(int,r[13:]))==(2,1,busy), 'transition receipt identity/ownership differs')
        require(c['actor']>0 and (c['actor']==o['tid'] if native else all(c['actor']!=v['tid'] for v in row['origins'])), 'wrong local fault task')
        if not native:
            tag='KD_MM_UNMAP handback ' if busy else 'KD_MM_BOUNDARY_SHARED_PRIVATE done '
            body=next((v for v in re.finditer(tag+IDENT,log) if v.group(3)==str(o['tid'])),None)
            require(body and transitions[0].end()<body.start(), 'target state was not revalidated after the local fault')
    zero_removals=len(re.findall('KD_MM_BOUNDARY_SHARED_ZERO done '+IDENT,log))
    require(zero_removals+result['remote_changed_boundary_private_removals']==result['remote_boundary_removals'], 'wrong body class counted')
    result.update(remote_shared_zero_removals=zero_removals,controlled_shared_zero_private=changed,controlled_shared_zero_busy=busy)
    return result
