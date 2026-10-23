#!/usr/bin/env python3
"""Strict mapping, execution and origin-allocation retirement receipts."""
import re


def require(good, message):
    if not good: raise AssertionError(message)


def records(messages, kind):
    return re.findall(r'KD_MM_UNMAP '+kind+r' mm=([0-9a-f]+) id=(\d+) origin=(\d+) executor=(\d+) start=([0-9a-f]+) end=([0-9a-f]+)'+(r' result=0' if kind=='done' else ''), messages)


def validate(row, messages):
    mode=row['mode'];cancel=mode=='cancel';refuse=mode=='refusal'
    require(mode in ('prefix','suffix','middle','cancel','refusal'),'unknown case')
    groups=2 if cancel else 3 if refuse else 16
    require(row['groups']==groups and row['idle']==1 and not row['errors'] and row['checks']>100 and
            row['mm'] and row['gate'] and row['reader_peak']==2 and row['cleanup_calls']==groups*3,'business/reader/cleanup state differs')
    a=row['counts'];b=row['after_cleanup']
    expected=dict(calls=groups,removed=1 if cancel or refuse else 16,delegated=0 if cancel or refuse else 15,
                  native=2 if refuse else 0,post_ban=int(refuse),handbacks=int(refuse),acks=int(refuse),
                  cancelled=int(cancel),refused=int(refuse),failed=0,native_only=int(refuse))
    require(a==expected,'operation balance differs')
    for key in ('removed','delegated','handbacks','acks','cancelled','failed'):
        require(b[key]==a[key],'cleanup changed body/retirement count')
    require(b['calls']==a['calls']+groups*3 and b['native']==a['native']+groups*3 and
            b['native_only']==b['refused']==1 and b['post_ban']==a['post_ban']+groups*3-(not refuse),'cleanup escaped sticky local path')
    removed=1 if cancel else groups
    require(row['pages_before']-row['pages_after']==removed and
            row['maps_after']-row['maps_before']==(removed if row['slice']==1 else 0),'global mapping accounting differs')
    origins={str(o['tid']):o for o in row['origins']}
    if cancel:
        require(row['cancel_result']==[0,-4] and len(set(row['cancel_tid']))==2 and all(row['cancel_tid']),'cancellation changed requested mappings')
        origins={str(t):dict(o,tid=t) for t,o in zip(row['cancel_tid'],row['origins'])}
    require(len(origins)==groups and all(int(t)>0 for t in origins),'origin set differs')
    parsed={k:records(messages,k) for k in ('done','handback','ack')}
    for kind,rows in parsed.items():
        count=expected['delegated' if kind=='done' else 'acks']
        require(len(rows)==len(set(rows))==len({r[1] for r in rows})==count,'missing/duplicate '+kind)
        for mm,ident,origin,executor,start,end in rows:
            o=origins.get(origin,{})
            require(int(mm,16)==row['mm'] and 0<int(ident)<=groups and origin!=executor and executor in origins and
                    int(start,16)==o.get('start') and int(end,16)==o.get('end'),'execution not bound to original mm/range/different task')
    require(sorted(parsed['handback'])==sorted(parsed['ack']),'ACK ownership mismatch')
    body=re.findall(r'KD_MM_PARTIAL done mm=([0-9a-f]+) id=(\d+) origin=(\d+) executor=(\d+) start=([0-9a-f]+) end=([0-9a-f]+) old_start=([0-9a-f]+) old_end=([0-9a-f]+) splits=(\d+) maps_before=(\d+) maps_after=(\d+) pages_before=(\d+) pages_after=(\d+) tables_unchanged=1',messages)
    require(len(body)==len(set(body))==expected['delegated'] and sorted(r[:6] for r in body)==sorted(parsed['done']),'native split/removal completion not paired')
    splits=2 if row['slice']==1 else 1
    for r in body:
        o=origins[r[2]]
        require(int(r[6],16)==o['old_start'] and int(r[7],16)==o['old_end'] and int(r[8])==splits and
                int(r[10])-int(r[9])==splits-1 and int(r[11])-int(r[12])==1,'wrong split boundaries or accounting')
    retired=re.findall(r'KD_MM_SPLIT retire mm=([0-9a-f]+) origin=(\d+) start=([0-9a-f]+) end=([0-9a-f]+) vma0=([0-9a-f]+) vma1=([0-9a-f]+) consumed=(\d+) freed=(\d+)',messages)
    require(len(retired)==len(set(retired))==len({r[1] for r in retired})==(2 if refuse else groups+1),'prepared object retirement missing/duplicate')
    for mm,origin,start,end,v0,v1,used,freed in retired:
        cleanup=origin==str(row['cleanup_tid'])
        o=(dict(start=row['origins'][0]['old_start'],end=row['origins'][0]['old_end']) if cleanup else origins.get(origin,{}))
        require(not cleanup or not refuse,'unexpected repeated cleanup preparation')
        require(int(mm,16)==row['mm'] and o.get('start')==int(start,16) and o.get('end')==int(end,16) and
                int(v0,16)>0 and int(v1,16)>0 and v0!=v1,'allocation retirement lost exact object/origin identity')
        returned=(cancel and origin==str(row['cancel_tid'][1])) or (refuse and origin==str(row['origins'][1]['tid']))
        wanted=0 if returned or cleanup else (3 if splits==2 else 1)
        require(int(used)==wanted and int(freed)==(3^wanted),'resource replay, leak or wrong ownership transfer')
    if not cancel and not refuse:
        require(row['late_fault_blocked']==1 and row['late_fault_code']==1 and
                'kd_mmap_down_read' in row['late_fault_stack'] and 'do_user_addr_fault' in row['late_fault_stack'],'actual blocked hardware fault not proved')
    return dict(remote_partial_removals=expected['delegated'],native_split_receipts=len(body),
                retired_prepared_descriptors=len(retired)*2,matched_acks=expected['acks'],
                cancelled_before_split=int(cancel),concurrent_local_readers=2,
                mapping_and_content_checks=True,cleanup_calls=groups*3,jit_bodies=0)
