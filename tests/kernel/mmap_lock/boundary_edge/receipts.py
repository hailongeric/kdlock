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
        # A changed surviving slot stays resident only in the queued victim.
        # The unchanged peers retain their separately validated input masks.
        if a['mode']!='change-near-private' or g==1:
            require(all(x[0]==y[g] for x,y in zip(a['residency'],b['residency'])), 'native boundary resident accounting differs')
    return dict(shape=a['shape'],mode=a['mode'],layouts_equal=True,residency_equal=True,changed_survivor_comparison=a['mode']=='change-near-private')


def validate(row, log, *, empty=False, zero=False, private=False, shared=False, shared_missing=False, neighbor=False, interior=False, interior_near_zero=False):
    existing=empty or zero or private
    ev=common['validate'](row,log,absent=not (zero or private),boundary=True,boundary_empty=empty,boundary_zero=zero,boundary_private=private,boundary_shared=shared,boundary_shared_missing=shared_missing,neighbor=neighbor,interior=interior,interior_near_zero=interior_near_zero)
    n,native,target,mode=row['groups'],row['native'],row['slice'],row['mode']
    victim=0 if native else 1
    require((target==1 if interior else target in (0,2)) and mode in ((('success','error1','error2','cancel','change-private','change-near-private','free-table','fault') if zero else ('success','error1','error2','cancel','change-zero','change-private','change-near-private','free-table','fault') if empty else ('success','error1','error2','cancel','appear','table','free-table','fault')) if interior else ('success','error','cancel','appear-near-zero','appear-zero','appear-private','appear-private-busy','free-table','fault') if shared_missing else ('success','error','cancel','free','change-busy','change-near-zero','free-table','shared','fault','busy') if private else ('success','error','cancel','change-zero','change-private','change-private-busy','free-table','shared','fault','busy') if existing else ('success','error','cancel','appear','table','free-table','shared','fault','busy')), 'unsupported edge input')
    require(row['injection']==((1 if mode=='error1' else 2 if mode=='error2' else 0) if interior else mode=='error') and row['cancel']==(mode=='cancel') and row['fault_interaction']==(mode=='fault') and
            row['busy_page']==(mode=='busy') and row['free_first']==(private and mode=='free') and row['interval_cleanup_calls']==n*4, 'case/control/cleanup routing differs')
    require((row['page_size'],row['pmd_size'],row['pud_size'])==(PAGE,PMD,PUD) and row['pgdir_size'] in (1<<39,1<<48), 'unsupported architecture geometry')
    growth=PAGE*bool(row['neighbor_body']['old_table'] and not row['neighbor_body']['destination_table']) if neighbor else 0
    require(row['table_bytes_after']==row['table_bytes_before']+growth+PAGE*(mode=='appear' and not empty or shared_missing and row['changing'] or mode=='fault' and not native and not (interior and existing))-PAGE*(mode=='free-table' and not shared), 'unexpected table creation or destruction')
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
            shares=shared or mode=='shared' and selected
            require((start//PMD==(lo+(2 if row['interior_right'] else 0)*PAGE)//PMD if interior else start//PMD==(lo+PAGE)//PMD)==shares, 'edge sharing a survivor table was misclassified')
        adjacent=row['neighbors'][g]
        require(len(adjacent)==2, 'two outer VMA records required')
        for side,entry in enumerate(adjacent):
            expected=lo+(-2 if side==0 else 4)*PAGE
            if mode=='free-table' and selected and side==(row['interior_right'] if interior else bool(target)):expected+=PMD if side else -PMD
            replaced=neighbor and selected and side==row['neighbor_config']['side']
            if replaced:expected+=(-1 if side==0 else 1)*(PMD if row['neighbor_loss'] else PAGE)
            require(entry['address']==entry['start']==expected and entry['end']==expected+PAGE and entry['unchanged']==(not replaced) and
                    not entry['anon'] and not entry['other'] and not entry['pfn'] and
                    entry['zero']==(not neighbor and side==(row['interior_right'] if interior else bool(target)) and (existing and not (mode=='free-table' and selected) or mode=='table' and selected)) and entry['none']==(not entry['zero']), 'retaining neighbor moved, populated or disappeared')
        require(row['anchors'][g]==first*PMD+2*PMD+8*PAGE and row['anchors'][g]//PUD==lo//PUD, 'upper-level anchor geometry differs')
        before=row['walks_before'][g]
        for phase,key in enumerate(('walks_before','walks_after','walks_accessed','walks_written')):
            w=row[key][g];leaf=0
            for p in range(3):
                interval=(lo+p*PAGE)//PMD
                populated=any((lo+q*PAGE)//PMD==interval and
                              (bool((row['masks'][g]|row['zero_masks'][g])&(1<<q)) and (not phase or bool(o['layouts'][q]['mapped'])) if phase<2 else bool(o['layouts'][q]['mapped']))
                              for q in range(3))
                if (not (selected and mode=='free-table' and phase and not shared) if existing else selected and (mode=='table' or phase==0 and mode=='free-table' and not shared_missing or phase>0 and (mode=='appear' or shared_missing and row['changing']))) and interval==(lo+target*PAGE)//PMD:populated=True
                if phase>0 and mode=='fault' and not native and g==1 and interval==(lo+row['late_slot']*PAGE)//PMD:populated=True
                if phase>=2 and any(e['address']//PMD==interval for e in adjacent):populated=True
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
            rf' target_pmd_none={0 if existing else 1} target_owned={1 if private else 0} tables_unchanged=1')
    tag=('KD_MM_BOUNDARY_INTERIOR_ZERO' if zero else 'KD_MM_BOUNDARY_INTERIOR_EMPTY' if empty else 'KD_MM_BOUNDARY_INTERIOR_MISSING') if interior else ('KD_MM_BOUNDARY_SHARED_PRIVATE' if private else 'KD_MM_BOUNDARY_SHARED_EMPTY' if empty else 'KD_MM_BOUNDARY_SHARED_MISSING' if shared_missing else 'KD_MM_BOUNDARY_SHARED_ZERO') if shared else 'KD_MM_BOUNDARY_PRIVATE' if private else 'KD_MM_BOUNDARY_ZERO' if zero else 'KD_MM_BOUNDARY_EMPTY' if empty else 'KD_MM_BOUNDARY'
    tail=r' target_table_pfn=([0-9a-f]+) target_pte_none=1' if existing else ''
    if zero:tail+=r' target_zero=1 zero_pfn=([0-9a-f]+) zero_owned=0'
    if shared and empty:tail+=r' target_zero=0 zero_pfn=0 zero_owned=0'
    if shared_missing:tail=r' target_table_pfn=(0) target_pte_none=0 target_zero=0 zero_pfn=0 zero_owned=0'
    if private:tail+=r' target_pfn=([0-9a-f]+) refs_before=(\d+) refs_after=(\d+) mapcount=0 target_put=1 tlb_complete=1'
    error_tail=tail.replace('target_pte_none=1','target_pte_none=0')+r' zero_ptes_preserved=1' if zero else tail
    if private:error_tail=tail.replace('target_pte_none=1','target_pte_none=0').replace('mapcount=0','mapcount=1').replace('tlb_complete=1','target_preserved=1')
    if shared and (empty or shared_missing):error_tail+=r' zero_ptes_preserved=1'
    if shared:
        fields=r' shared_geometry=1 target_table_mask=(\d+) other_table_mask=(\d+)'
        tail+=fields;error_tail+=fields
        if zero:tail+=r' zero_tlb_complete=1'
        if empty or shared_missing:tail+=r' zero_tlb_complete=0'
    dones=re.findall(tag+' done '+IDENT+suffix+tail,log)
    errors=re.findall(tag+' error '+IDENT+suffix+r' result=-12'+error_tail,log)
    changed_private=[]
    if shared and not interior and ((zero or empty) and mode=='change-private' or shared_missing and mode=='appear-private'):
        # Only the controlled victim may select kdmm19's fully checked class.
        changed_private=re.findall('KD_MM_BOUNDARY_SHARED_PRIVATE done '+IDENT+
            suffix.replace('target_owned=0','target_owned=1').replace('target_pmd_none=1','target_pmd_none=0')+
            r' target_table_pfn=([0-9a-f]+) target_pte_none=1 target_pfn=([0-9a-f]+) refs_before=(\d+) refs_after=(\d+) mapcount=0 target_put=1 tlb_complete=1'+fields,log)
        require(len(changed_private)==(not native), 'changed boundary target was not removed exactly once')
        dones+=changed_private
    changed_zero=[]
    if shared and (not interior or interior_near_zero) and (empty and mode=='change-zero' or shared_missing and mode=='appear-zero'):
        # A changed leaf selects the fully revalidated zero class for this
        # exact geometry. Bind the changed victim and native TLB completion;
        # an edge-only receipt cannot stand in for an interior body.
        changed_zero=re.findall(('KD_MM_BOUNDARY_INTERIOR_ZERO' if interior else 'KD_MM_BOUNDARY_SHARED_ZERO')+' done '+IDENT+suffix.replace('target_pmd_none=1','target_pmd_none=0')+
            r' target_table_pfn=([0-9a-f]+) target_pte_none=1 target_zero=1 zero_pfn=([0-9a-f]+) zero_owned=0'+fields+r' zero_tlb_complete=1',log)
        require(len(changed_zero)==(not native), 'changed zero target was not removed exactly once')
        dones+=changed_zero
    changed_empty=[]
    if shared_missing and mode=='appear-near-zero':
        changed_empty=re.findall('KD_MM_BOUNDARY_SHARED_EMPTY done '+IDENT+
            suffix.replace('target_pmd_none=1','target_pmd_none=0')+
            r' target_table_pfn=([0-9a-f]+) target_pte_none=1 target_zero=0 zero_pfn=0 zero_owned=0'+fields+r' zero_tlb_complete=0',log)
        require(len(changed_empty)==(not native), 'near fault did not select the retained empty-target body exactly once')
        dones+=changed_empty
    queue_done=re.findall('KD_MM_UNMAP done '+IDENT+r' result=0',log)
    queue_errors=re.findall('KD_MM_UNMAP error '+IDENT+r' result=-12',log)
    require(sorted(r[:6] for r in dones)==sorted(queue_done) and sorted(r[:6] for r in errors)==sorted(queue_errors), 'actual boundary body not bound to completion/error')
    origins={str(o['tid']):(g,o) for g,o in enumerate(row['origins'])}
    for r in dones+errors:
        g,o=origins[r[2]];lo,hi=o['old_start'],o['old_end'];start,end=o['start'],o['end']
        changed=r in changed_private
        require(not (changed or r in changed_zero or r in changed_empty) or g==victim, 'changed body executed for an unchanged target')
        w=row['walks_before'][g];survivor=(0 if row['interior_right'] else 2) if interior else 0 if target else 2 if shared else 1
        parent,leaf=int(r[7],16),int(r[8],16);floor,ceiling=int(r[15],16),int(r[16],16)
        require(int(r[6],16)==(hi-1)//PMD*PMD and parent==w['parent_pfn'][0] and
                leaf==w['table_pfn'][survivor] and int(r[9])==(not leaf) and bool(w['pmd_none']&(1<<target))==(not existing), 'body table state differs from verified input')
        appeared=shared_missing and r in changed_private+changed_zero+changed_empty
        if existing or appeared:
            expected_table=row['change_more']['table_after'] if appeared else w['table_pfn'][target]
            require(int(r[17],16)==expected_table==row['walks_after'][g]['table_pfn'][target]>0, 'target table identity lost')
            before_kind='anon' if private else 'zero' if zero else 'none'
            after_kind=before_kind if r in errors else 'none'
            require((row['ptes_before'][g]['none']&(1<<target) if appeared else row['ptes_before'][g][before_kind]&(1<<target)) and row['ptes_after'][g][after_kind]&(1<<target), 'target clear/preservation differs')
            if zero and not changed or r in changed_zero:require(int(r[18],16)>0, 'shared-zero target PFN missing')
            if private or changed:
                page=row['change']['page'][0] if changed else row['pages_before'][g*3+target]
                require(int(r[18],16)==page['pfn']>0 and (changed or page['pfn']==row['ptes_before'][g]['pfn'][target]), 'private target original physical identity differs')
                require(int(r[19])==(2 if row['free_first'] else 3) and int(r[20])==int(r[19])-(r in dones), 'target temporary hold/native mapping release differs')
        body_zero=row['zero_masks'][g] | (2 if shared and mode in ('change-near-zero','appear-near-zero') and g==victim else 0)
        if r in changed_zero:body_zero |= 1<<target
        if changed:body_zero &= ~(1<<target)
        body_mask=row['masks'][g] | ((1<<target) if changed else 0)
        offset=21 if private or changed else 19 if zero or r in changed_zero else 18
        if shared:require(tuple(map(int,r[offset:offset+2]))==((3,4) if (not row['interior_right'] if interior else target==0) else (6,1)), 'shared survivor was assigned to the wrong table')
        require(tuple(map(int,r[10:15]))==(body_mask,body_zero,7^(body_mask|body_zero),body_mask.bit_count(),body_mask.bit_count()), 'body ownership/slot identities differ')
        require(floor==(start if target else row['neighbors'][g][0]['end']) and
                ceiling==(end if interior else row['neighbors'][g][1]['start'] if target else end), 'native post-split retention bounds differ')
        addr=start//PMD*PMD
        if addr<floor:addr+=PMD
        cap=ceiling//PMD*PMD
        finish=end-PMD if end-1>cap-1 else end
        require(cap and addr>finish-1, 'native teardown would walk/free a table')
    if zero:
        require(len({r[18] for r in dones+errors if r not in changed_private})<=1, 'shared-zero physical identities disagree')
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
    elif not existing and not shared_missing:require(not any(row['change_more'].values()), 'unexpected table appearance')
    if existing and not (interior_near_zero and empty and mode=='change-zero' or private and mode in ('change-busy','change-near-zero') or shared and not interior and zero and mode in ('change-private','change-private-busy') or shared and not interior and empty and mode in ('change-zero','change-private','change-private-busy')):validate_empty_controls(row,log,zero=zero,shared=shared,interior=interior)
    require(not zero or mode!='change-zero', 'zero target cannot use empty-to-zero control')
    if mode!='fault':require(not any(row[k] for k in ('late_fault_blocked','late_fault_code','late_fault_value','late_fault_stack')), 'unrecorded fault obscures initial states')
    return dict(ev,remote_boundary_removals=len(dones),remote_boundary_errors=len(errors),remote_boundary_without_private_holds=sum(not row['masks'][origins[r[2]][0]] and r not in changed_private for r in dones),remote_changed_boundary_private_removals=len(changed_private),remote_changed_boundary_zero_removals=len(changed_zero),remote_changed_boundary_empty_removals=len(changed_empty),empty_target_checks=empty,boundary_zero_checks=zero,boundary_private_checks=private,remote_private_boundary_removals=len(dones) if private else 0,remote_private_without_probe_holds=len(dones) if private and row['free_first'] else 0,retention_bounds_verified=True,
                native_target_table_frees=int(mode=='free-table' and not shared),controlled_table_appearance=mode=='appear' or shared_missing and bool(row['changing']),neighbor_preservation=True)


def validate_empty_controls(row,log,*,zero=False,shared=False,interior=False):
    """Boundary-only transitions refuse; same-table support is not inherited."""
    mode,native,target=row['mode'],row['native'],row['slice']
    victim=0 if native else 1
    o=row['origins'][victim];w=row['walks_before'][victim]
    moved=row['retention_change']
    if mode=='free-table':
        address=o['old_start']+(-2 if (not row['interior_right'] if interior else target==0) else 4)*PAGE
        require(moved==dict(before_start=address,before_end=address+PAGE,before_zero=1,
                           table_before=w['table_pfn'][target],table_after=w['table_pfn'][target],before_publication=1)
                and moved['table_before']>0 and (row['walks_after'][victim]['table_pfn'][target]==moved['table_before'] if shared else row['walks_after'][victim]['pmd_none']&(1<<target)),
                'neighbor transition or required native table release unproven')
    else:require(not any(moved.values()), 'unexpected retention prerequisite change')
    if mode=='change-near-private':
        validate_near_private(row,log)
        return
    tag='edge_zero_change' if zero else 'edge_empty_change'
    before=r'before_none=0 before_zero=1' if zero else r'before_none=1'
    transitions=list(re.finditer(r'KD_MM_TEST '+tag+r' mm=([0-9a-f]+) index=(\d+) actor=(\d+) pending=(\d+) readers=(\d+) admission=(-?\d+) mode=(\d+) '+before+r' after_zero=(\d+) after_private=(\d+) table_before=([0-9a-f]+) table_after=([0-9a-f]+) anon_before=0 anon_after=([0-9a-f]+) zero_pfn=([0-9a-f]+) private_pfn=([0-9a-f]+) result=0',log))
    changing=mode in ('change-zero','change-private')
    require(len(transitions)==changing, 'empty target transition missing/duplicate')
    c,m=row['change'],row['change_more']
    if not changing:
        require(not any(m.values()), 'unexpected controlled target state');return
    private=mode=='change-private';r=transitions[0].groups()
    require(c['done']==1 and c['result']==0 and c['before_zero']==zero and c['after_private']==private and
            c['index']==victim*3+target and c['pending']==(0 if native else 2) and c['readers']==(1 if native else 2) and
            (native or c['admission']==-1) and c['actor']>0, 'transition ordering/ownership differs')
    require(m['mode']==(9 if zero else 8 if private else 7) and m['before_none']==(not zero) and m['after_zero']==(not private) and
            m['table_before']==m['table_after']==w['table_pfn'][target]==row['walks_after'][victim]['table_pfn'][target]>0 and
            not m['anon_before'] and bool(m['anon_after'])==private, 'pre-execution table or ancestry identity differs')
    require(int(r[0],16)==row['mm'] and tuple(map(int,r[1:9]))==(c['index'],c['actor'],c['pending'],c['readers'],c['admission'],m['mode'],not private,private) and
            tuple(int(v,16) for v in r[9:13])==(m['table_before'],m['table_after'],m['anon_after'],c['zero_pfn']), 'transition receipt not bound to observed state')
    if private:
        require(len(c['page'])==1 and bool(c['zero_pfn'])==zero, 'private transition test reference missing')
        p=c['page'][0]
        require(p['address']==o['start'] and p['pfn']==int(r[13],16)>0 and p['pfn']!=c['zero_pfn'] and p['maps']==1 and p['refs']==2 and p['hash']>0 and p['charged_same'] and not p['locked'], 'new private-page ownership differs')
    else:require(c['zero_pfn']>0 and not c['page'] and int(r[13],16)==0, 'zero transition acquired private ownership')
    require(c['actor']==o['tid'] if native else all(c['actor']!=origin['tid'] for origin in row['origins']), 'wrong transition executor')
    if not native:
        ack=re.search('KD_MM_UNMAP handback '+IDENT,log)
        require(ack and ack.group(3)==str(o['tid']) and transitions[0].end()<ack.start(), 'populated boundary target did not hand back before effects')


def validate_near_private(row,log):
    """A queued native zero-to-private fault changes only the near survivor."""
    require(row.get('boundary_interior_near_zero_test')==1, 'near conversion family missing')
    victim=0 if row['native'] else 1
    slot=2 if row['interior_right'] else 0
    o=row['origins'][victim];c,m=row['change'],row['change_more']
    transitions=list(re.finditer(r'KD_MM_TEST edge_zero_change ([^\n]+)',log))
    require(len(transitions)==1, 'exact near conversion receipt missing/duplicate')
    fields=dict(re.findall(r'(\w+)=(\S+)',transitions[0].group(1)))
    require(set(fields)==set(('mm','index','actor','pending','readers','admission','mode','before_none',
        'before_zero','after_zero','after_private','table_before','table_after','anon_before','anon_after',
        'zero_pfn','private_pfn','result')), 'unexpected transition fields')
    require(c['done']==1 and c['result']==0 and c['before_zero']==c['after_private']==1 and
        c['index']==victim*3+slot and c['pending']==(0 if row['native'] else 2) and
        c['readers']==(1 if row['native'] else 2) and (row['native'] or c['admission']==-1),
        'near conversion ordering/slot differs')
    require(m['mode']==9 and m['before_none']==m['after_zero']==0 and
        m['table_before']==m['table_after']==row['walks_before'][victim]['table_pfn'][slot]==row['walks_after'][victim]['table_pfn'][slot]>0 and
        m['anon_before']==o['original_anon'] and m['anon_after']>0 and
        (not m['anon_before'] or m['anon_after']==m['anon_before']), 'near conversion table/ancestry differs')
    require(len(c['page'])==1 and c['zero_pfn']>0, 'near conversion private reference missing')
    p=c['page'][0]
    require(p['address']==o['old_start']+slot*PAGE and p['pfn']>0 and p['pfn']!=c['zero_pfn'] and
        p['maps']==1 and p['refs']==2 and p['hash']>0 and p['charged_same'] and not p['locked'],
        'new survivor reference differs')
    expected=dict(mm=row['mm'],index=c['index'],actor=c['actor'],pending=c['pending'],readers=c['readers'],
        admission=c['admission'],mode=9,before_none=0,before_zero=1,after_zero=0,after_private=1,
        table_before=m['table_before'],table_after=m['table_after'],anon_before=m['anon_before'],
        anon_after=m['anon_after'],zero_pfn=c['zero_pfn'],private_pfn=p['pfn'],result=0)
    hexa={'mm','table_before','table_after','anon_before','anon_after','zero_pfn','private_pfn'}
    require({k:int(v,16 if k in hexa else 10) for k,v in fields.items()}==expected,
        'near conversion receipt not bound to exact observed state')
    require(c['actor']>0 and (c['actor']==o['tid'] if row['native'] else all(c['actor']!=x['tid'] for x in row['origins'])),
        'near conversion actor differs')
    if not row['native']:
        ack=re.search('KD_MM_UNMAP handback '+IDENT,log)
        require(ack and ack.group(3)==str(o['tid']) and transitions[0].end()<ack.start(),
            'private near survivor did not hand back before splitting')
