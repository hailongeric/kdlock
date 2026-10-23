#!/usr/bin/env python3
"""Bind boundary geometry, native retention bounds and exact remote completion."""
from pathlib import Path
import re
import runpy

common = runpy.run_path(str(Path(__file__).parents[1]/'zero_target/receipts.py'))
require, IDENT = common['require'], common['IDENT']
PAGE, PMD, PUD = 4096, 2<<20, 1<<30


def compare_native(a,b):
    common['compare_native'](a,b)


def compare_success(a,b):
    require(a['native']==1 and b['native']==0 and all(a[k]==b[k] for k in ('shape','mode','slice','injection')), 'native control input mismatch')
    require(not a['injection'] and not a['cancel'] and not b['cancel'], 'success control used for error/cancel')
    expected=common['semantic_layout'](a)
    for g,o in enumerate(b['origins']):
        require([{k:p[k] for k in ('mapped','lo','hi','pgoff','flags')} for p in o['layouts']]==expected and
                o['result']==a['origins'][0]['result']==0, 'native boundary result differs')
        require(all(x[0]==y[g] for x,y in zip(a['residency'],b['residency'])), 'native boundary resident accounting differs')
    return dict(shape=a['shape'],mode=a['mode'],layouts_equal=True,residency_equal=True)


def validate(row, log, *, empty=False):
    ev=common['validate'](row,log,absent=True,boundary=True,boundary_empty=empty)
    n,native,target,mode=row['groups'],row['native'],row['slice'],row['mode']
    victim=0 if native else 1
    require(target in (0,2) and mode in (('success','error','cancel','change-zero','change-private','free-table','shared','fault','busy') if empty else ('success','error','cancel','appear','table','free-table','shared','fault','busy')), 'unsupported edge input')
    require(row['injection']==(mode=='error') and row['cancel']==(mode=='cancel') and row['fault_interaction']==(mode=='fault') and
            row['busy_page']==(mode=='busy') and not row['free_first'] and row['interval_cleanup_calls']==n*4, 'case/control/cleanup routing differs')
    require((row['page_size'],row['pmd_size'],row['pud_size'])==(PAGE,PMD,PUD) and row['pgdir_size'] in (1<<39,1<<48), 'unsupported architecture geometry')
    require(row['table_bytes_after']==row['table_bytes_before']+PAGE*(mode=='appear' and not empty or mode=='fault' and not native)-PAGE*(mode=='free-table'), 'unexpected table creation or destruction')
    keys=['walks_before','walks_after','walks_accessed','walks_written','walks_cleanup','neighbors','anchors','tables_before','tables_after']
    require(all(len(row[k])==n for k in keys), 'incomplete table/neighbor observations')
    for g,o in enumerate(row['origins']):
        lo,hi=o['old_start'],o['old_end'];start,end=o['start'],o['end']
        head=row['injection'] and not native and g==0
        selected=g==victim
        require(hi-lo==3*PAGE and (start,end)==((lo,hi) if head else (lo+target*PAGE,lo+(target+1)*PAGE)), 'request does not match three-page geometry')
        first,last=lo//PMD,(hi-1)//PMD
        require(lo//PUD==(hi-1)//PUD and last-first==(not head), 'unexpected page-table crossing')
        if not head:
            shared=mode=='shared' and selected
            require((start//PMD==(lo+PAGE)//PMD)==shared, 'edge sharing a survivor table was misclassified')
        neighbor=row['neighbors'][g]
        require(len(neighbor)==2, 'two outer VMA records required')
        for side,entry in enumerate(neighbor):
            expected=lo+(-2 if side==0 else 4)*PAGE
            if mode=='free-table' and selected and side==bool(target):expected+=PMD if side else -PMD
            require(entry['address']==entry['start']==expected and entry['end']==expected+PAGE and entry['unchanged']==1 and
                    not entry['anon'] and not entry['other'] and not entry['pfn'] and
                    entry['zero']==(side==bool(target) and (empty and not (mode=='free-table' and selected) or mode=='table' and selected)) and entry['none']==(not entry['zero']), 'retaining neighbor moved, populated or disappeared')
        require(row['anchors'][g]==first*PMD+2*PMD+8*PAGE and row['anchors'][g]//PUD==lo//PUD, 'upper-level anchor geometry differs')
        before=row['walks_before'][g]
        for phase,key in enumerate(('walks_before','walks_after','walks_accessed','walks_written')):
            w=row[key][g];leaf=0
            for p in range(3):
                interval=(lo+p*PAGE)//PMD
                populated=any((lo+q*PAGE)//PMD==interval and
                              (bool((row['masks'][g]|row['zero_masks'][g])&(1<<q)) if phase<2 else bool(o['layouts'][q]['mapped']))
                              for q in range(3))
                if (not (selected and mode=='free-table' and phase) if empty else selected and (mode=='table' or phase==0 and mode=='free-table' or phase>0 and mode=='appear')) and interval==(lo+target*PAGE)//PMD:populated=True
                if phase>0 and mode=='fault' and not native and g==1 and interval==(lo+row['late_slot']*PAGE)//PMD:populated=True
                if phase>=2 and any(e['address']//PMD==interval for e in neighbor):populated=True
                if head:populated=True
                if populated:leaf|=1<<p
                require(bool(w['table_pfn'][p])==populated and w['parent_pfn'][p]==before['parent_pfn'][0]>0, 'wrong or replaced table identity')
                if phase and populated and before['table_pfn'][p]:require(w['table_pfn'][p]==before['table_pfn'][p], 'existing table replaced')
                for q in range(p):
                    if w['table_pfn'][p] and w['table_pfn'][q]:require((w['table_pfn'][p]==w['table_pfn'][q])==((lo+p*PAGE)//PMD==(lo+q*PAGE)//PMD), 'physical table aliases wrong interval')
            require(w['leaf']==leaf and w['pmd_none']==(7^leaf) and w['upper_none']==0, 'missing leaf confused with missing upper level')
            if phase<2:require(row['tables_before' if phase==0 else 'tables_after'][g]==dict(leaf=leaf,higher_none=7^leaf,pfn=w['table_pfn']), 'two walk observations disagree')
        require(row['walks_written'][g]==row['walks_accessed'][g], 'private writes changed table identity')
        cleaned=row['walks_cleanup'][g]
        require(cleaned==dict(leaf=0,upper_none=7,pmd_none=0,parent_pfn=[0]*3,table_pfn=[0]*3), 'cleanup leaked tables or invalidated only part of hierarchy')
    suffix=(r' boundary=([0-9a-f]+) parent_pfn=([0-9a-f]+) survivor_table_pfn=([0-9a-f]+) survivor_missing=(\d+)'
            r' resident_mask=(\d+) zero_mask=(\d+) untouched_mask=(\d+) held=(\d+) released=(\d+) floor=([0-9a-f]+) ceiling=([0-9a-f]+)'
            rf' target_pmd_none={0 if empty else 1} target_owned=0 tables_unchanged=1')
    tag='KD_MM_BOUNDARY_EMPTY' if empty else 'KD_MM_BOUNDARY'
    tail=r' target_table_pfn=([0-9a-f]+) target_pte_none=1' if empty else ''
    dones=re.findall(tag+' done '+IDENT+suffix+tail,log)
    errors=re.findall(tag+' error '+IDENT+suffix+r' result=-12'+tail,log)
    queue_done=re.findall('KD_MM_UNMAP done '+IDENT+r' result=0',log)
    queue_errors=re.findall('KD_MM_UNMAP error '+IDENT+r' result=-12',log)
    require(sorted(r[:6] for r in dones)==sorted(queue_done) and sorted(r[:6] for r in errors)==sorted(queue_errors), 'actual boundary body not bound to completion/error')
    origins={str(o['tid']):(g,o) for g,o in enumerate(row['origins'])}
    for r in dones+errors:
        g,o=origins[r[2]];lo,hi=o['old_start'],o['old_end'];start,end=o['start'],o['end']
        w=row['walks_before'][g];survivor=0 if target else 1
        parent,leaf=int(r[7],16),int(r[8],16);floor,ceiling=int(r[15],16),int(r[16],16)
        require(int(r[6],16)==(hi-1)//PMD*PMD and parent==w['parent_pfn'][0] and
                leaf==w['table_pfn'][survivor] and int(r[9])==(not leaf) and bool(w['pmd_none']&(1<<target))==(not empty), 'body table state differs from verified input')
        if empty:require(int(r[17],16)==w['table_pfn'][target]==row['walks_after'][g]['table_pfn'][target]>0 and row['ptes_before'][g]['none']&(1<<target) and row['ptes_after'][g]['none']&(1<<target), 'empty target/table identity lost')
        require(tuple(map(int,r[10:15]))==(row['masks'][g],row['zero_masks'][g],7^(row['masks'][g]|row['zero_masks'][g]),row['masks'][g].bit_count(),row['masks'][g].bit_count()), 'body ownership/slot identities differ')
        require(floor==(start if target else row['neighbors'][g][0]['end']) and
                ceiling==(row['neighbors'][g][1]['start'] if target else end), 'native post-split retention bounds differ')
        addr=start//PMD*PMD
        if addr<floor:addr+=PMD
        cap=ceiling//PMD*PMD
        finish=end-PMD if end-1>cap-1 else end
        require(cap and addr>finish-1, 'native teardown would walk/free a table')
    trans=list(re.finditer('KD_MM_TEST table_change '+r'mm=([0-9a-f]+) index=(\d+) actor=(\d+) pending=(\d+) readers=(\d+) admission=(-?\d+) mode=6 before_table_none=1 after_zero=1 after_private=0 table_before=0 table_after=([0-9a-f]+) anon_before=0 anon_after=0 zero_pfn=([0-9a-f]+) private_pfn=0 result=0',log))
    require(len(trans)==(mode=='appear'), 'controlled target-table appearance missing/duplicated')
    if mode=='appear':
        c,m=row['change'],row['change_more'];r=trans[0].groups()
        require(c['done']==1 and c['result']==c['before_zero']==c['after_private']==0 and not c['page'] and c['zero_pfn']>0 and
                c['index']==victim*3+target and c['pending']==(0 if native else 2) and c['readers']==(1 if native else 2) and
                (native or c['admission']==-1), 'appearance ordering/reference ownership differs')
        require(m==dict(mode=6,before_none=0,after_zero=1,table_before=0,table_after=row['walks_after'][victim]['table_pfn'][target],anon_before=0,anon_after=0) and m['table_after']>0, 'fault-created table lost or replaced')
        require(int(r[0],16)==row['mm'] and tuple(map(int,r[1:6]))==(c['index'],c['actor'],c['pending'],c['readers'],c['admission']) and
                int(r[6],16)==m['table_after'] and int(r[7],16)==c['zero_pfn'], 'transition receipt identity differs')
        require(c['actor']>0 and (str(c['actor']) not in origins if not native else c['actor']==row['origins'][0]['tid']), 'wrong local modifier')
        if not native:
            ack=re.search('KD_MM_UNMAP handback '+IDENT,log)
            require(ack and ack.group(3)==str(row['origins'][1]['tid']) and trans[0].end()<ack.start(), 'table appearance did not cause pre-effect handback')
    elif not empty:require(not any(row['change_more'].values()), 'unexpected table appearance')
    if empty:validate_empty_controls(row,log)
    if mode!='fault':require(not any(row[k] for k in ('late_fault_blocked','late_fault_code','late_fault_value','late_fault_stack')), 'unrecorded fault obscures initial states')
    return dict(ev,remote_boundary_removals=len(dones),remote_boundary_errors=len(errors),remote_boundary_without_private_holds=sum(not row['masks'][origins[r[2]][0]] for r in dones),empty_target_checks=empty,retention_bounds_verified=True,
                native_target_table_frees=int(mode=='free-table'),controlled_table_appearance=mode=='appear',neighbor_preservation=True)


def validate_empty_controls(row,log):
    """Boundary-only transitions refuse; same-table support is not inherited."""
    mode,native,target=row['mode'],row['native'],row['slice']
    victim=0 if native else 1
    o=row['origins'][victim];w=row['walks_before'][victim]
    moved=row['retention_change']
    if mode=='free-table':
        address=o['old_start']+(-2 if target==0 else 4)*PAGE
        require(moved==dict(before_start=address,before_end=address+PAGE,before_zero=1,
                           table_before=w['table_pfn'][target],table_after=w['table_pfn'][target],before_publication=1)
                and moved['table_before']>0 and row['walks_after'][victim]['pmd_none']&(1<<target),
                'neighbor transition or required native table release unproven')
    else:require(not any(moved.values()), 'unexpected retention prerequisite change')
    transitions=list(re.finditer(r'KD_MM_TEST edge_empty_change mm=([0-9a-f]+) index=(\d+) actor=(\d+) pending=(\d+) readers=(\d+) admission=(-?\d+) mode=(\d+) before_none=1 after_zero=(\d+) after_private=(\d+) table_before=([0-9a-f]+) table_after=([0-9a-f]+) anon_before=0 anon_after=([0-9a-f]+) zero_pfn=([0-9a-f]+) private_pfn=([0-9a-f]+) result=0',log))
    changing=mode in ('change-zero','change-private')
    require(len(transitions)==changing, 'empty target transition missing/duplicate')
    c,m=row['change'],row['change_more']
    if not changing:
        require(not any(m.values()), 'unexpected controlled target state');return
    private=mode=='change-private';r=transitions[0].groups()
    require(c['done']==1 and c['result']==c['before_zero']==0 and c['after_private']==private and
            c['index']==victim*3+target and c['pending']==(0 if native else 2) and c['readers']==(1 if native else 2) and
            (native or c['admission']==-1) and c['actor']>0, 'transition ordering/ownership differs')
    require(m['mode']==(8 if private else 7) and m['before_none']==1 and m['after_zero']==(not private) and
            m['table_before']==m['table_after']==w['table_pfn'][target]==row['walks_after'][victim]['table_pfn'][target]>0 and
            not m['anon_before'] and bool(m['anon_after'])==private, 'pre-execution table or ancestry identity differs')
    require(int(r[0],16)==row['mm'] and tuple(map(int,r[1:9]))==(c['index'],c['actor'],c['pending'],c['readers'],c['admission'],m['mode'],not private,private) and
            tuple(int(v,16) for v in r[9:13])==(m['table_before'],m['table_after'],m['anon_after'],c['zero_pfn']), 'transition receipt not bound to observed state')
    if private:
        require(len(c['page'])==1 and c['zero_pfn']==0, 'private transition test reference missing')
        p=c['page'][0]
        require(p['address']==o['start'] and p['pfn']==int(r[13],16)>0 and p['maps']==1 and p['refs']==2 and p['hash']>0 and p['charged_same'] and not p['locked'], 'new private-page ownership differs')
    else:require(c['zero_pfn']>0 and not c['page'] and int(r[13],16)==0, 'zero transition acquired private ownership')
    require(c['actor']==o['tid'] if native else all(c['actor']!=origin['tid'] for origin in row['origins']), 'wrong transition executor')
    if not native:
        ack=re.search('KD_MM_UNMAP handback '+IDENT,log)
        require(ack and ack.group(3)==str(o['tid']) and transitions[0].end()<ack.start(), 'populated boundary target did not hand back before effects')
