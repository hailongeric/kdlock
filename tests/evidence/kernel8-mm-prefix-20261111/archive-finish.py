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


import argparse
ap=argparse.ArgumentParser()
ap.add_argument('--controls-index-sha256',required=True)
args=ap.parse_args()
assert re.fullmatch('[0-9a-f]{64}',args.controls_index_sha256)
assert DRAFT.is_dir()
index=load(DRAFT/'copy-index.json');files[:]=index['files']
audit=load(DRAFT/'audit.json')
assert audit['status']=='DRAFT_WAITING_CLOSED_POSTREAD_AND_INDEPENDENT_RAW_AUDIT'
for row in files:
 p=Path(row['source']);b=read(p)
 assert identity(p)==row['source_identity'] and len(b)==row['raw_bytes'] and sha(b)==row['raw_sha256']

run=Path('/tmp/kdlock-kernel8-mm-prefix-run-20261111-01')
ix=load(run/'controls-index.json')
assert sha(read(run/'controls-index.json'))==args.controls_index_sha256
assert ix['count']==len(ix['files']) and ix['bytes']==sum(x['bytes'] for x in ix['files'])
assert set(x['name'] for x in ix['files'])==set(str(p.relative_to(run)) for p in source_members(run))-{'controls-index.json'}
for row in ix['files']:
 b=read(run/row['name']);assert (len(b),sha(b))==(row['bytes'],row['sha256'])
peer=Path('/tmp/kdlock-kernel8-mm-prefix-independent-audit-20261111.json')
script=Path('/tmp/kdlock-kernel8-mm-prefix-independent-audit-20261111.py')
proof=load(peer)
assert sha(read(peer))=='9478c230bc7bd1ccd703defadd03f6e0e6faf04c3c283f0df2d96dd3e3012ef0'
assert sha(read(script))==proof['script']['sha256']=='9254090566b564d433622bb517dd12fcfb19dd23beac71d503a94bf5510faaae'
assert proof['status']=='SAVED_MM_PREFIX_RAW_AUDIT_COMPLETE' and proof['entry_counts']=={'mmap':144,'munmap':103}
assert len(proof['episode_witnesses'])==247 and proof['cycles']==2 and proof['publications']==1 and proof['observation_count']==28743 and all(proof['nine_final_gates'].values())
for p,row in proof['inputs'].items():
 b=read(Path(p));assert len(b)==row['bytes'] and sha(b)==row['sha256']
assert proof['source_progress']['protected_mm_completion_observed'] is False and proof['source_progress']['per_instruction_runtime_count_measured'] is False
assert proof['feedback']['coverage_ack_rows']==0 and proof['feedback']['actual_settle_request_and_reply_equal_all_247_exact_keys']
audit['copied_trees'].append(copy_tree(run,'source-host-run'))
copy(peer,'independent-audit/raw-audit.json')
copy(script,'independent-audit/raw-audit.py')
stage=Path('/tmp/kdlock-kernel8-mm-prefix-stage-20261111-01')
six=load(stage/'controls-index.json')
assert sha(read(stage/'controls-index.json'))=='dd57add33283644c9ac1aaa5536919677d57268299e6520a2f1df2f5a3adb144'
assert six['count']==len(six['files'])==6 and six['bytes']==sum(x['bytes'] for x in six['files'])
assert {x['name'] for x in six['files']}=={str(p.relative_to(stage)) for p in source_members(stage)}-{'controls-index.json'}
for row in six['files']:
 b=read(stage/row['name']);assert (len(b),sha(b))==(row['bytes'],row['sha256'])
copy(stage/'controls-index.json','source-host-stage/controls-index.json')
for row in audit['copied_trees']:
 if row['source']==str(stage):row.update(files=7,bytes=sum(identity(p)[4] for p in source_members(stage)))
audit['closed_controls'].append({'source':str(stage),'index':'controls-index.json','sha256':sha(read(stage/'controls-index.json')),'files':6,'bytes':six['bytes']})
post=load(run/'postread.json');stats=load(run/'actual-stats.json');gone=load(run/'no-surviving-local-sessions.json')
assert sha(read(run/'postread.json'))=='262420f4b59d8665645d9d1029facadf5f619ffc193b1cf665ce828e661e4e64'
assert sha(read(run/'actual-stats.json'))=='980d815d172aef3fd47c3261431cfe98b1da34844f6d2caf9b49bc19ca2eedd8'
assert sha(read(run/'no-surviving-local-sessions.json'))=='f62536ad670653c1b23938b441826f72b2d1352fd95fffac5c3433275a064151'
assert post['status']=='FINAL_MM_PREFIX_IDLE_AND_PRESERVATION_VERIFIED'
for k in ['frozen_input5_unchanged','frozen_repo143_unchanged','kernel16_source78_protected_unchanged','module_client_binary_and_admission_unchanged','normal_default_boot_and_installed16_unchanged','prior_failures_K04_recovery_unchanged']:assert post[k] is True
assert post['idle']=={'activity':[],'identity':{'boot':'2ae5991e-d024-48ac-9f86-24a0a8910172','release':'7.0.0-38-kdrebuild8','taint':4096},'modules':'nls_iso8859_1 12288 1 - Live 0xffffffffc000a000\n'}
assert post['absent_original_pids']==gone['guest_original_pids_absent']==[3450,3451,3457] and gone['matching_task_sessions']==[] and gone['actual_launch_collection_postread_returncodes']==[0,0,0]
assert stats['status']=='SAVED_MM_PREFIX_STATS_VERIFIED' and stats['borrowed_prefix_count']==247 and stats['publications']==1 and stats['compiler_cycles']==2 and stats['coverage_ack_keys']==0 and stats['settled_keys']==247
assert stats['protected_mm_completion_observed'] is False and stats['complete_auxiliary_requirement_proved'] is False and stats['native_helper_callbacks_measured'] is False and stats['new_kernel_diagnostic_matches']==[]
assert len(stats['wire'])==14 and all(x['status']==0 for x in stats['wire'])
audit['final_readonly_controls']={'postread_sha256':sha(read(run/'postread.json')),'stats_sha256':sha(read(run/'actual-stats.json')),'no_surviving_sessions_sha256':sha(read(run/'no-surviving-local-sessions.json')),'postread_status':post['status'],'idle':post['idle'],'absent_original_pids':post['absent_original_pids'],'frozen_repo_files':143,'frozen_input_files':5,'linked_kernel_pins':16,'core_source_files':78,'prior_failures_and_K04_preserved':True,'ordinary_default_boot_and_installed16_preserved':True,'stats_status':stats['status'],'worker_effects':stats['worker_effects'],'parent_arena_reservations':stats['parent_arena_reservations'],'wire_attempts':14,'all_wire_status_zero':True,'late_kernel_log_scope':stats['late_kernel_log_scope'],'log_representation_note':stats['log_representation_note']}
copy(Path(__file__),'archive-finish.py')
audit['closed_controls'].append({'source':str(run),'index':'controls-index.json','sha256':args.controls_index_sha256,'files':ix['count'],'bytes':ix['bytes']})
audit['independent_raw_audit']={'source':str(peer),'sha256':sha(read(peer)),'script_source':str(script),'script_sha256':sha(read(script)),'status':proof['status'],'embedded_event_dicts_checked':proof['embedded_event_dicts_checked'],'joined_exact_lifetimes':len(proof['episode_witnesses']),'entry_counts':proof['entry_counts'],'roots':proof['roots'],'source_progress':proof['source_progress'],'feedback':{k:v for k,v in proof['feedback'].items() if k not in ['keys']},'assumptions':proof['assumptions']}
for p,(ident,digest) in origins.items():
 q=Path(p);assert identity(q)==ident and sha(q.read_bytes())==digest,p
for row in files:
 b=(DRAFT/row['path']).read_bytes();assert len(b)==row['stored_bytes'] and sha(b)==row['stored_sha256']
 raw=gzip.decompress(b) if row['encoding']=='gzip' else b
 assert len(raw)==row['raw_bytes'] and sha(raw)==row['raw_sha256']
payload=Path('/tmp/kdlock-kernel8-mm-prefix-collection-20261111-01/payload')
assert read(payload/'input/supervisor.py')==read(Path('/tmp/kdlock-kernel8-mm-prefix-supervisor-20261111-01.py'))
assert read(payload/'outer/runner-result-snapshot.json')==read(payload/'runtime/result.json')
config=load(Path('/tmp/kdlock-kernel8-mm-prefix-0798c1ab-03/host-config.json'))
assert sha(read(payload/'input/jit-config.bin'))==config['sha256']['jit_config']
kernel_log_root=Path('/tmp/kdlock-kernel8-mm-prefix-collection-20261111-01/payload/runtime')
before=read(kernel_log_root/'command-0001/stdout.log');after=read(kernel_log_root/'command-0004/stdout.log')
assert after.startswith(before)
delta=after[len(before):]
assert len(delta)==82 and sha(delta)=='f4a8e80246dde1b460c89d1f2498f428aa92c6ec2df836d8ff9bbccdc266dec0'
assert not re.search(rb'WARNING|BUG|Oops|Call Trace|general protection|Kernel panic',delta,re.I)
audit['kernel_log_delta']={'before_bytes':len(before),'before_sha256':sha(before),'after_bytes':len(after),'after_sha256':sha(after),'unchanged_prefix':True,'delta_bytes':len(delta),'delta_sha256':sha(delta),'delta_text':delta.decode(),'new_failure_diagnostic_present':False,'scope':'Exact recorded before/after dmesg command stdout prefix and delta; no further VM command.'}
audit['status']='COMPLETE'
audit['copy_summary']={'copied_files':len(files),'raw_bytes':sum(x['raw_bytes'] for x in files),'stored_bytes':sum(x['stored_bytes'] for x in files),'gzip_files':sum(x['encoding']=='gzip' for x in files),'source_bytes_rechecked':True,'duplicate_transport_tars_omitted':0,'active_object_capture_included':False,'all_mm_source_host_controls_closed_and_included':True}
audit['readme_sha256']=sha(read(DRAFT/'README.md'))
dump(DRAFT/'copy-index.json',{'format':'kdlock.lossless-file-copy.v1','files':files})
dump(DRAFT/'audit.json',audit)
paths=source_members(DRAFT)
assert not (DRAFT/'SHA256SUMS').exists()
(DRAFT/'SHA256SUMS').write_text(''.join(sha(p.read_bytes())+'  '+str(p.relative_to(DRAFT))+'\n' for p in paths))
assert set(str(p.relative_to(DRAFT)) for p in source_members(DRAFT))==set(row['path'] for row in files)|{'README.md','copy-index.json','audit.json','SHA256SUMS'}
print(json.dumps({'draft':str(DRAFT),'status':audit['status'],'copy_summary':audit['copy_summary'],'total_files':len(paths)+1,'total_stored_bytes':sum(identity(p)[4] for p in source_members(DRAFT)),'audit_sha256':sha(read(DRAFT/'audit.json')),'copy_index_sha256':sha(read(DRAFT/'copy-index.json')),'readme_sha256':sha(read(DRAFT/'README.md')),'sha256sums_sha256':sha(read(DRAFT/'SHA256SUMS'))},indent=2))
