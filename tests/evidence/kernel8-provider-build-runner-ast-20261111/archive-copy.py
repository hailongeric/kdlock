#!/usr/bin/env python3
"""Copy provider-build and runner-AST receipts using only the Python standard library."""
from pathlib import Path, PurePosixPath
import gzip, hashlib, io, json, os, stat, struct, tarfile

DRAFT=Path('/tmp/kdlock-kernel8-provider-build-runner-ast-draft-20261111-01')
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

assert not DRAFT.exists();DRAFT.mkdir()
audit={'format':'kdlock.provider-build-runner-ast-closed-byte-audit.v1','scope':'Standard-library byte, hash and tar archival inspection only. No project imports, AST checks, tests, builds or VM operations were run by this archival script.'}
audit['collections']=[collection(B,22,3181886),collection(A,12,1875905)]
expected=[('build',B,'21d6d90b4d2c91ab2760a0319d5eef8933148ab6452cf1a3f523d2b98b8c63cf','MM_PROVIDER_MODULE_BUILD_COMPLETE'),('ast',A,'3fc26667154f5232125e0e02ea40e11084a39fd475e5a44367d30514bc7d2de0','HOST_FRONTIER_RESERVATION_AST_COMPLETE')]
packagepath=Path('/tmp/kdlock-kernel8-build-collection-20261111-01/payload/input/package.json');package=load(packagepath)
assert len(package['files'])==package['code_file_count']==78 and package['core_git_head']=='0d42063ead37dc8fc1631fa56c8348890ede9c5f'
source_sets={};records={};source_audits=[]
for label,root,digest,status in expected:
 raw=read(root/'payload/receipts/result.json');record=json.loads(raw);records[label]=record
 assert sha(raw)==digest and record['status']==status
 assert record['identity_before']==record['identity_after']=={'activity':[],'identity':{'boot':'e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0','release':'7.0.0-38-kdrebuild8','taint':4096},'modules':'nls_iso8859_1 12288 1 - Live 0xffffffffc000a000\n'}
 assert record['kernel_core_git_head']==package['core_git_head'] and len(record['core_pins_before'])==16
 for command in record['commands']:
  assert command['returncode']==0
  log=read(root/'payload/receipts'/(command['label']+'.log'));assert sha(log)==command['log_sha256']
  assert not any('insmod' in arg or 'rmmod' in arg for arg in command['argv'])
 transport=root/'payload/transport';manifest=load(transport/'source-sha256.json');state=load(transport/'source-state.json')
 assert len(manifest)==state['files']==143 and state['git_status']=='' and state['source_git_head']==record['source_git_head'] and state['transfer_bytes']==sum(x['bytes'] for x in manifest.values())
 ta=tar_audit(transport/'source.tar',manifest)
 for name,h in package['files'].items():assert manifest[name]['sha256']==h
 source_sets[label]=manifest
 source_audits.append({'label':label,'manifest_sha256':sha(read(transport/'source-sha256.json')),'state_sha256':sha(read(transport/'source-state.json')),'state':state,'transport':ta,'all_78_core_hashes_match_package':True})
 # Driver exit is an independent retained process receipt, not inferred from result status.
 driver=load(root/'payload/driver/return.json');assert driver['returncode']==0
print('collection payloads, source143/core78 and actual command log hashes verified')
b=records['build'];a=records['ast'];recipepath=B/'payload/transport/recipe.json';recipe=load(recipepath)
assert b['source_git_head']=='de76da8aa2031d73f185f5864071f316c1150c08' and b['source_files_verified']==143
assert sha(read(recipepath))==b['recipe_sha256']=='8534523d3e9af0d3f27be329692c3ced75c8ce6e3b7a18f7ac6ca98f0c9c5c30'
assert len(b['commands'])==7 and [c['label'] for c in b['commands']]==['mmap-build','mmap-sign','mmap-vermagic','mmap-signer','mmap-sig_key','mmap-sig_hashalgo','mmap-depends']
assert [c['argv'] for c in b['commands']]==[c['argv'] for c in recipe['commands']]
assert b['tools_before']==b['tools_after'] and b['preserved_artifacts_unchanged'] and len(b['preserved_artifacts_before'])==11
assert b['signing_private_key_data_recorded'] is False
module=b['modules']['mmap']
for label in ['unsigned','signed']:
 raw=read(B/'payload'/(label+'.ko'));row=module[label];assert len(raw)==row['bytes'] and sha(raw)==row['sha256']
 assert raw[:6]==b'\x7fELF\x02\x01'
unsigned=read(B/'payload/unsigned.ko');signed=read(B/'payload/signed.ko')
assert signed.startswith(unsigned) and signed.endswith(b'~Module signature appended~\n')
assert module['modinfo']==recipe['expected_modinfo']
for key,value in module['modinfo'].items():assert read(B/'payload/receipts'/('mmap-'+key+'.log')).decode().strip()==value
assert len(module['diagnostics'])==1 and 'frame size of 1912 bytes is larger than 1024 bytes' in module['diagnostics'][0]['text'] and 'mmap_jit_profile.inc:615:1' in module['diagnostics'][0]['text']
loglines=read(B/'payload/receipts/mmap-build.log').decode().splitlines()
assert loglines[module['diagnostics'][0]['line']-1]==module['diagnostics'][0]['text']
assert b['prior_build_status']=='FAILED_OR_INCOMPLETE'
for name,row in recipe['host_source']['transport'].items():
 raw=read(B/'payload/transport'/name);assert len(raw)==row['bytes'] and sha(raw)==row['sha256']
assert b['recovery']['sha256']=='430e21491f050b3584a327f9ab62ff519efe70a64a22f45344dd7a856e9fd30d'
audit['provider_build']={'status':b['status'],'result_sha256':expected[0][2],'source_git_head':b['source_git_head'],'kernel_core_git_head':b['kernel_core_git_head'],'kernelrelease':b['kernelrelease'],'linked_build_id':b['linked_build_id'],'commands':b['commands'],'module':module,'recipe_sha256':b['recipe_sha256'],'recovery_sha256':b['recovery']['sha256'],'source_files_verified':143,'core_files':78,'linked_pins':16,'preserved_prior_artifact_pins':11,'signing_private_key_data_recorded':False,'provider_loaded':False,'mm_execution':'not_exercised','prior_incomplete_build_preserved':True,'identity':b['identity_after']}
assert a['source_git_head']=='5c14b483ca16b3bba8f3dd40a00f16a6efefc12c' and a['checks']=={'frontier_reservation_killable_runner_ast':1}
assert len(a['commands'])==1 and a['commands'][0]['label']=='frontier-reservation-killable-runner-ast'
assert a['cleanup_sha256']=='40872340905c520739493208ba84323e3f16b6aed40e7119cefc08bf8f5fd1f0'
assert a['objdump_before']==a['objdump_after']
assert read(A/'payload/receipts/frontier-reservation-killable-runner-ast.log')==b'FRONTIER_RESERVATION_KILLABLE_RUNNER_AST_COMPLETE 1\n'
cmd=a['commands'][0]['argv'];assert cmd[1:3]==['-B','-c'] and 'ast.parse(' in cmd[3] and cmd[4].endswith('/tests/kernel/rwsem_killable/runner.py')
assert source_sets['ast']['tests/kernel/rwsem_killable/runner.py']['sha256']=='b8aaa909ac8aba2db51de0dc10267480e53811fd850aeacc621a3677a30924e6'
assert source_sets['ast']['tests/kernel/rwsem_killable/README.md']['sha256']=='3f14a9762b3ccda8ec1f75bb0c726ac1674023e1be03f661a38a13aa4630ba0f'
audit['runner_ast']={'status':a['status'],'result_sha256':expected[1][2],'source_git_head':a['source_git_head'],'commands':a['commands'],'checks':a['checks'],'cleanup_sha256':a['cleanup_sha256'],'prior_named_source_sha256':a['prior_named_source_sha256'],'prior_named_source_checks_repeated':False,'runner_syntax_parsed_only':True,'runtime_execution':'not_exercised','identity':a['identity_after']}
assert set(source_sets['build'])==set(source_sets['ast'])
audit['source_transports']=source_audits
audit['source_delta_between_distinct_outcomes']=[name for name in sorted(source_sets['build']) if source_sets['build'][name]!=source_sets['ast'][name]]
inputs=[(B,'provider-build/collection'),(A,'runner-ast/collection'),(Path('/tmp/kdlock-kernel8-mm-provider-build-de76da8a-01'),'provider-build/source-host'),(Path('/tmp/kdlock-kernel8-frontier-claim-ast-20261111-01'),'runner-ast/source-host')]
audit['copied_trees']=[copy_tree(root,rel) for root,rel in inputs]
copy(packagepath,'kernel-package-0d42063e.json')
copy(Path(__file__),'archive-copy.py')
for p,(ident,digest) in origins.items():
 q=Path(p);assert identity(q)==ident and sha(q.read_bytes())==digest,p
for row in files:
 raw=(DRAFT/row['path']).read_bytes();assert len(raw)==row['stored_bytes'] and sha(raw)==row['stored_sha256']
 data=gzip.decompress(raw) if row['encoding']=='gzip' else raw
 assert len(data)==row['raw_bytes'] and sha(data)==row['raw_sha256']
audit['copy_summary']={'copied_files':len(files),'raw_bytes':sum(x['raw_bytes'] for x in files),'stored_bytes':sum(x['stored_bytes'] for x in files),'gzip_files':sum(x['encoding']=='gzip' for x in files),'source_bytes_rechecked':True,'duplicate_transport_tars_omitted':0}
dump(DRAFT/'copy-index.json',{'format':'kdlock.lossless-file-copy.v1','files':files})
dump(DRAFT/'audit.json',audit)
print(json.dumps({'draft':str(DRAFT),'copy_summary':audit['copy_summary'],'audit_sha256':sha((DRAFT/'audit.json').read_bytes()),'copy_index_sha256':sha((DRAFT/'copy-index.json').read_bytes()),'source_delta':audit['source_delta_between_distinct_outcomes']},indent=2))
