#!/usr/bin/env python3
"""Empty shared-table body completion and actual queued read/write faults."""
from pathlib import Path
import re
import runpy
edge=runpy.run_path(str(Path(__file__).parents[1]/'boundary_edge/receipts.py'))
require,IDENT=edge['require'],edge['IDENT']
compare_native,compare_success=edge['compare_native'],edge['compare_success']


def validate(row,log):
    result=edge['validate'](row,log,empty=True,shared=True)
    mode,native,target=row['mode'],row['native'],row['slice']
    changed=mode in ('change-zero','change-private','change-private-busy')
    private=changed and mode!='change-zero';busy=mode=='change-private-busy'
    pattern=(r'KD_MM_TEST shared_empty_change mm=([0-9a-f]+) index=(\d+) actor=(\d+) pending=(\d+) readers=(\d+) admission=(-?\d+) mode=(\d+)'
             r' before_none=1 before_zero=0 after_zero=(\d+) after_private=(\d+) table_before=([0-9a-f]+) table_after=([0-9a-f]+)'
             r' anon_before=([0-9a-f]+) anon_after=([0-9a-f]+) zero_pfn=([0-9a-f]+) private_pfn=([0-9a-f]+) refs=(\d+) mapcount=(\d+) locked=(\d+) result=0')
    transitions=list(re.finditer(pattern,log))
    require(len(transitions)==changed, 'controlled empty-leaf transition missing or duplicate')
    if changed:
        g=0 if native else 1;o=row['origins'][g];c,m=row['change'],row['change_more'];r=transitions[0].groups()
        table=row['walks_before'][g]['table_pfn'][target]
        require(c['done']==1 and c['result']==c['before_zero']==0 and c['after_private']==private and
                c['index']==g*3+target and c['pending']==(0 if native else 2 if busy else 3) and
                c['readers']==(1 if native else 2) and (native or c['admission']==-1), 'transition not before locked execution')
        require(not any(row['masks']) and not any(row['zero_masks']) and
                m['mode']==(15 if busy else 14 if private else 13) and m['before_none']==1 and m['after_zero']==(not private) and
                m['table_before']==m['table_after']==table>0 and m['anon_before']==0 and bool(m['anon_after'])==private,
                'target was not an empty leaf in the same existing table')
        if private:
            require(len(c['page'])==1 and c['zero_pfn']==0, 'new private inspection reference missing')
            p=c['page'][0]
            require(p['address']==o['start'] and p['pfn']>0 and p['maps']==1 and p['refs']==2 and
                    p['hash']>0 and p['charged_same'] and p['locked']==busy, 'new private reference/lock differs')
            state=(p['pfn'],2,1,busy)
        else:
            require(not c['page'] and c['zero_pfn']>0, 'read fault acquired ordinary page ownership')
            state=(0,0,0,0)
        require(int(r[0],16)==row['mm'] and tuple(map(int,r[1:9]))==
                (c['index'],c['actor'],c['pending'],c['readers'],c['admission'],m['mode'],not private,private) and
                tuple(int(v,16) for v in r[9:15])==(table,table,0,m['anon_after'],c['zero_pfn'],state[0]) and
                tuple(map(int,r[15:]))==state[1:], 'transition receipt identity/ownership differs')
        require(c['actor']>0 and (c['actor']==o['tid'] if native else all(c['actor']!=v['tid'] for v in row['origins'])), 'wrong local fault task')
        if not native:
            tag='KD_MM_UNMAP handback ' if busy else 'KD_MM_BOUNDARY_SHARED_PRIVATE done ' if private else 'KD_MM_BOUNDARY_SHARED_ZERO done '
            body=next((v for v in re.finditer(tag+IDENT,log) if v.group(3)==str(o['tid'])),None)
            require(body and transitions[0].end()<body.start(), 'state change did not precede locked classification/handback')
            if not private:
                line=log[body.start():].splitlines()[0]
                require(re.search(r' zero_pfn='+format(c['zero_pfn'],'x')+r' zero_owned=0',line), 'changed zero physical identity lost')
    empty_removals=len(re.findall('KD_MM_BOUNDARY_SHARED_EMPTY done '+IDENT,log))
    require(empty_removals+result['remote_changed_boundary_private_removals']+result['remote_changed_boundary_zero_removals']==result['remote_boundary_removals'], 'wrong body class counted')
    result.update(remote_shared_empty_removals=empty_removals,controlled_shared_empty_zero=changed and not private,
                  controlled_shared_empty_private=private,controlled_shared_empty_busy=busy)
    return result
