#!/usr/bin/env python3
"""Copy closed MM-prefix inputs using only the Python standard library."""
from pathlib import Path, PurePosixPath
import gzip, hashlib, io, json, os, re, stat, struct, tarfile

DRAFT=Path('/tmp/kdlock-kernel8-mm-prefix-evidence-draft-20261111-01')
B=Path('/tmp/kdlock-kernel8-mm-provider-build-collection-de76da8a-01')
A=Path('/tmp/kdlock-kernel8-frontier-claim-ast-collection-20261111-01')
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
 if len(b)>=65536 and p.suffix not in ('.o','.elf','.ko'):
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

M=Path('/tmp/kdlock-kernel8-mm-prefix-collection-20261111-01')
R=Path('/tmp/kdlock-kernel8-repeatboot-collection-20261111-02')
S=Path('/tmp/kdlock-kernel8-fixture-source-0798c1ab-01')
assert not DRAFT.exists();DRAFT.mkdir()
audit={'format':'kdlock.mm-prefix-closed-byte-audit.v1','status':'DRAFT_WAITING_CLOSED_POSTREAD_AND_INDEPENDENT_RAW_AUDIT','scope':'Offline standard-library byte/hash/tar/record inspection only. No project import, test, build, object-tool or VM execution.'}
audit['mm_collection']=collection(M,176,51325789)
audit['repeatboot_collection']=collection(R,76,14869902)
assert audit['mm_collection']['copy_index_sha256']=='5f1a8c78a528864de642817b3b6d38c98295dabf3c824558cb3756b538ec8097'
assert audit['repeatboot_collection']['copy_index_sha256']=='7160752bf14065136e08ab6c600546cb57b2b8967994b6bd7de6fa170361f40d'

def controls(root,index_name):
 ix=load(root/index_name)
 assert ix['count']==len(ix['files']) and ix['bytes']==sum(x['bytes'] for x in ix['files'])
 assert set(x['name'] for x in ix['files'])==set(str(p.relative_to(root)) for p in source_members(root))-set([index_name])
 for row in ix['files']:
  b=read(root/row['name']);assert (len(b),sha(b))==(row['bytes'],row['sha256'])
 return {'source':str(root),'index':index_name,'sha256':sha(read(root/index_name)),'files':ix['count'],'bytes':ix['bytes']}

failroot=Path('/tmp/kdlock-kernel8-repeatboot-run-20261111-01')
successroot=Path('/tmp/kdlock-kernel8-repeatboot-run-20261111-02')
metadata=Path('/tmp/kdlock-kernel8-runtime-metadata-20261111-02')
audit['closed_controls']=[controls(failroot,'failed-controls-index.json'),controls(successroot,'controls-index.json'),controls(metadata,'copy-index.json')]
fail=load(failroot/'failed-preflight.json')
assert fail['status']=='PREFLIGHT_FAILED_BEFORE_PHASE_AND_BOOT_SELECTION' and fail['returncode']==1 and not fail['arm_or_reboot_dispatched'] and fail['menu_commands_dispatched']==0 and not fail['namespace_byte_drift_observed']
assert sha(read(Path('/tmp/kdlock-kernel8-repeatboot-mm-frontier-20261111-01/repeat.py')))==fail['helper_sha256']=='9543da61aeceb6c449a44848750972315f4f480f27234501ae1d860bcbebbc23'
assert sha(read(Path('/tmp/kdlock-kernel8-repeatboot-mm-frontier-20261111-02/repeat.py')))==fail['corrected_helper_prepared_sha256']=='54c5c48385e459e71d17061920463c5d29983327135442635d303c30cc7f99e9'
configroot=Path('/tmp/kdlock-kernel8-mm-prefix-0798c1ab-03');config=load(configroot/'host-config.json')
assert sha(read(configroot/'host-config.json'))=='c38376355e1b34c5a7dd7c645c8666b8737c201aefe12c31b6d69ba38ba3ec54'
for q in [M/'payload/input/host-config.json',M/'payload/outer/config.json',M/'payload/runtime/config.json']:assert read(q)==read(configroot/'host-config.json')
assert read(M/'payload/runtime/gs_proof.input')==read(successroot/'actual-gs-proof.json') and sha(read(successroot/'actual-gs-proof.json'))==config['sha256']['gs_proof']
assert sha(read(metadata/'stdout.json'))==config['experimental_admission']['fresh_metadata_sha256']=='e503f28582cc90cabb4cbe1112da3acf2769112e23132fd601dd9d6ecc869691'
for p in [configroot/'recovery.json',Path('/tmp/kdlock-kernel8-mm-prefix-recovery-20261111-01/recovery.json')]:assert sha(read(p))==config['sha256']['recovery']=='5e67b010e274427e676677043fef389f22488f9639319e9e7dcfbd5029561fde'
outer=load(M/'payload/outer/result.json');inner=load(M/'payload/runtime/result.json')
assert sha(read(M/'payload/outer/result.json'))=='637457c3e5399fc91eac45d11b7bf0fc2407b70c905a4b97ea88fe758c27a89e'
assert sha(read(M/'payload/runtime/result.json'))==outer['runner_result_sha256']=='08d9660d0d81faf2481c63eedacc8d1e382318fc7084e6895e09a2df701e6bb6'
assert outer['status']=='SYSCALL_AND_BORROWED_PREFIX_COMPLETE' and outer['child_returncode']==0 and not outer['signals_or_cleanup_on_failure'] and outer['config_unchanged']
assert inner['status']=='syscall_and_borrowed_jit_prefix_pass' and inner['overall_pass'] and inner['syscall_pass'] and inner['borrowed_jit_prefix_observed'] and inner['borrowed_generated_entry_observed']
assert inner['protected_mm_completion_observed'] is False and inner['meaningful_returned_mm_body']=='not_established'
expected_gates={'all_round_effects','client_returned_zero','original_owner_left','provider_retired','native_gate_drained','shutdown_archive_settle_end','channel_closed','provider_unloaded','provider_devices_absent'}
assert set(inner['protected_completion_final_gates'])==expected_gates and all(v is True for v in inner['protected_completion_final_gates'].values())
assert inner['boot_id']==inner['post_boot_id']==config['boot_id']=='2ae5991e-d024-48ac-9f86-24a0a8910172' and inner['post_taint']==4096
assert inner['workload']==config['workload'] and len(inner['rounds'])==3 and inner['client_returncode']==0
assert len(inner['cycles'])==2 and sum(x['published'] for x in inner['cycles'])==1 and sum(x['acknowledged'] for x in inner['cycles'])==0
assert len(inner['facts'])==inner['settled_keys']==247 and all(x['acknowledged'] is False for x in inner['facts'])
rounds=[]
for row in inner['rounds']:
 w=row['workload'];assert w['completed_iterations']==64 and w['overall_pass'] and w['worker_errors']==0 and len(w['workers'])==8 and not w['deadline_exceeded']
 sums={k:sum(x[k] for x in w['workers']) for k in ['completed','mmap_attempts','mmap_successes','munmap_attempts','munmap_successes','mincore_attempts','unmapped_page_checks','reuse_successes','fresh_zero_bytes','written_bytes','readback_bytes']}
 assert sums['completed']==64 and sums['mmap_attempts']==sums['mmap_successes']==192 and sums['munmap_attempts']==sums['munmap_successes']==128
 rounds.append({'round':row['round'],'workers':8,'effects':sums,'arena_reservations':w['arena_reservations'],'arena_cleanup_errno':w['arena_cleanup_errno']})
manifest=load(S/'source-sha256.json');state=load(S/'source-state.json');export=load(S/'export-receipt.json')
assert state=={'files':143,'git_status':'','source_git_head':'0798c1abf422017cfc93647a2649be0e5a73c75a','transfer_bytes':1614072}
assert len(manifest)==143 and sum(x['bytes'] for x in manifest.values())==1614072
source_tar=tar_audit(S/'source.tar',manifest)
assert source_tar['sha256']=='3b2512060b7eb3cac27b3a794bb5f0dc833c6ff24cd9866218481b53832a8053'
packagepath=Path('/tmp/kdlock-kernel8-build-collection-20261111-01/payload/input/package.json');package=load(packagepath)
assert package['core_git_head']=='0d42063ead37dc8fc1631fa56c8348890ede9c5f' and len(package['files'])==78 and all(manifest[n]['sha256']==v for n,v in package['files'].items())
assert manifest['tests/kernel/mmap_api/runner.py']['sha256']==outer['runner_sha256']=='3f36ab1289a6bc8e1601a745d36615d96d4a4bb9600c13d4ce8d99e321744afa'
assert config['sha256']['source_manifest']==sha(read(S/'source-sha256.json')) and config['sha256']['source_state']==sha(read(S/'source-state.json'))
supervisor=Path('/tmp/kdlock-kernel8-mm-prefix-supervisor-20261111-01.py')
assert sha(read(supervisor))=='09dc900987cec70b89ea60620ddd07c1493fa6c7dd2b4649201421b33c238ebc'
audit.update(repeatboot_failed_preflight=fail,source={'state':state,'manifest_sha256':sha(read(S/'source-sha256.json')),'transport':source_tar,'core_files':78,'core_head':package['core_git_head'],'export':export},actual_result={'outer_sha256':sha(read(M/'payload/outer/result.json')),'inner_sha256':sha(read(M/'payload/runtime/result.json')),'outer_status':outer['status'],'inner_status':inner['status'],'supervisor_sha256':sha(read(supervisor)),'runner_sha256':outer['runner_sha256'],'config_sha256':outer['config_sha256'],'child_pid':outer['child_pid'],'child_returncode':outer['child_returncode'],'boot_id':inner['boot_id'],'post_taint':inner['post_taint'],'rounds':rounds,'completed_worker_iterations':192,'worker_mmap_successes':576,'worker_munmap_successes':384,'publications':1,'cycles':2,'coverage_acknowledged':0,'settled_keys':247,'final_gates':inner['protected_completion_final_gates'],'protected_mm_completion_observed':False,'meaningful_returned_mm_body':'not_established'},separate_records={'aux_review':'tests/evidence/kernel8-aux-context-review-20261111','provider_frame_build':'tests/evidence/kernel8-mm-ioctl-frame-build-20261111','conditional_budget_sha256':'bdcab02965bc43fb2134e5ef13087a0ecec92ee9fbfaef98ae62b657a8bf35b2','experimental_admission_sha256':'db233cd8ac3164d3170c071ecc7081c9e58141f93cbf0b147f700dab761f5a1b','full_auxiliary_requirement_proved':False,'native_helper_callbacks_measured':False})
closed_trees=[(M,'mm-collection'),(R,'repeatboot-collection'),(S,'source-export'),(failroot,'repeatboot/source-host-failed-01'),(successroot,'repeatboot/source-host-02'),(Path('/tmp/kdlock-kernel8-repeatboot-mm-frontier-20261111-01'),'repeatboot/helper-original-01'),(Path('/tmp/kdlock-kernel8-repeatboot-mm-frontier-20261111-02'),'repeatboot/helper-corrected-02'),(metadata,'fresh-runtime-metadata-02'),(Path('/tmp/kdlock-kernel8-mm-prefix-recovery-20261111-01'),'fresh-recovery'),(Path('/tmp/kdlock-kernel8-mm-prefix-stage-20261111-01'),'source-host-stage'),(Path('/tmp/kdlock-kernel8-mm-prefix-0798c1ab-01'),'configuration/initial-plan-01'),(Path('/tmp/kdlock-kernel8-mm-prefix-0798c1ab-02'),'configuration/geometry-and-admission-02'),(configroot,'configuration/actual-03')]
audit['copied_trees']=[copy_tree(p,rel) for p,rel in closed_trees]
copy(packagepath,'source-export/kernel-package-0d42063e.json')
copy(Path('/tmp/kdlock-kernel8-export-0798c1ab-20261111.py'),'source-export/export-0798c1ab.py')
copy(supervisor,'supervisor.py')
copy(Path(__file__),'archive-copy.py')
for p,(ident,digest) in origins.items():
 q=Path(p);assert identity(q)==ident and sha(q.read_bytes())==digest,p
for row in files:
 b=(DRAFT/row['path']).read_bytes();assert len(b)==row['stored_bytes'] and sha(b)==row['stored_sha256']
 raw=gzip.decompress(b) if row['encoding']=='gzip' else b
 assert len(raw)==row['raw_bytes'] and sha(raw)==row['raw_sha256']
audit['copy_summary']={'copied_files':len(files),'raw_bytes':sum(x['raw_bytes'] for x in files),'stored_bytes':sum(x['stored_bytes'] for x in files),'gzip_files':sum(x['encoding']=='gzip' for x in files),'source_bytes_rechecked':True,'duplicate_transport_tars_omitted':0,'active_object_capture_included':False,'still_active_mm_source_host_included':False}
dump(DRAFT/'copy-index.json',{'format':'kdlock.lossless-file-copy.v1','files':files});dump(DRAFT/'audit.json',audit)
print(json.dumps({'draft':str(DRAFT),'status':audit['status'],'copy_summary':audit['copy_summary']},indent=2))
