#!/usr/bin/env python3
"""Exact private-near holds, two-split retention and pre-effect busy refusal."""
from pathlib import Path
import re
import runpy
base=runpy.run_path(str(Path(__file__).parents[1]/'boundary_interior_missing/receipts.py'))
require,IDENT=base['require'],base['IDENT']
compare_native,compare_success=base['compare_native'],base['compare_success']

def validate(row,log):
    result=base['validate'](row,log,empty=True,near_private=True)
    near=2 if row['interior_right'] else 0
    mode,native=row['mode'],row['native'];g=0 if native else 1
    require(row['near_private_write_checks']==sum(bool(o['layouts'][near]['mapped']) for o in row['origins']),
            'private-survivor isolated writes missing')
    origins={str(o['tid']):(i,o) for i,o in enumerate(row['origins'])}
    bodies=re.findall('KD_MM_BOUNDARY_INTERIOR_EMPTY (?:done|error) '+IDENT,log)
    kept=re.findall('KD_MM_INTERIOR_NEAR_PRIVATE kept '+IDENT+
        r' pfn=([0-9a-f]+) refs_before=3 refs_after=3 mapcount=1 pte_same=1 held=1 released=1 result=(0|-12)',log)
    require(sorted(r[:6] for r in kept)==sorted(bodies), 'exact near hold/preservation/retirement not paired with every body/error')
    require(log.count('KD_MM_INTERIOR_NEAR_PRIVATE kept ')==len(kept), 'malformed or duplicate near preservation receipt')
    for r in kept:
        i,o=origins[r[2]];p=row['pages_before'][i*3+near]
        require(int(r[6],16)==p['pfn']==row['ptes_before'][i]['pfn'][near] and
            p['maps']==1 and p['refs']==2 and int(r[7])==(-12 if row['injection'] else 0),
            'wrong near page, hold count or error route')
        prefix='KD_MM_INTERIOR_NEAR_PRIVATE kept '+re.escape('mm='+r[0]+' id='+r[1]+' origin='+r[2]+' executor='+r[3]+' start='+r[4]+' end='+r[5])
        position=re.search(prefix,log)
        done=re.search('KD_MM_BOUNDARY_INTERIOR_EMPTY (?:done|error) '+re.escape('mm='+r[0]+' id='+r[1]+' origin='+r[2]),log)
        require(position and done and position.start()<done.start(), 'body published before exact hold retirement')
    roll=re.findall('KD_MM_INTERIOR_NEAR_PRIVATE rollback '+IDENT+r' pfn=([0-9a-f]+) held=1 released=1 effects=0',log)
    near_rollback=not native and not row['interior_right'] and mode=='change-far-busy'
    require(len(roll)==near_rollback and log.count('KD_MM_INTERIOR_NEAR_PRIVATE rollback ')==len(roll),
            'near hold missing on late far refusal or falsely claimed on early refusal')
    if near_rollback:
        ack=re.findall('KD_MM_UNMAP handback '+IDENT,log)
        require(len(ack)==1 and roll[0][:6]==ack[0] and int(roll[0][6],16)==row['pages_before'][g*3+near]['pfn'],
                'near rollback did not release the exact victim page before handback')
    if row['changing']:validate_change(row,log,near)
    else:require(not re.search(r'KD_MM_TEST (?:edge_empty_change|edge_private_busy) ',log), 'unexpected queued change')
    return dict(result,private_near_holds_retired=len(kept),private_near_rollback=int(near_rollback),
        private_near_write_checks=row['near_private_write_checks'])

def validate_change(row,log,near):
    mode,native=row['mode'],row['native'];g=0 if native else 1
    o=row['origins'][g];c,m=row['change'],row['change_more']
    busy=mode in ('change-near-busy','change-far-busy')
    private=mode=='change-private'
    slot=(near if mode=='change-near-busy' else 2-near) if busy else 1
    tag='edge_private_busy' if busy else 'edge_empty_change'
    matches=list(re.finditer('KD_MM_TEST '+tag+r' ([^\n]+)',log))
    require(len(matches)==1,'exact queued eligibility change missing/duplicate')
    require(c['done']==1 and c['result']==c['before_zero']==0 and c['after_private']==(busy or private) and
        c['index']==g*3+slot and c['pending']==(0 if native else 2) and c['readers']==(1 if native else 2) and
        (native or c['admission']==-1), 'queued transition slot/ordering differs')
    table=row['walks_before'][g]['table_pfn'][slot]
    require(m==dict(mode=10 if busy else 8 if private else 7,before_none=int(not busy),after_zero=int(not (busy or private)),
        table_before=table,table_after=table,anon_before=o['original_anon'],anon_after=o['original_anon']) and table>0 and o['original_anon']>0,
        'transition changed table/ancestry identity or fabricated an initial empty state')
    expected=dict(mm=row['mm'],index=c['index'],actor=c['actor'],pending=c['pending'],readers=c['readers'],admission=c['admission'],mode=m['mode'],
        table_before=table,table_after=table,anon_before=o['original_anon'],anon_after=o['original_anon'],result=0)
    if busy or private:
        require(len(c['page'])==1 and c['zero_pfn']==0,'private observation/reference missing')
        p=c['page'][0]
        require(p['address']==o['old_start']+slot*4096 and p['pfn']>0 and p['maps']==1 and p['refs']==2 and
            p['hash']>0 and p['charged_same'] and p['locked']==busy,'private transition ownership differs')
        expected['private_pfn']=p['pfn']
        if busy:
            before=row['pages_before'][g*3+slot]
            require(all(p[k]==before[k] for k in ('address','pfn','hash','maps','refs','charged_same')),'busy change replaced or modified the existing survivor')
        else:require(p['pfn']!=row['pages_before'][g*3+near]['pfn'],'new private target aliases near survivor')
    else:
        require(not c['page'] and c['zero_pfn']>0,'read fault acquired private ownership')
        expected['private_pfn']=0
    if busy:expected.update(before_locked=0,after_locked=1,refs=2,mapcount=1)
    else:expected.update(before_none=1,after_zero=int(not private),after_private=int(private),zero_pfn=c['zero_pfn'])
    fields=dict(re.findall(r'(\w+)=(\S+)',matches[0].group(1)))
    hexa={'mm','table_before','table_after','anon_before','anon_after','zero_pfn','private_pfn'}
    require({k:int(v,16 if k in hexa else 10) for k,v in fields.items()}==expected,'queued receipt not bound to exact page/table state')
    require(c['actor']>0 and (c['actor']==o['tid'] if native else all(c['actor']!=x['tid'] for x in row['origins'])), 'wrong queued modifier')
    if not native:
        ack=re.search('KD_MM_UNMAP handback '+IDENT,log)
        require(ack and ack.group(3)==str(o['tid']) and matches[0].end()<ack.start(),'unsupported changed class did not hand back before effects')
