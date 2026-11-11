#!/usr/bin/env python3
"""Copy closed K03 receipts and audit bytes using only the Python standard library."""
from pathlib import Path, PurePosixPath
import gzip, hashlib, io, json, os, stat, struct, tarfile

DRAFT=Path('/tmp/kdlock-kernel8-killable-claim-recovery-draft-20261111-02')
F=Path('/tmp/kdlock-kernel8-managed-killable-failure-collection-20261111-03')
R=Path('/tmp/kdlock-kernel8-killable-final-recovery-collection-20261111-01')
OLD=Path('/tmp/kdlock-kernel8-fixture-source-6a4ba5a1-01')
NEW=Path('/tmp/kdlock-kernel8-fixture-source-5c14b483-01')
U64=(1<<64)-1
sha=lambda b:hashlib.sha256(b).hexdigest()
load=lambda p:json.loads(p.read_bytes())
files=[]
origins={}

def dump(p,d):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')

def identity(p):
 s=p.lstat();assert stat.S_ISREG(s.st_mode),str(p)
 return [s.st_dev,s.st_ino,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]

def read(p):
 a=identity(p);b=p.read_bytes();assert a==identity(p) and len(b)==a[4],str(p)
 origins[str(p)]=(a,sha(b));return b

def source_members(root):
 entries=[]
 for p in sorted(root.rglob('*')):
  s=p.lstat();assert not stat.S_ISLNK(s.st_mode),str(p)
  if stat.S_ISREG(s.st_mode):entries.append(p)
  else:assert stat.S_ISDIR(s.st_mode),str(p)
 return entries

def copy(p,rel):
 b=read(p);stored=b;encoding='identity'
 if len(b)>=65536 and p.suffix not in ('.o','.elf'):
  stored=gzip.compress(b,compresslevel=9,mtime=0);rel+='.gz';encoding='gzip'
  assert gzip.decompress(stored)==b
 q=DRAFT/rel;assert not q.exists(),str(q);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(stored)
 assert q.read_bytes()==stored
 files.append({'source':str(p),'source_identity':origins[str(p)][0], 'raw_bytes':len(b),'raw_sha256':sha(b),'path':rel,'encoding':encoding,'stored_bytes':len(stored),'stored_sha256':sha(stored)})

def copy_tree(root,rel):
 entries=source_members(root)
 for p in entries:copy(p,rel+'/'+str(p.relative_to(root)))
 return {'source':str(root),'files':len(entries),'bytes':sum(identity(p)[4] for p in entries)}

def tar_audit(p,expected):
 b=read(p);rows=[];seen=set();end=0
 with tarfile.open(fileobj=io.BytesIO(b),mode='r:') as t:
  for m in t.getmembers():
   path=PurePosixPath(m.name)
   assert m.isfile() and not path.is_absolute() and '..' not in path.parts and '\\' not in m.name and m.name not in seen,m.name
   seen.add(m.name);data=t.extractfile(m).read();assert len(data)==m.size
   assert m.name in expected and (len(data),sha(data))==(expected[m.name]['bytes'],expected[m.name]['sha256']),m.name
   rows.append({'name':m.name,'bytes':m.size,'sha256':sha(data)})
   end=max(end,m.offset_data+((m.size+511)//512)*512)
 assert seen==set(expected) and len(b)>=end+1024 and not any(b[end:])
 return {'source':str(p),'bytes':len(b),'sha256':sha(b),'members':rows,'regular_unique_exact_members':True,'zero_trailing_padding':True}

def collection(root,count,byte_count):
 ix=load(root/'copy-index.json');cl=load(root/'collection.json')
 assert ix['count']==count==len(ix['files']) and ix['bytes']==byte_count==sum(x['bytes'] for x in ix['files'])
 assert cl['status']=='COMPLETE' and cl['files']==count and cl['bytes']==byte_count
 expected={x['name']:{'bytes':x['bytes'],'sha256':x['sha256']} for x in ix['files']};assert len(expected)==count
 actual={str(p.relative_to(root/'payload')) for p in source_members(root/'payload')};assert actual==set(expected)
 for x in ix['files']:
  assert x['path']=='payload/'+x['name'];b=read(root/x['path']);assert (len(b),sha(b))==(x['bytes'],x['sha256'])
 ta=tar_audit(root/'.collection/copy.tar',expected);assert ta['sha256']==cl['archive_sha256']
 return {'source':str(root),'payload_files':count,'payload_bytes':byte_count,'copy_index_sha256':sha(read(root/'copy-index.json')),'collection_sha256':sha(read(root/'collection.json')),'transport':ta}

def framed(b,operation,fixed,words,blobs=0):
 abi,op,total,count=struct.unpack_from('<4Q',b);assert abi==1 and op==operation and total==len(b)
 at=32;fs=struct.unpack_from('<'+str(fixed)+'Q',b,at);at+=8*fixed
 rows=[]
 for _ in range(count):rows.append(struct.unpack_from('<'+str(words)+'Q',b,at));at+=8*words
 data=[]
 for _ in range(blobs):
  n=struct.unpack_from('<Q',b,at)[0];at+=8;data.append(b[at:at+n]);at+=n
 assert at==len(b)
 return fs,rows,data

def claim(b,op=1):
 fs,rows,blobs=framed(b,op,3,12,1)
 return {'claim_identity':fs[0],'holder_identity':fs[1],'epoch':fs[2],'rows':[list(r) for r in rows],'version':blobs[0].decode(),'version_sha256':sha(blobs[0])}

assert not DRAFT.exists();DRAFT.mkdir()
audit={'format':'kdlock.k03-closed-byte-audit.v1','scope':'Offline standard-library byte, hash, tar, event and wire inspection only. No project import, test, build or VM operation.'}
audit['collections']=[collection(F,156,1691973),collection(R,40,3808106)]
fr=load(F/'payload/runtime/result.json');outer=load(F/'payload/controller/result.json');rr=load(R/'payload/runtime/result.json');proof=load(R/'payload/runtime/restored-producer-proof.json')
assert fr['status']=='failed_retained' and outer['status']=='INCOMPLETE_CHILD_RETAINED'
assert sha(read(F/'payload/runtime/result.json'))=='56dcf7cfa9e75645d0ab56cb61809550639119ee0701db84af05c34da302005a'
assert sha(read(F/'payload/controller/result.json'))=='fc1375e0653d88fec37b72242da86408151293034028fa7170e099c5bc873c62'
assert fr['error']=="AssertionError('fixed-image checks added an unlearned fact or replaced the image')"
assert fr['live_children']=={} and len(fr['children'])==len(fr['waitpid'])==len(fr['exit_acknowledgments'])==19
assert {x['pid'] for x in fr['children']}=={x['pid'] for x in fr['waitpid']}=={x['pid'] for x in fr['exit_acknowledgments']}
assert all(x['reaped'] and x['returned'] for x in fr['exit_acknowledgments'])
names=[x['name'] for x in fr['cases']];assert len(names)==7 and names==['ready-before-fatal-cancel','reader-drain-cancel','queued-exit-before-holder-release','learning-0','learning-1','origin-signal-wakes-foreign-c','candidate-cancel-drains-current-w']
for c in fr['cases']:
 s=c['status'];assert s['overflow']==s['owner']==s['tail']==s['readers']==s['writer']==s['writer_pending']==s['native_scopes']==s['cleanup_error']==0 and s['pool_idle']==1
# Completed scene receipts retain role fields until reset; retirement is checked below.
# Verify every full event dictionary in retained result JSON against raw event words.
e=read(F/'payload/runtime/observations-failure.bin');eh=struct.unpack_from('<5Q',e);assert eh==(1,20,131072,241,0) and len(e)==40+241*160
fields='kind task state origin node acquisition parent owner owner_task object image ip cursor related phase result flags source_user return_user notifier'.split()
events=[dict(zip(fields,struct.unpack_from('<20Q',e,40+i*160)),index=i) for i in range(241)]
matched=[0]
def visit(x):
 if isinstance(x,dict):
  if set(fields+['index'])<=x.keys():
   i=x['index'];assert 0<=i<len(events)
   assert all((x[k]&U64)==events[i][k] for k in fields);matched[0]+=1
  for v in x.values():visit(v)
 elif isinstance(x,list):
  for v in x:visit(v)
visit(fr)
root_chains=[]
for indices in [(102,103,112,113,114,115),(191,192,204,205,206,207)]:
 chain=[events[i] for i in indices];assert [x['kind'] for x in chain]==[1,22,6,23,24,28]
 for k in ['state','origin','node','acquisition']:
  assert len({x[k] for x in chain})==1
 assert chain[1]['parent']==chain[2]['parent']==chain[3]['parent']==chain[4]['parent']==chain[5]['parent']==0
 assert chain[1]['image']==chain[3]['image']==chain[4]['image']==chain[5]['image']==fr['fixed_image']
 assert chain[2]['task']==chain[3]['task']==chain[4]['task']==chain[5]['task']!=chain[0]['origin']
 assert chain[4]['ip']==chain[4]['cursor']==chain[5]['ip']==chain[5]['cursor']==0xffffffffc000b4e6
 assert chain[4]['related']==chain[5]['related']==0xffffffffc000b300
 assert (chain[4]['result'],chain[4]['flags'],chain[4]['phase'])==(3,10,1)
 root_chains.append(chain)
assert any(x['kind']==2 and x['node']==events[102]['node'] for x in events[116:191])
audit['failure']={'runtime_sha256':sha(read(F/'payload/runtime/result.json')),'outer_sha256':sha(read(F/'payload/controller/result.json')),'status':fr['status'],'outer_status':outer['status'],'error':fr['error'],'scenes':names,'children_reaped':19,'event_header':list(eh),'event_dictionary_matches':matched[0],'root_chains':root_chains,'cycles':fr['cycles'],'original_verdict_preserved':True}
# Retain exact fact keys; do not deduplicate equal exit scalar tuples.
c3=claim(read(F/'payload/runtime/cycle-3/claim.bin'));c4=claim(read(F/'payload/runtime/cycle-4/claim.bin'))
keys=[[0xff110003bf8001d4,1],[0xff110003bf8002c4,1]]
assert [r[:2] for r in c3['rows']]==keys[:1] and [r[:2] for r in c4['rows']]==keys and c4['rows'][0]==c3['rows'][0]
assert c4['rows'][0][2:]==c4['rows'][1][2:]==[0xff110003f538fc00,0xff110003f538fd38,3,10,0xffffffffc000b4e6,0xffffffffc000b300,0xffffffffc000b4e6,1,0,0]
assert c3['epoch']==c4['epoch']==0xff11000346654b40 and c3['version']==c4['version'] and c4['version_sha256']=='2ceb6ee5cfb0ef1c5ce8c1358b6fe270dcda07a634e5265f8deb92a8ec3ce291'
audit['claims']={'cycle_3':c3,'cycle_4':c4,'literal_no_new_facts':False,'identical_exit_scalar_words':10,'distinct_pending_keys':keys,'coverage_acknowledged_during_original_cycles':sum(x['acknowledged'] for x in fr['cycles'])}
# SOURCE8 preserves provider order; inspect reached CALL bytes without disassembly execution.
src=read(F/'payload/runtime/source-export.bin');abi,op,total,count=struct.unpack_from('<4Q',src);assert abi==1 and op==8 and total==len(src)
fixed=struct.unpack_from('<7Q',src,32);at=88;regions=[]
for _ in range(count):
 start,n=struct.unpack_from('<2Q',src,at);at+=16;code=src[at:at+n];at+=n;assert len(code)==n;regions.append((start,code))
at+=fixed[4]*16;n=struct.unpack_from('<Q',src,at)[0];at+=8;version=src[at:at+n];at+=n;assert at==len(src) and version.decode()==c4['version']
site=0xffffffffc000b4e6;target=0xffffffffc000b300
reached=[code[site-start:site-start+5] for start,code in regions if start<=site<start+len(code)]
assert reached==[bytes.fromhex('2e2e2effd0')] and not any(start<=target<start+len(code) for start,code in regions)
audit['native_frontier']={'source_ip':site,'cursor':site,'target':target,'call_bytes_hex':reached[0].hex(),'next_instruction':site+5,'target_outside_all_exported_regions':True,'kind':3,'detail':10,'phase':1,'classification':0,'entry_result':0,'labels':['COVERAGE_MISS','UNRESOLVED_TARGET','TARGET_READY','UNCLASSIFIED'],'source_provider_regions':[{'start':start,'bytes':len(code),'sha256':sha(code)} for start,code in regions]}
# Verify all recorded envelopes and raw protocol payloads, including cached END17 query.
wire=[]
for tag,root in [('failure',F),('recovery',R)]:
 rows=[]
 for p in sorted((root/'payload/runtime/wire').glob('*/returned-envelope.bin')):
  b=read(p);assert len(b)==72;w=struct.unpack('<9Q',b);reply=read(p.with_name('reply.bin'));request=read(p.with_name('request.bin'))
  assert w[0]==1 and w[7]==len(reply) and w[8]==0
  rows.append({'attempt':p.parent.name,'operation':w[1],'sequence':w[2],'status':w[8],'request_bytes':len(request),'reply_bytes':len(reply)})
 wire.append({'collection':tag,'rows':rows})
assert len(wire[0]['rows'])==18 and len(wire[1]['rows'])==5
assert [(x['operation'],x['sequence'],x['status']) for x in wire[1]['rows']]==[(0,0,0),(9,18,0),(10,19,0),(11,20,0),(6,21,0)]
q=read(R/'payload/runtime/wire/attempt-00000001/reply.bin');assert struct.unpack_from('<6Q',q)==(1,6,17,0,48,48)
assert q[48:96]==read(F/'payload/runtime/wire/attempt-00000018/request.bin') and q[96:]==read(F/'payload/runtime/wire/attempt-00000018/reply.bin')
audit['wire']=wire
# Compare retained producer stage blobs, metadata, machine bytes and exact fact keys.
assert rr['status']=='ORDINARY_CLEANUP_COMPLETE' and rr['original_failure_preserved'] and proof==rr['restored_producer']
assert sha(read(R/'payload/runtime/result.json'))=='40872340905c520739493208ba84323e3f16b6aed40e7119cefc08bf8f5fd1f0'
assert proof['retained_unacknowledged_keys']==keys and proof['actual_coverage_acknowledged_keys']==1 and proof['actual_last_end_sequence']==17
for cycle in [1,2]:
 p=F/'payload/runtime'/('cycle-'+str(cycle));st=F/'payload/runtime/wire'/('attempt-'+str(5 if cycle==1 else 11).zfill(8))/'request.bin'
 fs,rows,blobs=framed(read(st),3,1,0,5);a,m,mf,machine,flat=blobs
 for b,name,key in [(a,'image.S','assembly_sha256'),(m,'metadata.c','metadata_sha256'),(mf,'manifest.json','manifest_sha256'),(machine,'build/image.bin','machine_sha256')]:
  assert b==read(p/name) and sha(b)==proof['cycles'][cycle-1][key]
 assert sha(flat)==proof['cycles'][cycle-1]['flat_sha256']
 # ELF64 section headers give the independently retained .text bytes.
 elf=read(p/'build/image.elf');assert elf[:6]==b'\x7fELF\x02\x01'
 shoff=struct.unpack_from('<Q',elf,40)[0];shsize,shnum,shstr=struct.unpack_from('<3H',elf,58)
 headers=[struct.unpack_from('<IIQQQQIIQQ',elf,shoff+i*shsize) for i in range(shnum)]
 namesec=headers[shstr];namestr=elf[namesec[4]:namesec[4]+namesec[5]];text=[]
 for h in headers:
  name=namestr[h[0]:].split(b'\0',1)[0]
  if name==b'.text':text.append(elf[h[4]:h[4]+h[5]])
 assert text==[machine]
archive_bytes=read(R/'payload/runtime/shutdown-archive.json');archive=json.loads(archive_bytes)
ac=claim(bytes.fromhex(archive['raw_claim']['bytes_hex']),10)
assert ac['rows']==c4['rows'] and ac['epoch']==c4['epoch'] and ac['version']==c4['version']
assert len(archive['facts'])==2 and archive['learning_closed']
context=dict(archive['construction_context']);history=json.loads(context['original_runtime_history'])
historypins=load(Path('/tmp/kdlock-kernel8-killable-final-recovery-20261111-01/history-pins.json'))
assert set(history)==set(historypins) and len(history)==146
for name,row in history.items():
 raw=bytes.fromhex(row['data_hex']);assert len(raw)==row['bytes']==historypins[name]['bytes'] and sha(raw)==row['sha256']==historypins[name]['sha256']
 assert raw==read(F/'payload/runtime'/name)
assert sum(row['bytes'] for row in history.values())==1537842
assert json.loads(context['restored_producer'])==proof
archivekeys=[[int.from_bytes(bytes.fromhex(f['fact']['record_identity']['bytes_hex']),'little'),f['fact']['incarnation']] for f in archive['facts']]
assert archivekeys==keys
assert bytes.fromhex(archive['raw_claim']['bytes_hex'])==read(R/'payload/runtime/wire/attempt-00000003/reply.bin')
reqfixed,reqkeys,reqblobs=framed(read(R/'payload/runtime/wire/attempt-00000004/request.bin'),11,2,2,1)
assert [list(x) for x in reqkeys]==keys and reqblobs==[hashlib.sha256(archive_bytes).digest()]
assert reqfixed==tuple([ac['claim_identity'],ac['holder_identity']])
fs,settled,_=framed(read(R/'payload/runtime/wire/attempt-00000004/reply.bin'),11,3,2)
assert [list(x) for x in settled]==keys
assert (len(archive_bytes),sha(archive_bytes))==(3318053,'0cdb77a5c44ff7ad4dcb81081f9eccd37d041702638a43c62e133a31563e7cd7')
assert rr['archive']=={'bytes':len(archive_bytes),'claim_keys':2,'settled_keys':2,'sha256':sha(archive_bytes)}
assert [a['action'] for a in rr['actions']]==['SIGTERM','RETIRE','rmmod'] and rr['actions'][0]['pid']==12651 and rr['actions'][0]['pidfd_exit_and_fd_release_observed']
assert rr['actions'][1]['returncode']==rr['actions'][2]['returncode']==0
pre=load(R/'payload/runtime/pre-signal.json')
assert all(pre[k]==0 for k in ['cleanup_error','native_scopes','owner','readers','tail','writer','writer_pending','overflow']) and pre['pool_idle']==1
assert all(all(v==(-1 if k in ('admission','selection') else 0) for k,v in role.items()) for role in pre['roles'])
rs=rr['retired_status'];assert all(rs[k]==0 for k in ['binding_live','cleanup_error','native_scopes','owner','readers','runtime_live','self_held','setup_complete','setup_error','source_live','tail','trace_live','writer','writer_pending']) and rs['pool_idle']==rs['retired']==1
assert all(all(v==(-1 if k in ('admission','selection') else 0) for k,v in role.items()) for role in rs['roles'])
assert rr['identity_before']==rr['identity_after'] and rr['identity_after']['boot']=='e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0'
audit['recovery']={'status':rr['status'],'runtime_sha256':sha(read(R/'payload/runtime/result.json')),'producer_proof_sha256':sha(read(R/'payload/runtime/restored-producer-proof.json')),'archive_bytes':len(archive_bytes),'archive_sha256':sha(archive_bytes),'archive_claim_keys':keys,'settled_keys':keys,'embedded_runtime_history_files':146,'embedded_runtime_history_bytes':1537842,'archive_digest_in_settle_request_verified':True,'pre_signal_roles_reset':True,'new_publications':0,'new_coverage_acks':0,'prior_coverage_acknowledged_keys':1,'ordinary_retire_returncode':0,'ordinary_rmmod_returncode':0,'identity':rr['identity_after'],'modules_after':rr['modules_after'],'original_failure_preserved':True}
# Verify and retain both full source transports. Their membership must remain identical.
source_audits=[];source_sets=[]
for label,root in [('before-6a4ba5a1',OLD),('after-5c14b483',NEW)]:
 manifest=load(root/'source-sha256.json');ta=tar_audit(root/'source.tar',manifest);assert len(manifest)==143
 source_sets.append(manifest);source_audits.append({'label':label,'manifest_sha256':sha(read(root/'source-sha256.json')),'state':load(root/'source-state.json'),'transport':ta})
assert set(source_sets[0])==set(source_sets[1])
changed=[k for k in sorted(source_sets[0]) if source_sets[0][k]!=source_sets[1][k]]
assert changed==['tests/kernel/rwsem_killable/README.md','tests/kernel/rwsem_killable/runner.py']
packagepath=Path('/tmp/kdlock-kernel8-build-collection-20261111-01/payload/input/package.json');package=load(packagepath)
assert len(package['files'])==package['code_file_count']==78
assert package['core_git_head']=='0d42063ead37dc8fc1631fa56c8348890ede9c5f'
for name,digest in package['files'].items():
 assert source_sets[0][name]['sha256']==source_sets[1][name]['sha256']==digest
receipt=load(NEW/'export-receipt.json');assert receipt['kernel_package_files']==78 and receipt['kernel_core_git_head']=='0d42063ead37dc8fc1631fa56c8348890ede9c5f'
audit['source_correction']={'sources':source_audits,'changed_members':changed,'kernel_core_files':78,'kernel_core_git_head':receipt['kernel_core_git_head'],'corrected_checker_runtime_status':'not established by K03','source_head':'5c14b483ca16b3bba8f3dd40a00f16a6efefc12c'}
# Preserve complete controls, payloads and collection transports. No duplicate tars omitted.
inputs=[(F,'failure-collection'),(R,'recovery-collection'),(Path('/tmp/kdlock-kernel8-managed-killable-20261111-03'),'source-host/failure'),(Path('/tmp/kdlock-kernel8-killable-final-recovery-20261111-01'),'source-host/recovery'),(Path('/tmp/kdlock-kernel8-killable-final-recovery-copy-20261111-01'),'source-host/recovery-copy'),(Path('/tmp/kdlock-kernel8-restart-state-20261111-01'),'source-host/restart-state'),(OLD,'source-export/before-6a4ba5a1'),(NEW,'source-export/after-5c14b483')]
audit['copied_trees']=[copy_tree(root,rel) for root,rel in inputs]
copy(Path('/tmp/kdlock-kernel8-export-5c14b483-20261111.py'),'source-export/export-5c14b483.py')
copy(packagepath,'source-export/kernel-package-0d42063e.json')
copy(Path(__file__),'archive-copy.py')
for p,(ident,digest) in origins.items():
 q=Path(p);assert identity(q)==ident and sha(q.read_bytes())==digest,p
for row in files:
 b=(DRAFT/row['path']).read_bytes();assert len(b)==row['stored_bytes'] and sha(b)==row['stored_sha256']
 raw=gzip.decompress(b) if row['encoding']=='gzip' else b
 assert len(raw)==row['raw_bytes'] and sha(raw)==row['raw_sha256']
audit['copy_summary']={'copied_files':len(files),'raw_bytes':sum(x['raw_bytes'] for x in files),'stored_bytes':sum(x['stored_bytes'] for x in files),'gzip_files':sum(x['encoding']=='gzip' for x in files),'source_bytes_rechecked':True,'duplicate_transport_tars_omitted':0}
dump(DRAFT/'copy-index.json',{'format':'kdlock.lossless-file-copy.v1','files':files})
dump(DRAFT/'audit.json',audit)
print(json.dumps({'draft':str(DRAFT),'copy_summary':audit['copy_summary'],'audit_sha256':sha((DRAFT/'audit.json').read_bytes()),'copy_index_sha256':sha((DRAFT/'copy-index.json').read_bytes()),'ignored_candidate_paths':[x['path'] for x in files if x['path'].endswith(('.o','.log'))]},indent=2))
