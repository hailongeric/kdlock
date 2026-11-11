#!/usr/bin/env python3
"""Read the completed kernel6 private receipt collection with stdlib only."""
import hashlib
import json
import os
from pathlib import Path
import struct

ROOT = Path('/tmp/kdlock-kernel6-private-complete-collection-01')
FIELDS = ('kind','task','state','origin','node','acquisition','parent','owner','owner_task','object','image','ip','cursor','related','phase','result','flags','source_user','return_user','notifier')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def doc(p): return json.loads(p.read_bytes())
def check(value, why):
    if not value: raise ValueError(why)
def frame(raw, op, nf, nr=0, nb=0):
    abi, actual, size, count = struct.unpack_from('<4Q', raw)
    check((abi,actual,size)==(1,op,len(raw)) and (nr or not count), 'frame header')
    offset=32; fixed=struct.unpack_from('<%dQ'%nf,raw,offset);offset+=nf*8;rows=[];blobs=[]
    for _ in range(count): rows.append(struct.unpack_from('<%dQ'%nr,raw,offset));offset+=nr*8
    for _ in range(nb):
        length,=struct.unpack_from('<Q',raw,offset);offset+=8;check(length<=len(raw)-offset,'blob extent');blobs.append(raw[offset:offset+length]);offset+=length
    check(offset==len(raw),'frame trailing bytes');return fixed,rows,blobs
def text_section(raw):
    h=struct.unpack_from('<16sHHIQQQIHHHHHH',raw)
    check(h[0][:6]==b'\x7fELF\x02\x01' and h[1:3]==(2,62) and h[11]>=64,'image ELF')
    headers=[struct.unpack_from('<IIQQQQIIQQ',raw,h[6]+i*h[11]) for i in range(h[12])]
    shstr=headers[h[13]];names=raw[shstr[4]:shstr[4]+shstr[5]];found=[]
    for s in headers:
        end=names.find(b'\0',s[0]);name=names[s[0]:end]
        if name==b'.text': found.append(raw[s[4]:s[4]+s[5]])
    check(len(found)==1,'exact ELF text section');return found[0]

index=doc(ROOT/'copy-index.json');before=doc(ROOT/'.collection/inventory-before.json');after=doc(ROOT/'.collection/inventory-after.json')
check(before['files']==after['files'] and before['directories']==after['directories'],'collection changed')
check(len(index['files'])==index['count']==900 and index['bytes']==55914019,'collection extent')
for item in index['files']:
    p=ROOT/item['path'];check(p.stat().st_size==item['bytes'] and sha(p)==item['sha256'],'copied file '+item['path'])
    original=before['files'][item['name']]
    check(item['identity']==original['identity'] and item['sha256']==original['sha256'],'copy provenance')

report={'status':'SAVED_RAW_RECEIPTS_AUDIT_COMPLETE','collection_files':900,'collection_bytes':55914019,'families':{},'scope':'Saved-file and archive handling only. No project imports, decoder invocation, helper replay, runtime workload or VM/network action. Full C-function epilogues, general contexts/progress and performance remain outside the private fixtures.'}
for family in ('rwsem','mutex'):
    root=ROOT/'payload'/family;r=doc(root/'result.json');controller=doc(ROOT/'payload'/(family+'-controller')/'result.json')
    raw=(root/'observations-final.bin').read_bytes();abi,words,capacity,count,overflow=struct.unpack_from('<5Q',raw)
    check((abi,words,overflow)==(1,20,0) and capacity==65536 and len(raw)==40+160*count and count==r['observation_records'],'event extent')
    rows=[dict(zip(FIELDS,v),index=i) for i,v in enumerate(struct.iter_unpack('<20Q',raw[40:]))]
    saved=doc(root/'observations-final.json');check(tuple(saved['fields'])==FIELDS and saved['records']==rows,'binary/JSON events')
    proof_rows=[0]
    def validate_embedded(value):
        if isinstance(value,dict):
            if set(FIELDS)<=value.keys() and 'index' in value:
                check(0<=value['index']<len(rows) and all(rows[value['index']][k]==value[k] for k in FIELDS),'embedded event');proof_rows[0]+=1
            for v in value.values(): validate_embedded(v)
        elif isinstance(value,list):
            for v in value: validate_embedded(v)
    validate_embedded(r)
    image=r['warm_image_identity'];lifetimes=[]
    def retire(scope,request):
        grant=next(x for x in scope if x['kind']==6 and x['node']==request['node'] and x['acquisition']==request['acquisition'])
        release,owner=grant['related'],grant['owner'];rel=[x for x in scope if x['related']==release and x['owner']==owner and x['state']==request['state'] and x['acquisition']==request['acquisition']]
        bound=next(x for x in rel if x['kind']==10 and x['source_user']);handled=next(x for x in rel if x['kind']==15 and x['phase']==4)
        begin=next(x for x in scope if x['kind']==18 and x['owner']==owner and x['object']==grant['object'])
        end=next(x for x in scope if x['kind']==19 and x['owner']==owner and x['object']==grant['object'] and x['related']==begin['related'] and x['result']==0)
        drop=next(x for x in rel if x['kind']==16 and x['source_user']==bound['source_user'])
        retired=next(x for x in rel if x['kind']==20 and not (x['source_user'] or x['return_user'] or x['notifier']))
        ready=next(x for x in scope if x['kind']==9 and x['node']==request['node'] and x['acquisition']==request['acquisition'] and x['flags']&13==13 and not x['flags']&16 and not(x['source_user'] or x['return_user'] or x['notifier']))
        free=next(x for x in scope if x['kind']==2 and x['node']==request['node'] and x['acquisition']==request['acquisition'] and x['flags']&2144==2144)
        owner_end=next(x for x in scope if x['kind']==21 and x['owner']==owner)
        check(bound['index']<handled['index']<begin['index']<end['index']<drop['index']<retired['index']<=ready['index']<free['index'] and end['index']<owner_end['index'],'physical/source/final retirement order')
        lifetimes.append({'grant':grant['index'],'release':release,'owner':owner,'physical_end':end['index'],'source_drop':drop['index'],'retired':retired['index'],'ready':ready['index'],'free':free['index']})
    recursive=[];deferred=[];plain_count=0
    plain=r['warm_completion'][0];plain_scope=rows[plain['start']:plain['end']]
    for selection in (x for x in plain_scope if x['kind']==5):
        prepare=max((x for x in plain_scope if x['index']<selection['index'] and x['kind']==22 and x['node']==selection['node']),key=lambda x:x['index'])
        freed=next((x['index'] for x in plain_scope if x['index']>selection['index'] and x['kind']==2 and x['node']==selection['node']),plain_scope[-1]['index'])
        done=next(x for x in plain_scope if prepare['index']<=x['index']<=freed and x['kind']==27 and x['node']==selection['node'] and x['acquisition']==prepare['acquisition'] and x['result']==3)
        episode=[x for x in plain_scope if prepare['index']<=x['index']<=done['index'] and x['state']==done['state'] and x['origin']==done['origin']]
        check(done['flags']&1536==1536 and not any(x['kind']==28 for x in episode) and any(x['kind']==23 and x['image']==image and x['task']!=x['origin'] for x in episode) and all(x['result']==1 and x['image']==image for x in episode if x['kind']==24),'plain positive generated completion')
        plain_count+=1
    check(plain_count>0,'warm plain foreign selection')
    for case in r['cases']:
        if not case.get('name','').startswith('warm-recursive'): continue
        scope=rows[case['start']:case['end']];child,returned,done=case['child_completion'],case['child_return'],case['root_completion']
        expected_child=5 if family=='mutex' and case['mode']==2 else 3
        check(child['result']==returned['result']==expected_child and done['result']==3 and child['state']==returned['state']==done['state']==case['state'],'recursive result/current state')
        check(child['acquisition']!=done['acquisition'] and returned['related']==case['child'] and returned['source_user'] and returned['return_user'] and returned['source_user']!=returned['return_user'],'recursive endpoint identities')
        for completion in (child,done):
            prepare=next(x for x in scope if x['kind']==22 and x['node']==completion['node'] and x['acquisition']==completion['acquisition'])
            episode=[x for x in scope if prepare['index']<=x['index']<=completion['index'] and x['state']==completion['state'] and x['origin']==completion['origin']]
            check(completion['flags']&1536==1536 and not any(x['kind']==28 for x in episode),'positive completion flags/forward')
            check(any(x['kind']==23 and x['image']==image and x['task']!=x['origin'] for x in episode) and all(x['result']==1 and x['image']==image for x in episode if x['kind']==24),'protected generated path')
        for node in (case['root'],case['child']): retire(scope,next(x for x in scope if x['kind']==3 and x['node']==node and x['state']==case['state']))
        if case['mode']==2:
            grant=next(x for x in scope if x['kind']==6 and x['node']==case['root'] and x['state']==case['state'])
            rel=[x for x in scope if x['owner']==grant['owner'] and x['related']==grant['related'] and x['state']==case['state'] and x['acquisition']==grant['acquisition']]
            if family=='mutex':
                requested=next(x for x in rel if x['kind']==11 and x['result']==2 and x['return_user'])
                held=next(x for x in rel if x['kind']==12 and x['notifier']);unwind=next(x for x in rel if x['kind']==13 and x['notifier']==held['notifier'])
                notified=next(x for x in rel if x['kind']==14 and x['notifier']==held['notifier']);returned_user=next(x for x in rel if x['kind']==17 and x['return_user']==requested['return_user'])
                handled=next(x for x in rel if x['kind']==15);final=next(x for x in rel if x['kind']==20)
                check(requested['index']<held['index']<unwind['index']<handled['index'] and notified['index']<final['index'] and returned_user['index']<final['index'],'deferred exact notifier/return closure')
                deferred.append({k:v['index'] for k,v in (('requested',requested),('deferred',held),('unwind',unwind),('notified',notified),('return_drop',returned_user),('retired',final))})
            else:
                requested=next(x for x in rel if x['kind']==11 and x['result']==4 and x['task']!=grant['owner_task'])
                physical=next(x for x in scope if x['kind']==19 and x['owner']==grant['owner'])
                accepted=next(x for x in scope if x['kind']==25 and x['node']==case['child'] and x['phase']==4 and x['result']==9 and x['task']==requested['task'] and x['image']==image)
                check(requested['index']<physical['index']<accepted['index'],'rwsem synchronous outer physical ACK')
        recursive.append({'mode':case['mode'],'child_result':child['result'],'child_done':child['index'],'child_return':returned['index'],'root_done':done['index']})
    credit_lifetimes=0
    for proof in r.get('reader_checks',[]):
        for credit in proof.get('credits',[]):
            opened,released,freed,reserved=(credit[k] for k in ('acquire','release','free','reserve'))
            latest=max((x for x in rows[:opened['index']] if x['kind']==1 and x['state']==opened['state'] and x['acquisition']==opened['acquisition']),key=lambda x:x['index'])
            check(latest==reserved,'latest credit reserve')
            cap=next((x['index'] for x in rows[reserved['index']+1:] if x['kind']==1 and x['owner']==reserved['owner'] and x['related']==reserved['related']),len(rows))
            check(reserved['index']<opened['index']<released['index']<freed['index']<cap and freed['owner']==reserved['owner'] and freed['related']==reserved['related'] and freed['parent']==reserved['parent'] and freed['flags']&2144==2144,'read exact slot lifetime')
            credit_lifetimes+=1
    retained_rows=[]
    if family=='rwsem':
        warm={x['mode']:x for x in r['reader_checks'][-6:]}
        check(set(warm)=={6,7,9,11,12,10} and all(x['fixed_image']==image for x in warm.values()),'reader fixed image')
        check(warm[6]['shared']['release']['index']<warm[6]['accepted']['index']<warm[6]['resumed']['index'],'shared B returns to A')
        for mode in (9,11):
            x=warm[mode]
            check(x['writer_grant']['acquisition']==x['retained']['acquisition']==x['accepted']['acquisition'] and x['writer_grant']['owner']==x['retained']['owner']==x['requested']['owner']==x['physical']['owner'],'retained same grant/physical owner')
            check(x['retained']['index']<x['requested']['index']<x['physical_begin']['index']<x['physical']['index']<x['accepted']['index']<x['forwarded']['index'] and x['competitor']['acquire']['index']>x['physical_begin']['index'],'retained terminal physical ACK')
            retained_rows.append({'mode':mode,**{k:x[k]['index'] for k in ('retained','requested','physical_begin','physical','accepted','forwarded')}})
        check(warm[11]['forwarded']['index']<warm[11]['ancestor_physical']['index'],'ancestor physical duty survives terminal handback')
        x=warm[10];check(x['retained']['index']<x['miss']['index']<x['physical']['index']<x['native_accepted']['index'],'native retained miss up_read ACK')
    source=doc(root/'source-metadata.json');regions=[(x['start'],(root/('source-%d.bin'%i)).read_bytes()) for i,x in enumerate(source['regions'])]
    def source_bytes(ip,length):
        found=[data[ip-start:ip-start+length] for start,data in regions if start<=ip and ip+length<=start+len(data)]
        check(found and len(set(found))==1,'actual source bytes');return found[0]
    version=source['version'].encode();gs=int(r['gs_proof']['current_task_gs_offset'],0)
    def flat(raw):
        a,ia,packet,io,g,e,s,o,n=struct.unpack_from('<9Q',raw);check((a,ia,packet,io,g)==(1,1,168,56,gs),'flat ABI')
        off=72;check(raw[off:off+n]==version,'flat version');off+=n+e*8;sites={}
        for _ in range(s):
            ip,nxt,kind,length=struct.unpack_from('<4Q',raw,off);off+=32;body=raw[off:off+length];off+=length
            check(kind<=2 and nxt==ip+length and body==source_bytes(ip,length) and ip not in sites,'flat source');sites[ip]=(kind,body)
        observations=[struct.unpack_from('<4Q',raw,off+i*32) for i in range(o)];off+=o*32;check(off==len(raw),'flat trailing')
        return sites,observations
    claims={};facts={};candidates={};images={};pubs={};acked=set();settled=set();old=source['old'];epoch=None;last_claim=None;publications=0;cycle=0;nextseq=1
    attempts=sorted((root/'wire').glob('attempt-*'))
    for directory in attempts:
        req=(directory/'request.bin').read_bytes();reply=(directory/'reply.bin').read_bytes();q=doc(directory/'request.json');out=doc(directory/'result.json')
        abi,op,seq,_,inlen,_,capacity,outlen,status=struct.unpack('<9Q',(directory/'returned-envelope.bin').read_bytes())
        check(abi==1 and op==q['operation']==out['operation'] and seq==q['sequence']==out['sequence']==out['returned_sequence'] and inlen==len(req)==q['request_bytes'] and outlen==len(reply)==out['reply_bytes'] and capacity==q['output_capacity'] and outlen<=capacity and status==out['status']==0 and out['completed_response'],'wire actual envelope')
        if op==0: check(seq==0 and struct.unpack('<6Q',reply)==(1,0,0,0,0,0),'initial query');continue
        check(seq==nextseq,'wire sequence');nextseq+=1
        if op==8:
            epoch,_,_,actualgs,_,slot,previous=struct.unpack_from('<7Q',reply,32);check(actualgs==gs and slot==source['slot'] and previous==old and reply==(root/'source-export.bin').read_bytes(),'source export')
        elif op in (1,10):
            fixed,records,blobs=frame(reply,op,3,12,1);check(fixed[2]==epoch and blobs==[version],'claim source')
            claim={}
            for record in records:
                key=record[:2];check(all(key) and key not in claim and (key not in facts or facts[key]==record),'immutable fact');claim[key]=record;facts[key]=record
            claims[fixed[:2]]=claim
            if op==1:
                cycle+=1;check(reply==(root/('cycle-%d'%cycle)/'claim.bin').read_bytes(),'cycle claim')
            else: last_claim=reply
        elif op==2:
            requested,_,_=frame(req,2,5);fixed,_,_=frame(reply,2,12,0,4)
            check(requested[:2] in claims and fixed[1]==requested[3] and fixed[7]==requested[4]==old and fixed[9]==epoch,'build binding');candidates[fixed[0]]={'fixed':fixed,'claim':requested[:2],'cycle':cycle}
        elif op==3:
            fixed,_,blobs=frame(req,3,1,0,5);actual,_,_=frame(reply,3,1);check(actual==fixed,'stage identity');candidate=candidates[fixed[0]];croot=root/('cycle-%d'%candidate['cycle'])
            check(blobs[0]==(croot/'image.S').read_bytes() and blobs[1]==(croot/'metadata.c').read_bytes() and blobs[2]==(croot/'manifest.json').read_bytes() and blobs[3]==(croot/'build/image.bin').read_bytes()==text_section((croot/'build/image.elf').read_bytes()),'five stage blobs and linked text')
            check(len(blobs[3])<=candidate['fixed'][11],'reserved code capacity');candidate['flat']=flat(blobs[4]);images[candidate['fixed'][2]]=candidate
        elif op==4:
            fixed,included,_=frame(req,4,3,2);actual,actualkeys,_=frame(reply,4,14,2);candidate=candidates[fixed[0]];binding=candidate['fixed']
            check(candidate['claim']==fixed[1:] and included==actualkeys and actual[1:3]==fixed[1:] and actual[3]==binding[1] and actual[4]==binding[5] and actual[5]==binding[6] and actual[6]==actual[8]==old and actual[7]==binding[2] and actual[9]==epoch and actual[10]==binding[8] and actual[11]==binding[3] and actual[12]==binding[4] and actual[13]==fixed[0],'actual publication receipt')
            expected=[];emitted={x[:3] for x in candidate['flat'][1] if x[3]==0}
            for key in included:
                fact=claims[fixed[1:]][key];producer=images[fact[3]];site=producer['flat'][0].get(fact[6]);kind=None
                if site:
                    flow,rawsite=site;at=0
                    while at<len(rawsite) and (rawsite[at] in (0x26,0x2e,0x36,0x3e,0x64,0x65,0x66,0x67,0xf0,0xf2,0xf3) or 0x40<=rawsite[at]<=0x4f):at+=1
                    if at+1<len(rawsite) and rawsite[at]==0xff:
                        group=rawsite[at+1]>>3&7
                        if (group,flow) in ((2,0),(4,1)):kind=flow
                eligible=fact[2]==producer['fixed'][4] and fact[4]==3 and fact[5]<=15 and fact[10]==1 and fact[11]==0 and kind is not None and fact[9] in ((1,2) if kind==0 else (4,)) and fact[8]==(fact[6] if fact[9]==1 else fact[7])
                if eligible and (fact[6],fact[7],kind) in emitted:expected.append(key)
            pubs[actual[0]]={'claim':fixed[1:],'expected':expected,'acked':False};old=actual[7];publications+=1
            check(reply==(root/('cycle-%d'%cycle)/'commit.bin').read_bytes(),'cycle commit')
        elif op==5:
            requested,_,_=frame(req,5,1);fixed,keys,_=frame(reply,5,5,2);publication=pubs[requested[0]]
            check(not publication['acked'] and fixed[1]==requested[0] and fixed[2:4]==publication['claim'] and fixed[4]==epoch and keys==publication['expected'] and not acked.intersection(keys),'coverage ACK exact emitted subset');acked.update(keys);publication['acked']=True
            check(reply==(root/('cycle-%d'%cycle)/'ack.bin').read_bytes(),'cycle ACK')
        elif op==6:
            fixed,_,_=frame(req,6,2);actual,_,_=frame(reply,6,2);check(fixed==actual and fixed in claims,'claim end')
        elif op==9:
            fixed,_,_=frame(reply,9,1);check(fixed==(epoch,),'shutdown epoch')
        elif op==11:
            fixed,keys,blobs=frame(req,11,2,2,1);actual,actualkeys,_=frame(reply,11,3,2)
            check(actual[1:]==fixed and keys==actualkeys==list(claims[fixed]) and blobs==[hashlib.sha256((root/'shutdown-archive.json').read_bytes()).digest()] and not acked.intersection(keys),'exact durable archive settlement');settled.update(keys)
        else: raise ValueError('unexpected operation '+str(op))
    archive=doc(root/'shutdown-archive.json')
    check(archive['format']=='kdlock.feedback-archive' and archive['learning_closed'] is True and bytes.fromhex(archive['raw_claim']['bytes_hex'])==last_claim,'archived actual claim')
    check(old==image and all(x['acked'] for x in pubs.values()) and acked|settled==facts.keys() and len(archive['facts'])==len(settled)==r['settled_keys'] and sha(root/'shutdown-archive.json')==r['archive_sha256']==controller['archive_sha256'],'final publication/fact closure')
    check(controller['status']=='COMPLETE' and controller['returncode']==0 and controller['unloaded'] and controller['runner_result_sha256']==sha(root/'result.json') and r['managed_fork_exit']['shutdown_native_holds_drained'],'actual ordinary completion')
    check(controller['after_idle']['devices']==[] and [x.split()[0] for x in controller['after_idle']['modules'].splitlines()]==['nls_iso8859_1'] and controller['after_identity']=={'boot_id':'4400eea1-c8fc-40e1-b6b7-f7a99ecc1364','release':'7.0.0-38-kdrebuild6','taint':12288},'saved poststate')
    report['families'][family]={'controller_sha256':sha(ROOT/'payload'/(family+'-controller')/'result.json'),'runner_sha256':sha(root/'result.json'),'event_count':count,'overflow':overflow,'embedded_event_joins':proof_rows[0],'read_credit_lifetimes':credit_lifetimes,'warm_plain_positive':plain_count,'recursive':recursive,'exclusive_retirement_lifetimes':lifetimes,'deferred_notifier_return_closure':deferred,'reader_retained_downgrade':retained_rows,'wire_attempts':len(attempts),'publications':publications,'covered_acknowledged_keys':len(acked),'archive_settled_keys':len(settled),'unique_retained_facts':len(facts),'archive_sha256':r['archive_sha256'],'warm_claim_empty':r['warm_claim_empty'],'warm_no_new_facts':r['warm_claim_no_new_facts'],'warm_retained_baseline':len(r.get('warm_retained_intentional_keys',[])),'ordinary_unloaded':True,'full_C_function_return':r['full_c_function_jit_return']}

out=Path('/tmp/kdlock-kernel6-private-saved-audit-4400eea1-full.json')
with out.open('x') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
print(json.dumps({'report':str(out),'sha256':sha(out),'families':{k:{f:v[f] for f in ('event_count','wire_attempts','publications','covered_acknowledged_keys','archive_settled_keys')} for k,v in report['families'].items()}},sort_keys=True))
