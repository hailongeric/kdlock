#!/usr/bin/env python3
"""Bind native queued near faults to exact revalidated body/hold retirement."""
from pathlib import Path
import re
import runpy

base=runpy.run_path(str(Path(__file__).parents[1]/'boundary_interior_missing/receipts.py'))
require,IDENT=base['require'],base['IDENT']
compare_native,compare_success=base['compare_native'],base['compare_success']
OUTCOMES={'create':0,'create-busy':1,'create-far-busy':2,'create-cancel':3,'create-error1':4,'create-error2':4}


def validate(row,log):
    zero=bool(row['boundary_zero_test'])
    result=base['validate'](row,log,empty=not zero,zero=zero,near_create=True)
    native,right,mode=row['native'],row['interior_right'],row['mode']
    g=0 if native else 1;near=2 if right else 0;far=2-near
    o=row['origins'][g];c,m,n=row['change'],row['change_more'],row['near_create']
    outcome=OUTCOMES[mode];initial_zero=bool(row['zero_masks'][g]&(1<<near))
    require(n['index']==c['index']==g*3+near and n['from_zero']==initial_zero and n['outcome']==outcome,
            'creation control does not name the initially unowned near slot')
    require(c['done']==c['after_private']==1 and c['result']==0 and c['before_zero']==initial_zero and
            c['pending']==(0 if native else 3 if not outcome else 2) and c['readers']==(1 if native else 2) and
            (native or c['admission']==-1), 'native fault did not run behind the published writer queue')
    require(len(c['page'])==1 and bool(c['zero_pfn'])==initial_zero, 'new private reference or initial zero identity missing')
    p=c['page'][0];table=row['walks_before'][g]['table_pfn'][near]
    require(p['address']==o['old_start']+near*4096 and p['pfn']>0 and p['pfn']!=c['zero_pfn'] and
            p['maps']==1 and p['refs']==2 and p['hash']>0 and p['charged_same']==1 and p['locked']==(outcome==1),
            'new near page eligibility/reference differs')
    require(all(p['pfn']!=a['pfn'] for a in row['pages_before']), 'created survivor aliases an existing owned page')
    require(m==dict(mode=20,before_none=int(not initial_zero),after_zero=0,table_before=table,table_after=table,
            anon_before=o['original_anon'],anon_after=m['anon_after']) and table>0 and m['anon_after']>0 and
            (not m['anon_before'] or m['anon_before']==m['anon_after']) and
            row['walks_after'][g]['table_pfn'][near]==table,
            'creation changed the retained leaf identity or lost existing/new reverse-map ancestry')
    expected=dict(mm=row['mm'],index=c['index'],actor=c['actor'],pending=c['pending'],readers=c['readers'],
        admission=c['admission'],mode=20,from_zero=int(initial_zero),outcome=outcome,before_none=int(not initial_zero),
        before_zero=int(initial_zero),after_private=1,table_before=table,table_after=table,
        anon_before=m['anon_before'],anon_after=m['anon_after'],zero_pfn=c['zero_pfn'],private_pfn=p['pfn'],
        refs=2,mapcount=1,locked=int(outcome==1),far_index=0,far_table=0,far_pfn=0,far_refs=0,far_maps=0,far_locked=0,result=0)
    if outcome==2:
        require(n['far_index']==g*3+far and len(n['far_page'])==1 and
                n['far_table']==row['walks_before'][g]['table_pfn'][far]>0, 'busy far identity missing')
        f=n['far_page'][0];original=row['pages_before'][g*3+far]
        require(all(f[k]==original[k] for k in ('address','pfn','maps','refs','charged_same')) and
                f['refs']==2 and f['maps']==1 and f['locked']==1 and f['hash']==0,
                'far lock fabricated another reference, fault or page replacement')
        expected.update(far_index=n['far_index'],far_table=n['far_table'],far_pfn=f['pfn'],far_refs=2,far_maps=1,far_locked=1)
    else:require(n['far_index']==n['far_table']==0 and not n['far_page'], 'unrequested far-page ownership')
    transitions=list(re.finditer(r'KD_MM_TEST near_create ([^\n]+)',log))
    require(len(transitions)==log.count('KD_MM_TEST near_create ')==1, 'exact creation receipt missing/duplicate')
    fields=dict(re.findall(r'(\w+)=(\S+)',transitions[0].group(1)))
    hexa={'mm','table_before','table_after','anon_before','anon_after','zero_pfn','private_pfn','far_table','far_pfn'}
    require({k:int(v,16 if k in hexa else 10) for k,v in fields.items()}==expected, 'creation receipt not bound to exact live state')
    require(c['actor']>0 and (c['actor']==o['tid'] if native else all(c['actor']!=x['tid'] for x in row['origins'])),
            'modifier is not the existing local reader')
    require(row['near_private_write_checks']==1, 'created near survivor isolated write missing')
    body_tag='KD_MM_BOUNDARY_INTERIOR_'+('ZERO' if zero else 'EMPTY')
    bodies=list(re.finditer(body_tag+r' (?:done|error) '+IDENT,log))
    admitted=not native and outcome in (0,4)
    victim_bodies=[b for b in bodies if b.group(3)==str(o['tid'])]
    require(len(victim_bodies)==admitted, 'new near path did not complete exactly once or refused after effects')
    kept=list(re.finditer(r'KD_MM_INTERIOR_NEAR_PRIVATE kept '+IDENT+
        r' pfn=([0-9a-f]+) refs_before=3 refs_after=3 mapcount=1 pte_same=1 held=1 released=1 result=(0|-12)',log))
    require(len(kept)==log.count('KD_MM_INTERIOR_NEAR_PRIVATE kept ')==admitted,
            'exact new-near hold/retirement missing, duplicated or attributed to an unchanged peer')
    if admitted:
        b=victim_bodies[0];k=kept[0]
        require(k.groups()[:6]==b.groups() and int(k.group(7),16)==p['pfn'] and
                int(k.group(8))==(-12 if outcome==4 else 0) and
                transitions[0].end()<k.start()<b.start(), 'body used stale survivor state or published before exact retirement')
    elif not native and outcome in (1,2):
        ack=re.search(r'KD_MM_UNMAP handback '+IDENT,log)
        require(ack and ack.group(3)==str(o['tid']) and transitions[0].end()<ack.start(), 'busy refusal was not before effects')
    roll=list(re.finditer(r'KD_MM_INTERIOR_NEAR_PRIVATE rollback '+IDENT+r' pfn=([0-9a-f]+) held=1 released=1 effects=0',log))
    rolled=not native and not right and outcome==2
    require(len(roll)==log.count('KD_MM_INTERIOR_NEAR_PRIVATE rollback ')==rolled, 'late far refusal lost or invented a near hold')
    if rolled:
        ack=re.search(r'KD_MM_UNMAP handback '+IDENT,log)
        require(roll[0].groups()[:6]==ack.groups() and int(roll[0].group(7),16)==p['pfn'] and
                transitions[0].end()<roll[0].start()<ack.start(), 'new survivor rollback not bound to original ACK route')
    return dict(result,queued_near_creation=True,created_from='zero' if initial_zero else 'untouched',
        created_near_different_task_removals=int(admitted and not outcome),
        created_near_remote_errors=int(admitted and outcome==4),created_near_holds_retired=len(kept),
        created_near_rollback=int(rolled),private_near_write_checks=1,
        controlled_creation_cancelled=int(not native and outcome==3))
