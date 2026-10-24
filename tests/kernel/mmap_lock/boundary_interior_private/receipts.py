#!/usr/bin/env python3
"""Bind interior private teardown and pre-effect rollback to exact page ownership."""
from pathlib import Path
import re
import runpy

base=runpy.run_path(str(Path(__file__).parents[1]/'boundary_interior_missing/receipts.py'))
require,IDENT=base['require'],base['IDENT']
compare_native,compare_success=base['compare_native'],base['compare_success']


def validate(row,log):
    result=base['validate'](row,log,private=True)
    mode,native,right=row['mode'],row['native'],row['interior_right']
    g=0 if native else 1;near=2 if right else 0;far=2-near
    o=row['origins'][g];c,m=row['change'],row['change_more']
    require(not re.search(r'KD_MM_INTERIOR_NEAR_PRIVATE (?:kept|rollback) ',log),
            'private target incorrectly acquired a private near survivor')
    busy=mode in ('change-busy','change-far-busy')
    zero=mode=='change-near-zero'
    changes=list(re.finditer(r'KD_MM_TEST (edge_private_busy|interior_near_zero) ([^\n]+)',log))
    require(len(changes)==log.count('KD_MM_TEST edge_private_busy ')+log.count('KD_MM_TEST interior_near_zero ')==bool(busy or zero),
            'queued eligibility receipt missing or duplicated')
    if busy or zero:
        slot=near if zero else far if mode=='change-far-busy' else 1
        index=g*3+slot;table=row['walks_before'][g]['table_pfn'][slot]
        require(c['done']==1 and c['result']==c['before_zero']==0 and c['after_private']==busy and
                c['index']==index and c['pending']==(0 if native else 2) and c['readers']==(1 if native else 2) and
                (native or c['admission']==-1), 'change was not behind the published writer queue')
        require(m==dict(mode=21 if zero else 10,before_none=int(zero),after_zero=int(zero),
                table_before=table,table_after=table,anon_before=o['original_anon'],anon_after=o['original_anon']) and
                table>0 and o['original_anon']>0 and row['walks_after'][g]['table_pfn'][slot]==table,
                'controlled eligibility change lost the retained table or reverse-map ancestry')
        expected=dict(mm=row['mm'],index=index,actor=c['actor'],pending=c['pending'],readers=c['readers'],
            admission=c['admission'],mode=m['mode'],table_before=table,table_after=table,
            anon_before=o['original_anon'],anon_after=o['original_anon'],result=0)
        if busy:
            p=dict(row['pages_before'][index]);p['locked']=1
            require(c['page']==[p] and p['pfn']>0 and p['refs']==2 and p['maps']==1 and
                    not c['zero_pfn'] and not row['pages_before'][index]['locked'],
                    'busy control changed a physical page or acquired another reference')
            expected.update(before_locked=0,after_locked=1,private_pfn=p['pfn'],refs=2,mapcount=1)
        else:
            require(not c['page'] and c['zero_pfn']>0 and row['ptes_before'][g]['none']&(1<<near) and
                    row['ptes_after'][g]['zero']&(1<<near), 'near read fault acquired private ownership or failed to create a real zero PTE')
            expected.update(before_none=1,after_zero=1,after_private=0,zero_pfn=c['zero_pfn'],private_pfn=0)
        fields=dict(re.findall(r'(\w+)=(\S+)',changes[0].group(2)))
        hexa={'mm','table_before','table_after','anon_before','anon_after','zero_pfn','private_pfn'}
        require({k:int(v,16 if k in hexa else 10) for k,v in fields.items()}==expected,
                'queued eligibility receipt differs from exact live state')
        require(c['actor']>0 and (c['actor']==o['tid'] if native else all(c['actor']!=x['tid'] for x in row['origins'])),
                'modifier is not an existing local reader')
        if not native:
            ack=re.search(r'KD_MM_UNMAP handback '+IDENT,log)
            require(ack and ack.group(3)==str(o['tid']) and changes[0].end()<ack.start(),
                    'changed eligibility did not cause handback before destructive work')
    else:require(not any(m.values()), 'unrequested eligibility change')
    rolled=not native and mode in ('change-far-busy','change-near-zero')
    rolls=list(re.finditer(r'KD_MM_INTERIOR_TARGET rollback '+IDENT+
        r' pfn=([0-9a-f]+) refs_before=3 refs_held=3 mapcount=1 pte_same=1 held=1 released=1 target_put=1 effects=0',log))
    require(len(rolls)==log.count('KD_MM_INTERIOR_TARGET rollback ')==rolled,
            'exact pre-effect target hold was lost, duplicated or invented')
    if rolled:
        ack=re.search(r'KD_MM_UNMAP handback '+IDENT,log)
        require(rolls[0].groups()[:6]==ack.groups() and int(rolls[0].group(7),16)==row['pages_before'][g*3+1]['pfn'] and
                changes[0].end()<rolls[0].start()<ack.start(), 'target retirement was not before its exact handback/ACK')
    return dict(result,controlled_target_busy=mode=='change-busy',controlled_far_busy=mode=='change-far-busy',
        controlled_near_zero=zero,exact_target_rollback=int(rolled),probe_holds_dropped_before_body=bool(row['free_first']))
