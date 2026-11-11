#!/usr/bin/env python3
"""Independent offline K04 event/wire inspection; no project imports or execution."""
from pathlib import Path, PurePosixPath
import hashlib, io, json, os, stat, struct, tarfile
BASE=Path('/tmp/kdlock-kernel8-managed-killable-collection-20261111-04')
P=BASE/'payload/runtime'
OUT=Path('/tmp/kdlock-k04-independent-audit-20261111.json')
sha=lambda b:hashlib.sha256(b).hexdigest()
read=lambda p:p.read_bytes()
load=lambda p:json.loads(read(p))
MASK=(1<<64)-1
FIELDS='kind task state origin node acquisition parent owner owner_task object image ip cursor related phase result flags source_user return_user notifier'.split()
NAMES='SLOT_RESERVE SLOT_FREE ENQUEUE SELECT_LOCAL SELECT_PROXY GRANT PROXY_RETURN QUEUE_DONE NODE_RETIRE_READY RELEASE_BIND RELEASE_REQUEST RELEASE_DEFER RELEASE_UNWIND RELEASE_NOTIFY_DONE RELEASE_HANDLED RELEASE_SOURCE_DROP RELEASE_RETURN_DROP PHYSICAL_BEGIN PHYSICAL_END RELEASE_RETIRE OWNER_RETIRE FRAME_PREPARE JIT_ENTER JIT_EXIT JIT_OPERATION CHILD_RETURN EPISODE_DONE FORWARD NATIVE_UNLOCK OWNER_STOP READ_ACQUIRE READ_RELEASE WRITE_DOWNGRADE_REAL WRITE_DOWNGRADE_RETAINED NATIVE_MODE NATIVE_READ_ACQUIRE NATIVE_READ_RELEASE NATIVE_WRITE_ACQUIRE NATIVE_WRITE_RELEASE NATIVE_DOWNGRADE NATIVE_CANCEL NATIVE_TRY_MISS ACQUIRE_CANCELLED'.split()
K={name:i+1 for i,name in enumerate(NAMES)}
audit={'format':'kdlock.k04-independent-offline-event-wire-audit.v1','scope':'Source-host standard-library byte/hash/tar/event/wire review only; no project imports, tests, builds, live checks or Git mutations.'}
# Independently verify the selected closed collection and its complete transport.
ix=load(BASE/'copy-index.json');cl=load(BASE/'collection.json');assert ix['count']==cl['files']==len(ix['files'])==179 and ix['bytes']==cl['bytes']==2093451 and cl['status']=='COMPLETE'
selected={row['name']:row for row in ix['files']};assert len(selected)==179
actual=set()
for p in (BASE/'payload').rglob('*'):
 if p.is_file():
  assert stat.S_ISREG(p.lstat().st_mode);actual.add(str(p.relative_to(BASE/'payload')))
assert actual==set(selected)
for name,row in selected.items():
 b=read(BASE/row['path']);assert row['path']=='payload/'+name and len(b)==row['bytes'] and sha(b)==row['sha256']
tarbytes=read(BASE/'.collection/copy.tar');seen=set();end=0
with tarfile.open(fileobj=io.BytesIO(tarbytes),mode='r:') as t:
 for m in t.getmembers():
  path=PurePosixPath(m.name);assert m.isfile() and not path.is_absolute() and '..' not in path.parts and m.name not in seen
  seen.add(m.name);b=t.extractfile(m).read();row=selected[m.name];assert len(b)==m.size==row['bytes'] and sha(b)==row['sha256'];end=max(end,m.offset_data+((m.size+511)//512)*512)
assert seen==set(selected) and len(tarbytes)>=end+1024 and not any(tarbytes[end:]) and sha(tarbytes)==cl['archive_sha256']
audit['collection']={'files':179,'bytes':2093451,'copy_index_sha256':sha(read(BASE/'copy-index.json')),'collection_sha256':sha(read(BASE/'collection.json')),'transport_sha256':sha(tarbytes),'regular_unique_exact_members':True}
r=load(P/'result.json');outer=load(BASE/'payload/receipts/result.json')
assert sha(read(P/'result.json'))=='d50378c6e084a41eca1da70e23f9d76b7df80048175e85f6fba6ce57cb7bb062' and r['status']=='managed_killable_mechanism_pass'
assert sha(read(BASE/'payload/receipts/result.json'))=='d7b47fa9e366f666d577b906189e5ca806da2ac769692de380884d89c325f488' and outer['status']=='MANAGED_KILLABLE_COMPLETE'
raw=read(P/'observations-final.bin');head=struct.unpack_from('<5Q',raw);assert head==(1,20,131072,241,0) and len(raw)==38600 and sha(raw)==outer['event_sha256']
events=[dict(zip(FIELDS,struct.unpack_from('<20Q',raw,40+i*160)),index=i) for i in range(241)]
obs=load(P/'observations-final.json');assert obs['fields']==FIELDS and obs['kinds']==K and len(obs['records'])==241
for actual,expected in zip(obs['records'],events):assert actual==expected
matched=0
def visit(x):
 global matched
 if isinstance(x,dict):
  if set(FIELDS+['index'])<=set(x):
   assert 0<=x['index']<241 and all((x[k]&MASK)==events[x['index']][k] for k in FIELDS);matched+=1
  for value in x.values():visit(value)
 elif isinstance(x,list):
  for value in x:visit(value)
visit(r)
scenes={c['name']:c for c in r['cases']}
assert list(scenes)==['ready-before-fatal-cancel','reader-drain-cancel','queued-exit-before-holder-release','learning-0','learning-1','origin-signal-wakes-foreign-c','candidate-cancel-drains-current-w']
assert [c['start'] for c in scenes.values()]==[0,19,31,46,96,146,185] and [c['end'] for c in scenes.values()]==[19,31,46,96,146,185,241]
for c in scenes.values():
 saved=load(P/(c['name']+'.json'));current=json.loads(json.dumps(c))
 if 'native_frontier' in current:current['native_frontier'].pop('fact',None)
 assert saved==current
 s=c['status'];assert all(s[k]==0 for k in ['readers','writer_pending','writer','tail','owner','native_scopes','overflow','cleanup_error']) and s['pool_idle']==1

def find(c,name,**fields):
 return [e for e in events[c['start']:c['end']] if e['kind']==K[name] and all(e[k]==v for k,v in fields.items())]
def one(c,name,**fields):
 found=find(c,name,**fields);assert len(found)==1,(c['name'],name,fields,len(found));return found[0]
def order(*rows):assert all(a['index']<b['index'] for a,b in zip(rows,rows[1:]))
def signed(v):return v-(1<<64) if v>>63 else v
# Match every recorded child, explicit exit ACK and actual waitpid observation.
children={c['pid']:c for c in r['children']};waits={w['pid']:w for w in r['waitpid']};acks={a['pid']:a for a in r['exit_acknowledgments']};before={x['pid']:x for x in r['before_exit_ack']}
assert len(children)==len(waits)==len(acks)==len(before)==19 and set(children)==set(waits)==set(acks)==set(before)
for pid,c in children.items():
 w=waits[pid];a=acks[pid];b=before[pid];assert c['role']==w['role']==a['role']==b['role']
 assert a['returned'] and a['reaped'] and a['returncode']==0 and a['wait_status']==w['wait_status']
 actor=b['status']['roles'][c['role']];assert actor['pid']==pid and actor['done'] and actor['active']==1 and actor['exit_state']==0
 assert w['wait_status'] in (0,9) and b['status']['events']<=w['events_before_observation']<=241
assert sum(x['wait_status']==0 for x in waits.values())==13 and sum(x['wait_status']==9 for x in waits.values())==6
# Every actual successful source grant joins its exact source token, callback and retirement.
retirements=[]
for c in scenes.values():
 for g in find(c,'GRANT'):
  identity={'state':g['state'],'acquisition':g['acquisition'],'related':g['related'],'owner':g['owner']}
  b=one(c,'RELEASE_BIND',**identity);assert b['source_user']
  pb=one(c,'PHYSICAL_BEGIN',owner=g['owner'],owner_task=g['owner_task']);pe=one(c,'PHYSICAL_END',owner=g['owner'],owner_task=g['owner_task'])
  drop=one(c,'RELEASE_SOURCE_DROP',state=g['state'],acquisition=g['acquisition'],related=g['related'],source_user=b['source_user'])
  retired=one(c,'RELEASE_RETIRE',**identity);owner=one(c,'OWNER_RETIRE',owner=g['owner'],owner_task=g['owner_task'])
  ready=one(c,'NODE_RETIRE_READY',node=g['node'],acquisition=g['acquisition']);free=one(c,'SLOT_FREE',node=g['node'],acquisition=g['acquisition'])
  stop=one(c,'OWNER_STOP',owner=g['owner'],owner_task=g['owner_task'])
  order(pb,pe,drop,retired,owner,ready,free);assert stop['index']<owner['index'] and stop['flags']&128
  assert pe['phase']==2 and pe['result']==0 and pb['related']==pe['related'] and retired['phase']==6 and drop['phase']==5
  assert not retired['source_user'] and not retired['return_user'] and not retired['notifier']
  assert free['flags']&(32|64|2048)==(32|64|2048) and not free['flags']&16
  retirements.append({'scene':c['name'],'grant':g,'physical_end':pe,'source_drop':drop,'release_retire':retired,'owner_retire':owner,'node_ready':ready,'slot_free':free})
assert len(retirements)==8
# Canonical typed cancellations must execute no body and acquire no grant.
cancellations=[]
for name,role in [('reader-drain-cancel',3),('queued-exit-before-holder-release',3),('origin-signal-wakes-foreign-c',3),('candidate-cancel-drains-current-w',2)]:
 c=scenes[name];actor=c['status']['roles'][role];ce=one(c,'ACQUIRE_CANCELLED',origin=actor['task']);nr=one(c,'NODE_RETIRE_READY',node=ce['node']);sf=one(c,'SLOT_FREE',node=ce['node'])
 assert actor['result']==-4 and actor['effects']==actor['steps']==0 and ce['state']==actor['state'] and ce['phase']==5 and signed(ce['result'])==-4
 assert not find(c,'GRANT',node=ce['node']) and not find(c,'JIT_ENTER',node=ce['node'])
 order(ce,nr,sf);assert nr['flags']&12==12 and not nr['flags']&18 and nr['source_user']==nr['return_user']==nr['notifier']==0 and sf['flags']&(32|64|2048)==(32|64|2048)
 cancellations.append({'scene':name,'cancelled':ce,'node_ready':nr,'slot_free':sf,'actual_exit':waits[actor['pid']]})
ready=scenes['ready-before-fatal-cancel'];actor=ready['status']['roles'][3];assert actor['result']==0 and actor['effects']==actor['steps']==1 and len(find(ready,'GRANT',origin=actor['task']))==1 and not find(ready,'ACQUIRE_CANCELLED') and waits[actor['pid']]['wait_status']==9
reader=scenes['reader-drain-cancel'];assert reader['held_reader']['readers']==1;readrelease=one(reader,'NATIVE_READ_RELEASE');assert reader['cancelled']['index']<readrelease['index']
# The queue-only caller really exits while its physical predecessor retains its queue node.
q=scenes['queued-exit-before-holder-release'];held=q['holder_before_release'];w=q['status']['roles'][3];exitrow=q['actual_exit'];nr=q['retire_ready'];sf=q['slot_free'];nwr=one(q,'NATIVE_WRITE_RELEASE')
qp=read(P/'queued-exit-before-holder-release.bin');qh=struct.unpack_from('<5Q',qp);assert qh==(1,20,131072,38,0) and qp[40:]==raw[40:40+38*160]
assert exitrow==waits[w['pid']] and exitrow['events_before_observation']==38 and exitrow['wait_status']==9
assert held['events']==38 and held['writer'] and held['native_scopes']==1 and held['pool_idle']==0 and held['roles'][0]['done']==0 and held['roles'][3]['exit_state']==16
assert held['tail']==q['cancelled']['node'] and nr['index']==41 and sf['index']==42 and nwr['index']==38
assert not any(e['kind'] in [K['NODE_RETIRE_READY'],K['SLOT_FREE']] and e['node']==q['cancelled']['node'] for e in events[q['start']:38])
order(q['cancelled'],nwr,nr,sf)
audit['queue_only_exit']={'actual_exit':exitrow,'prefix_events':38,'holder_release':nwr,'node_ready':nr,'slot_free':sf,'storage_retained_after_actual_exit':True,'holder_snapshot':held}
# Foreign C's blocked physical wait is woken by W's cancellation without releasing the reader first.
f=scenes['origin-signal-wakes-foreign-c'];remote=f['registered_foreign_wait'];wa=f['status']['roles'][3];ca=remote['roles'][2]
assert remote['readers']==1 and remote['writer_pending'] and remote['roles'][3]['selection']==3 and remote['roles'][3]['cancel_waiter']==ca['task']
readrelease=one(f,'NATIVE_READ_RELEASE');assert f['actual_exit']==waits[wa['pid']] and f['actual_exit']['events_before_observation']<=readrelease['index']
assert f['slot_free']['index']<readrelease['index'] and wa['result']==-4 and wa['effects']==0
# Candidate C is stopped after handing back W; its borrowed physical callback drains first.
c=scenes['candidate-cancel-drains-current-w'];wg=c['w_grant'];dg=c['d_grant'];ct=c['status']['roles'][2]['task'];wt=c['status']['roles'][3]['task'];dt=c['status']['roles'][4]['task']
assert wg['owner_task']==ct and wg['origin']==wt and ct!=wt and dg['owner_task']==dt!=ct
assert c['status']['roles'][2]['state']!=c['status']['roles'][3]['state'] and c['status']['roles'][2]['regs']!=c['status']['roles'][3]['regs']
stopped=one(c,'OWNER_STOP',owner=wg['owner'],owner_task=ct);pe=one(c,'PHYSICAL_END',owner=wg['owner'],owner_task=ct);nu=one(c,'NATIVE_UNLOCK',node=wg['node'],state=wg['state'],acquisition=wg['acquisition'],task=wt)
assert stopped['flags']&256 and stopped['index']==208 and pe['index']==214 and c['cancelled']['index']==216 and nu['index']==218 and dg['index']==222
assert [e['index'] for e in find(c,'GRANT',owner_task=ct)]==[204] and [e['index'] for e in find(c,'SELECT_PROXY',task=ct)]==[202] and len(find(c,'ENQUEUE',task=ct))==1
order(stopped,pe,c['cancelled'],nu,dg)
group=load(P/'candidate-cancel-drains-current-w-before-exit-ack.json');prefix=read(P/'candidate-cancel-drains-current-w-before-exit-ack.bin');gh=struct.unpack_from('<5Q',prefix)
assert gh==(1,20,131072,232,0) and prefix[40:]==raw[40:40+232*160] and sha(prefix)==group['raw_sha256']
ack=group['w_physical_ack'];order(ack['request'],ack['handled'],ack['begin'],ack['end'],ack['native_unlock']);assert ack['end']==pe and ack['native_unlock']==nu
for role in (2,3,4):
 a=group['status']['roles'][role];assert a['active'] and a['done'] and not a['exit_state'] and a['pid']==c['status']['roles'][role]['pid']
 assert before[a['pid']]['status']==group['status'] and waits[a['pid']]['events_before_observation']==241
assert group['status']['roles'][2]['admission']==2 and group['status']['roles'][2]['result']==-4
assert group['status']['roles'][2]['effects']==0 and group['status']['roles'][4]['effects']==1
assert c['slot_free']['index']==235 and c['native_frontier']['slot_free']['index']==236
visit(group)
audit['cancel_current_borrow']={'no_additional_C_borrowers':True,'C_enqueue_count':1,'C_grant_indices':[204],'C_proxy_selection_indices':[202],'stop':stopped,'W_callback_end':pe,'C_cancelled':c['cancelled'],'W_native_unlock_ack':nu,'D_local_grant':dg,'C_slot_free':c['slot_free'],'W_slot_free':c['native_frontier']['slot_free'],'before_exit_ack_events':232,'all_three_actual_exits_after_events':241,'ordering_limit':'The ACQUIRE_CANCELLED event is after W physical callback completion but before W source NATIVE_UNLOCK acknowledgment; retained storage retirement follows. No stronger total order is claimed.'}
# Decode SOURCE8 bytes and check the exact first-unexecuted CALL handback and once-only source counters.
src=read(P/'source-export.bin');abi,op,total,count=struct.unpack_from('<4Q',src);assert abi==1 and op==8 and total==len(src)
fixed=struct.unpack_from('<7Q',src,32);at=88;regions=[]
for _ in range(count):
 start,n=struct.unpack_from('<2Q',src,at);at+=16;data=src[at:at+n];at+=n;regions.append((start,data))
at+=fixed[4]*16;n=struct.unpack_from('<Q',src,at)[0];at+=8;version=src[at:at+n];at+=n;assert at==len(src)
frontiers=[]
for f in r['native_frontiers']:
 c=scenes[f['name']];g=f['grant'];identity={key:g[key] for key in ['node','state','acquisition','origin']}
 for key,kind in [('reserve','SLOT_RESERVE'),('frame','FRAME_PREPARE'),('enter','JIT_ENTER'),('exit','JIT_EXIT'),('forward','FORWARD'),('slot_free','SLOT_FREE')]:assert f[key]==one(c,kind,**identity)
 assert f['frame']['parent']==f['enter']['parent']==f['exit']['parent']==f['forward']['parent']==0
 assert f['frame']['image']==f['enter']['image']==f['exit']['image']==f['forward']['image']==r['fixed_image']
 order(f['reserve'],f['frame'],g,f['enter'],f['exit'],f['forward'],f['slot_free'])
 call=f['call'];site=call['site'];target=c['status']['native_helper'];assert call=={'indirect':True,'length':5,'raw_hex':'2e2e2effd0','site':0xffffffffc000b4e6,'target':None}
 assert [data[site-start:site-start+5] for start,data in regions if start<=site<start+len(data)]==[bytes.fromhex(call['raw_hex'])]
 assert not any(start<=target<start+len(data) for start,data in regions)
 ex=f['exit'];fw=f['forward'];assert (ex['result'],ex['flags'],ex['phase'],ex['ip'],ex['cursor'],ex['related'])==(3,10,1,site,site,target)
 assert (fw['result'],fw['flags'],fw['phase'],fw['ip'],fw['cursor'],fw['related'])==(0,3,1,site,site,target)
 actor=c['status']['roles'][3];assert actor['effects']==actor['steps']==actor['helper_entered']==actor['helper_returned']==1 and actor['result']==0 and actor['seen_task']==actor['task'] and actor['helper_return_ip']==site+5
 assert actor['state']==g['state'] and g['origin']==actor['task']!=g['owner_task'] and f['enter']['task']==g['owner_task']
 assert not any(e['kind']==K['SLOT_RESERVE'] and e['owner']==f['reserve']['owner'] and e['related']==f['reserve']['related'] for e in events[f['reserve']['index']+1:f['slot_free']['index']+1])
 frontiers.append(f)
assert len(frontiers)==2 and frontiers[0]['slot_free']['index']==145<frontiers[1]['reserve']['index']==191 and frontiers[0]['reserve']['task']!=frontiers[1]['reserve']['task']
audit['native_frontiers']={'episodes':frontiers,'distinct_nonoverlapping_root_lifetimes':True,'source_version_sha256':sha(version),'source_call_bytes_hex':'2e2e2effd0','first_unexecuted_source_ip':0xffffffffc000b4e6,'native_return_word':0xffffffffc000b4eb,'source_and_helper_counters_once_each':True}
# Exact claim and shutdown records retain both distinct, unACKed native-frontier keys.
def framed(b,operation,fixed,words,blobs=0):
 abi,op,total,count=struct.unpack_from('<4Q',b);assert abi==1 and op==operation and total==len(b)
 at=32;fs=struct.unpack_from('<'+str(fixed)+'Q',b,at);at+=8*fixed;rows=[]
 for _ in range(count):rows.append(struct.unpack_from('<'+str(words)+'Q',b,at));at+=8*words
 data=[]
 for _ in range(blobs):
  n=struct.unpack_from('<Q',b,at)[0];at+=8;data.append(b[at:at+n]);at+=n
 assert at==len(b);return fs,rows,data
c3,rows3,versions3=framed(read(P/'cycle-3/claim.bin'),1,3,12,1);c4,rows4,versions4=framed(read(P/'cycle-4/claim.bin'),1,3,12,1)
assert len(rows3)==1 and len(rows4)==2 and rows3[0]==rows4[0] and rows4[0][2:]==rows4[1][2:] and rows4[0][:2]!=rows4[1][:2]
assert c3[2]==c4[2]==fixed[0] and versions3==versions4==[version] and version.decode()==r['source_version']
keys=[list(row[:2]) for row in rows4]
assert rows4[0][3]==r['fixed_image'] and rows4[0][4:]==(3,10,0xffffffffc000b4e6,0xffffffffc000b300,0xffffffffc000b4e6,1,0,0)
wire=[];ackkeys=[]
for p in sorted((P/'wire').glob('*/returned-envelope.bin')):
 b=read(p);w=struct.unpack('<9Q',b);reply=read(p.with_name('reply.bin'));assert w[0]==1 and w[7]==len(reply) and w[8]==0
 wire.append({'attempt':p.parent.name,'operation':w[1],'sequence':w[2],'status':w[8]})
 if w[1]==5:
  _,rows,_=framed(reply,5,5,2);ackkeys.extend([list(row) for row in rows])
assert len(wire)==22 and [x['operation'] for x in wire[14:18]]==[1,6,1,6] and [(x['operation'],x['sequence']) for x in wire[-4:]]==[(9,18),(10,19),(11,20),(6,21)]
assert len(ackkeys)==1 and all(key not in ackkeys for key in keys)
archivebytes=read(P/'shutdown-archive.json');archive=json.loads(archivebytes);assert sha(archivebytes)==r['archive_sha256']==outer['archive_sha256']=='fc2220a597868184cb5731251f8a33b7869f6c541bbb6c7f0802846440782d1e'
claimbytes=bytes.fromhex(archive['raw_claim']['bytes_hex']);afs,arows,aversions=framed(claimbytes,10,3,12,1)
assert arows==rows4 and aversions==[version] and afs[2]==c4[2] and claimbytes==read(P/'wire/attempt-00000020/reply.bin')
reqfs,reqkeys,digests=framed(read(P/'wire/attempt-00000021/request.bin'),11,2,2,1);sfs,settled,_=framed(read(P/'wire/attempt-00000021/reply.bin'),11,3,2)
assert [list(row) for row in reqkeys]==[list(row) for row in settled]==keys and digests==[hashlib.sha256(archivebytes).digest()] and reqfs==afs[:2]
assert len(archive['facts'])==2
pending=[]
for state in archive['facts']:
 fact=state['fact'];key=[int.from_bytes(bytes.fromhex(fact['record_identity']['bytes_hex']),'little'),fact['incarnation']]
 if key in keys:assert not state['acknowledgment_identities'];pending.append(key)
assert sorted(pending)==sorted(keys)
assert r['pending_before_shutdown']==r['settled_keys']==2 and not r['fixed_claim_no_new_facts'] and r['fixed_claim_no_new_ordinary_learning'] and r['fixed_claim_only_expected_native_frontiers'] and not r['fixed_claim_published'] and r['fixed_image_unchanged'] and r['fixed_snapshot_unchanged']
assert [x['published'] for x in r['cycles']]==[True,True,False,False] and [x['acknowledged'] for x in r['cycles']]==[0,1,0,0] and len({x['image'] for x in r['cycles'][1:]})==1
assert sum(not f['acknowledged'] for f in r['facts'])==2
audit['pending_native_frontier_facts']={'epoch':c4[2],'keys':keys,'claim3_sha256':sha(read(P/'cycle-3/claim.bin')),'claim4_sha256':sha(read(P/'cycle-4/claim.bin')),'all_other_ten_scalar_words_identical':True,'literal_no_new_facts':False,'new_ordinary_learning':False,'new_publication_during_fixed_checks':False,'archive_sha256':sha(archivebytes),'archive_bytes':len(archivebytes),'settled_keys':keys,'pending_keys_received_no_coverage_ack':True,'actual_other_coverage_ack_keys':ackkeys,'shutdown_wire':wire[-4:]}
# Final ordinary lifecycle completion and unchanged boot; limits stay explicit.
final=r['final'];assert all(final[k]==0 for k in ['binding_live','cleanup_error','native_scopes','owner','readers','runtime_live','self_held','setup_complete','setup_error','source_live','tail','trace_live','writer','writer_pending','overflow']) and final['pool_idle']==final['retired']==1
assert all(all(v==(-1 if k in ('admission','selection') else 0) for k,v in role.items()) for role in final['roles'])
assert outer['identity_before']==outer['identity_after']=={'activity':[],'identity':{'boot':'e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0','release':'7.0.0-38-kdrebuild8','taint':4096},'modules':'nls_iso8859_1 12288 1 - Live 0xffffffffc000a000\n'}
assert len(outer['commands'])==1 and outer['commands'][0]['returncode']==0 and load(BASE/'payload/driver/return.json')['returncode']==0
assert outer['source_git_head']=='5c14b483ca16b3bba8f3dd40a00f16a6efefc12c' and outer['compiled_module_source_git_head']=='140aecc4f83a6b6ae6f20245234e8a63504f9210' and outer['module_sha256']==r['module_sha256']=='74bec2fad7f75b1e5ea4d5ffbd4a4d699d99f3ca2413145ef4801479498e36b8'
assert outer['kernel_core_git_head']=='0d42063ead37dc8fc1631fa56c8348890ede9c5f' and outer['host_checks_sha256']=='3fc26667154f5232125e0e02ea40e11084a39fd475e5a44367d30514bc7d2de0'
runner=read(Path('/home/eric/vm/vm-shared/kdlock-main/tests/kernel/rwsem_killable/runner.py'));helper=read(Path('/home/eric/vm/vm-shared/kdlock-main/tests/kernel/run_runtime_fixture.py'))
assert sha(runner)=='b8aaa909ac8aba2db51de0dc10267480e53811fd850aeacc621a3677a30924e6' and b'command([tools["rmmod"], NAME], args.deadline)' in runner and b'if result.returncode:' in helper
assert r['mm_jit']=='not_exercised' and r['full_c_function_jit_return']=='outside_protected_scope'
audit['scene_summary']=[{'name':c['name'],'start':c['start'],'end':c['end'],'status_gates_clear':True} for c in scenes.values()]
audit['actual_child_exits']={'total':19,'normal':13,'SIGKILL':6,'rows':r['waitpid'],'all_explicit_exit_acks_returned_and_reaped':True}
audit['canonical_cancellations']=cancellations
audit['successful_grant_retirements']=retirements
audit['raw_event_dictionary_comparisons']=matched
audit['raw_event_header']=list(head)
audit['final']={'inner_result_sha256':sha(read(P/'result.json')),'outer_result_sha256':sha(read(BASE/'payload/receipts/result.json')),'status':r['status'],'gates_and_exact_lifetime_probes_clear':True,'ordinary_RETIRE_completed':True,'ordinary_rmmod_completed':'Runner success follows its checked subprocess rmmod and final outer idle module list contains only NLS. No separate fabricated rmmod receipt is asserted.','identity':outer['identity_after'],'module_sha256':r['module_sha256'],'source_git_head':outer['source_git_head'],'runner_source_sha256':sha(runner),'checked_command_helper_sha256':sha(helper),'limits':['private root mechanism only','no general nested cancellation proof','no real MM JIT','no full C epilogue JIT return','no native-context expansion','no performance claim']}
assert not OUT.exists();OUT.write_text(json.dumps(audit,indent=2,sort_keys=True)+'\n')
print(json.dumps({'audit':str(OUT),'bytes':OUT.stat().st_size,'sha256':sha(read(OUT)),'script_sha256':sha(read(Path(__file__))),'event_dictionary_matches':matched,'actual_exits':19,'normal':13,'SIGKILL':6,'successful_grants_retired':len(retirements),'pending_keys':keys},indent=2))
