#!/usr/bin/env python3
"""Missing shared leaf: exact geometry, real faults and post-fault inaccessibility."""
from pathlib import Path
import re
import runpy
edge=runpy.run_path(str(Path(__file__).parents[1]/'boundary_edge/receipts.py'))
require,IDENT=edge['require'],edge['IDENT']
compare_native,compare_success=edge['compare_native'],edge['compare_success']


def validate(row,log):
    result=edge['validate'](row,log,shared=True,shared_missing=True)
    mode,native,target=row['mode'],row['native'],row['slice']
    victim=0 if native else 1
    require(row['shape'] in ('prefix-ur','prefix-uz','prefix-uu','suffix-ru','suffix-zu','suffix-uu'),
            'missing table cannot contain a populated near survivor')
    for g,w in enumerate(row['walks_before']):
        if row['injection'] and not native and g==0:continue
        same=3 if target==0 else 6
        require(w['pmd_none']&same==same and not any(w['table_pfn'][p] for p in (target,1)) and
                not ((row['masks'][g]|row['zero_masks'][g])&same) and not w['upper_none'],
                'target/near table actually absent with required upper levels')
    removed=sum(not o['layouts'][target]['mapped'] for o in row['origins'])
    require(row['target_rechecks_accessed']==row['target_rechecks_written']==removed,
            'near demand fault/private writes restored target access or were not rechecked')
    moved=row['retention_change'];o=row['origins'][victim]
    if mode=='free-table':
        address=o['old_start']+(-2 if target==0 else 4)*4096
        require(moved==dict(before_start=address,before_end=address+4096,before_zero=0,
                           table_before=0,table_after=0,before_publication=1) and
                row['walks_after'][victim]['pmd_none']&(1<<target),
                'retention loss must be tested without creating the missing target table')
    else:require(not any(moved.values()), 'unexpected retention prerequisite change')
    modes={'appear-near-zero':16,'appear-zero':17,'appear-private':18,'appear-private-busy':19}
    changed=mode in modes;near=mode=='appear-near-zero'
    private=mode in ('appear-private','appear-private-busy');busy=mode=='appear-private-busy'
    pattern=(r'KD_MM_TEST shared_table_change mm=([0-9a-f]+) index=(\d+) actor=(\d+) pending=(\d+) readers=(\d+) admission=(-?\d+) mode=(\d+)'
             r' before_table_none=1 after_zero=(\d+) after_private=(\d+) table_before=([0-9a-f]+) table_after=([0-9a-f]+)'
             r' anon_before=([0-9a-f]+) anon_after=([0-9a-f]+) zero_pfn=([0-9a-f]+) private_pfn=([0-9a-f]+) refs=(\d+) mapcount=(\d+) locked=(\d+) result=0')
    transitions=list(re.finditer(pattern,log))
    require(len(transitions)==changed, 'missing-table transition missing or duplicate')
    c,m=row['change'],row['change_more']
    if changed:
        r=transitions[0].groups();slot=1 if near else target
        table=row['walks_after'][victim]['table_pfn'][target]
        require(c['done']==1 and c['result']==c['before_zero']==0 and c['after_private']==private and
                c['index']==victim*3+slot and c['pending']==(0 if native else 2 if busy else 3) and
                c['readers']==(1 if native else 2) and (native or c['admission']==-1), 'fault did not precede locked execution')
        require(not any(row['masks']) and not any(row['zero_masks']) and
                m['mode']==modes[mode] and m['before_none']==0 and m['after_zero']==(not private) and
                m['table_before']==0 and m['table_after']==table>0 and m['anon_before']==0 and bool(m['anon_after'])==private,
                'missing table confused with an existing empty leaf or fault-created table lost')
        if private:
            require(len(c['page'])==1 and c['zero_pfn']==0, 'new private reference missing')
            p=c['page'][0]
            require(p['address']==o['start'] and p['pfn']>0 and p['maps']==1 and p['refs']==2 and
                    p['hash']>0 and p['charged_same'] and p['locked']==busy, 'new private reference/lock differs')
            state=(p['pfn'],2,1,busy)
        else:
            require(not c['page'] and c['zero_pfn']>0, 'read fault acquired private-page ownership')
            state=(0,0,0,0)
        require(int(r[0],16)==row['mm'] and tuple(map(int,r[1:9]))==
                (c['index'],c['actor'],c['pending'],c['readers'],c['admission'],m['mode'],not private,private) and
                tuple(int(v,16) for v in r[9:15])==(0,table,0,m['anon_after'],c['zero_pfn'],state[0]) and
                tuple(map(int,r[15:]))==state[1:], 'transition receipt identity/ownership differs')
        require(c['actor']>0 and (c['actor']==o['tid'] if native else all(c['actor']!=v['tid'] for v in row['origins'])), 'wrong local fault task')
        if not native:
            tag='KD_MM_UNMAP handback ' if busy else 'KD_MM_BOUNDARY_SHARED_PRIVATE done ' if private else 'KD_MM_BOUNDARY_SHARED_EMPTY done ' if near else 'KD_MM_BOUNDARY_SHARED_ZERO done '
            body=next((v for v in re.finditer(tag+IDENT,log) if v.group(3)==str(o['tid'])),None)
            require(body and transitions[0].end()<body.start(), 'appearance did not precede locked classification or handback')
            if not private and not near:
                line=log[body.start():].splitlines()[0]
                require(re.search(r' zero_pfn='+format(c['zero_pfn'],'x')+r' zero_owned=0',line), 'changed zero physical identity lost')
    else:require(not any(m.values()), 'unexpected controlled appearance')
    missing_removals=len(re.findall('KD_MM_BOUNDARY_SHARED_MISSING done '+IDENT,log))
    require(missing_removals+sum(result['remote_changed_boundary_'+k+'_removals'] for k in ('empty','zero','private'))==result['remote_boundary_removals'], 'wrong body class counted')
    result.update(remote_shared_missing_removals=missing_removals,controlled_missing_near_zero=near,
                  controlled_missing_target_zero=mode=='appear-zero',controlled_missing_target_private=private,
                  controlled_missing_target_busy=busy,target_inaccessible_after_survivor_faults=True)
    return result
