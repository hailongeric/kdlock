#!/usr/bin/env python3
"""Real native writer gate, current neighbors and exact completion/retirement."""
from pathlib import Path
import re
import runpy
edge=runpy.run_path(str(Path(__file__).parents[1]/'boundary_edge/receipts.py'))
require,IDENT=edge['require'],edge['IDENT']
PAGE,PMD=4096,2<<20


def validate(row,log):
    empty,zero,private=(bool(row[k]) for k in ('boundary_empty_test','boundary_zero_test','boundary_private_test'))
    missing=not (empty or zero or private)
    result=edge['validate'](row,log,empty=empty,zero=zero,private=private,shared=True,shared_missing=missing,neighbor=True)
    n,native,target=row['groups'],row['native'],row['slice']
    victim=0 if native else 1
    cfg,r=row['neighbor_config'],row['neighbor_body'];o=row['origins'][victim]
    side,loss=cfg['side'],cfg['loss']
    require(side in (0,1) and loss in (0,1) and row['neighbor_loss']==loss and
            row['mode'] in ('success','error','cancel') and not (loss and (row['injection'] or row['cancel'])), 'wrong writer replacement case')
    old=o['old_start']+(-2 if side==0 else 4)*PAGE
    new=old+(-1 if side==0 else 1)*(PMD if loss else PAGE)
    count=0 if native else 2 if loss or row['injection'] or row['cancel'] else 3
    require(cfg==dict(old_address=old,new_address=new,target_start=o['old_start'],target_end=o['old_end'],side=side,loss=loss,count=count,cancel=row['cancel'],offset=target), 'replacement configuration not bound to target')
    require(row['neighbor_old_inaccessible']==1, 'old neighbor restored or removal unverified')
    require(r['armed']==r['queued']==r['released']==r['retired']==r['reader_blocked']==r['writer_blocked']==1 and
            r['pending']==r['close_pending']==count and r['readers']==r['result']==0 and r['admission']==-1,
            'replacement did not hold the native writer through queue publication and old VMA retirement')
    require(r['owner']==r['close_owner']>0 and r['old_vma']>0 and r['new_vma']>0 and r['old_vma']!=r['new_vma'] and
            r['actor']>0 and r['probe_actor']>0 and r['actor']!=r['probe_actor'] and
            all(r['actor']!=p['tid'] for p in row['origins']), 'writer task/VMA identity differs')
    entry=row['neighbors'][victim][side]
    require(r['old_flags']==r['new_flags']==entry['flags'] and r['pgoff']==entry['pgoff']==victim*2+side and
            entry['none']==1 and not any(entry[k] for k in ('zero','anon','other','pfn')), 'native move changed an untouched file-backed neighbor')
    # Same native move_page_tables branch: an existing source leaf allocates a
    # missing destination leaf, even when this particular source PTE is empty.
    expected_old=row['walks_before'][victim]['table_pfn'][0 if not side else 2]
    require(r['old_table']==expected_old, 'old neighbor table disagrees with locked target geometry')
    if not loss:require(r['destination_table']==r['old_table'], 'near relocation changed table interval')
    elif side:require(r['destination_table']>0, 'right far destination shares the existing independent-anchor table')
    else:require(r['destination_table']==0, 'left far destination must be initially missing')
    growth=PAGE*bool(r['old_table'] and not r['destination_table'])
    require(r['tables_before']==row['table_bytes_before'] and r['tables_queued']==r['tables_closed']==r['tables_before']+growth and
            r['maps_queued']==r['maps_before']+1 and r['maps_closed']==r['maps_before'] and r['pages_closed']==r['pages_before'],
            'native replacement leaked or prematurely freed VMA/page-table accounting')
    for key,vmas,maps,faults in [('neighbor_body',2*n,0,0),('neighbor_accessed',2*n,2*n,2*n),('neighbor_clean',0,0,2*n)]:
        snapshot=row[key]
        require({k:v for k,v in snapshot.items() if k not in ('vmas','faults','page_refs','page_maps')}==
                {k:v for k,v in r.items() if k not in ('vmas','faults','page_refs','page_maps')}, 'immutable writer receipt changed after retirement')
        require((snapshot['vmas'],snapshot['page_maps'],snapshot['page_refs'],snapshot['faults'])==(vmas,maps,maps+1,faults),
                'file-backed neighbor page/VMA reference leak or premature population')
    removed=sum(not x['layouts'][target]['mapped'] for x in row['origins'])
    require(row['neighbor_rechecks_accessed']==row['neighbor_rechecks_written']==removed,
            'survivor fault/write did not preserve removed-target inaccessibility')
    queued=list(re.finditer(r'KD_MM_NEIGHBOR queued mm=([0-9a-f]+) actor=(\d+) owner=([0-9a-f]+) old=([0-9a-f]+) new=([0-9a-f]+) old_start=([0-9a-f]+) new_start=([0-9a-f]+) side=(\d+) loss=(\d+) pending=(\d+) readers=(\d+) admission=(-?\d+) tables=(\d+)',log))
    retired=list(re.finditer(r'KD_MM_NEIGHBOR retired mm=([0-9a-f]+) actor=(\d+) owner=([0-9a-f]+) old=([0-9a-f]+) new=([0-9a-f]+) pending=(\d+) readers=0 effects=0 tables=(\d+) maps=(\d+) pages=(\d+)',log))
    require(len(queued)==len(retired)==1 and queued[0].end()<retired[0].start(), 'queued/retirement event missing, duplicated or reordered')
    q=queued[0].groups();t=retired[0].groups()
    require((int(q[0],16),int(q[1]),*[int(x,16) for x in q[2:7]],*map(int,q[7:]))==
            (row['mm'],r['actor'],r['owner'],r['old_vma'],r['new_vma'],old,new,side,loss,count,0,-1,r['tables_queued']), 'publication event identity differs')
    require((int(t[0],16),int(t[1]),*[int(x,16) for x in t[2:5]],*map(int,t[5:]))==
            (row['mm'],r['actor'],r['owner'],r['old_vma'],r['new_vma'],count,r['tables_closed'],r['maps_closed'],r['pages_closed']), 'retirement event identity differs')
    effects=list(re.finditer(r'KD_MM_UNMAP (?:done|error|handback|ack) '+IDENT,log))
    require(all(retired[0].end()<event.start() for event in effects), 'body/handback ran before native writer retired old neighbor')
    if not native and loss:
        handback=re.search('KD_MM_UNMAP handback '+IDENT,log)
        require(handback and handback.group(3)==str(o['tid']) and row['counts']['native_only']==row['counts']['post_ban']==1,
                'current retention loss not handed back with sticky local third call')
    if missing:
        require(row['shape'] in ('prefix-ur','prefix-uz','prefix-uu','suffix-ru','suffix-zu','suffix-uu'), 'missing target table requires untouched near survivor')
    return dict(result,native_writer_gate=True,queued_neighbor_replacement=True,retention_loss=bool(loss),replacement_side=side,
                replacement_before_effects=True,neighbor_page_lifetime=True,table_bytes_added_by_native_mremap=growth)


def compare_native(a,b):
    edge['compare_native'](a,b)
    require(a['neighbor_loss']==b['neighbor_loss'] and a['neighbor_config']['side']==b['neighbor_config']['side'], 'error replacement control differs')


def compare_success(a,b):
    require(a['neighbor_loss']==b['neighbor_loss'] and a['neighbor_config']['side']==b['neighbor_config']['side'], 'replacement control differs')
    return dict(edge['compare_success'](a,b),side=a['neighbor_config']['side'],loss=a['neighbor_loss'])
