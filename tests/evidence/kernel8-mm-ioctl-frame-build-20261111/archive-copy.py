#!/usr/bin/env python3
"""Copy provider-build and runner-AST receipts using only the Python standard library."""
from pathlib import Path, PurePosixPath
import gzip, hashlib, io, json, os, re, stat, struct, tarfile

DRAFT=Path('/tmp/kdlock-kernel8-mm-ioctl-frame-build-draft-20261111-01')
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
B=Path('/tmp/kdlock-kernel8-mm-provider-build-collection-0798c1ab-01')
H=Path('/tmp/kdlock-kernel8-mm-provider-build-0798c1ab-01')
S=Path('/tmp/kdlock-kernel8-fixture-source-0798c1ab-01')
O=Path('/tmp/kdlock-kernel8-mm-provider-build-collection-de76da8a-01')
assert not DRAFT.exists();DRAFT.mkdir()
audit={'format':'kdlock.mm-ioctl-frame-build-closed-byte-audit.v1','scope':'Offline standard-library file, hash, tar, ELF and recorded-disassembly inspection. No project import, test, build, object tool or VM execution.'}
audit['collection']=collection(B,24,3268998)
assert audit['collection']['copy_index_sha256']=='9e7f1b77bd06d4a633de73d6fcd6501db4513643f699f6f4372b20a0721b60ae'
r=load(B/'payload/receipts/result.json');recipe=load(B/'payload/transport/recipe.json');prior=load(O/'payload/receipts/result.json')
assert sha(read(B/'payload/receipts/result.json'))=='73f57b2690b98c442160b576b757429a0090674f75f6eeafb60d7499ac473052'
assert r['status']=='MM_PROVIDER_MODULE_BUILD_COMPLETE' and r['source_git_head']=='0798c1abf422017cfc93647a2649be0e5a73c75a'
assert len(r['commands'])==9 and all(c['returncode']==0 for c in r['commands'])
assert [c['argv'] for c in r['commands']]==[c['argv'] for c in recipe['commands']]
for c in r['commands']:assert sha(read(B/'payload/receipts'/(c['label']+'.log')))==c['log_sha256']
assert sha(read(B/'payload/transport/recipe.json'))==r['recipe_sha256']=='ea8c428a9a82f1e4d193a33998c949e58be8e22f79e8e07dfa6231007f0341a7'
assert read(B/'payload/transport/controller.py')==read(H/'controller.py') and sha(read(H/'controller.py'))=='6d166dac84dcf0d48fbaf5f4ae78411c4d34f82ec8fbc459802c912cde4f3136'
assert r['modules']['mmap']['diagnostics']==[] and r['modules']['mmap']['modinfo']==recipe['expected_modinfo']
assert not re.search(r'\b(?:warning:|error:)',read(B/'payload/receipts/mmap-build.log').decode())
assert r['tools_before']==r['tools_after'] and r['tools_after']['objdump']['sha256']=='44f07f8da860b15bd4dec909f229dec536595fb170a616fe3ab29c7b21c9736f'
expected_idle={'activity':[],'identity':{'boot':'e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0','release':'7.0.0-38-kdrebuild8','taint':4096},'modules':'nls_iso8859_1 12288 1 - Live 0xffffffffc000a000\n'}
assert r['identity_before']==r['identity_after']==expected_idle and r['linked_build_id']=='a33dd4d11d0f0c6649107507e685b6e86e716c1a'
assert len(r['core_pins_before'])==16 and len(r['preserved_artifacts_before'])==11 and r['preserved_artifacts_unchanged'] and r['source_files_verified']==143
assert r['previous_provider']['receipt_sha256']==sha(read(O/'payload/receipts/result.json'))=='21d6d90b4d2c91ab2760a0319d5eef8933148ab6452cf1a3f523d2b98b8c63cf'
assert len(prior['modules']['mmap']['diagnostics'])==1 and 'frame size of 1912 bytes is larger than 1024 bytes' in prior['modules']['mmap']['diagnostics'][0]['text']
assert r['signing_private_key_data_recorded'] is False
# Module bytes remain distinct from each other and from the prior build.
for label,root,record in [('current',B,r),('previous',O,prior)]:
 for form in ['unsigned','signed']:
  data=read(root/'payload'/(form+'.ko'));row=record['modules']['mmap'][form];assert len(data)==row['bytes'] and sha(data)==row['sha256'] and data[:6]==b'\x7fELF\x02\x01'
  if label=='previous':assert row==r['previous_provider'][form]==r['previous_provider_pins'][form]
 unsigned=read(root/'payload/unsigned.ko');signed=read(root/'payload/signed.ko');assert signed.startswith(unsigned) and signed.endswith(b'~Module signature appended~\n')
# Independent ELF symbol/section decoding verifies each measured SUB and PUSH byte.
def elf_function(data,symbol):
 shoff=struct.unpack_from('<Q',data,40)[0];shsize,shnum,shstr=struct.unpack_from('<3H',data,58)
 headers=[struct.unpack_from('<IIQQQQIIQQ',data,shoff+i*shsize) for i in range(shnum)]
 matches=[]
 for h in headers:
  if h[1]!=2:continue
  string=headers[h[6]];names=data[string[4]:string[4]+string[5]]
  for off in range(h[4],h[4]+h[5],h[9]):
   no,info,other,section,value,size=struct.unpack_from('<IBBHQQ',data,off);name=names[no:].split(b'\0',1)[0]
   if name.decode()==symbol:
    assert info&15==2;target=headers[section];matches.append({'value':value,'size':size,'section_offset':target[4],'section_address':target[3]})
 assert len(matches)==1;return matches[0]
frames={}
for label,root,expected_reserve in [('old',O,1912),('new',B,704)]:
 key='mmap-'+label+'-ioctl-frame';frame=r['frame_comparison'][key];log=read(B/'payload/receipts'/(key+'.log'))
 assert len(log)==frame['log_bytes']<=262144 and sha(log)==frame['log_sha256']
 assert re.findall(r'^\s*[0-9a-f]+ <([^>]+)>:\s*$',log.decode(),re.M)==['jit_ioctl']
 assert frame['fixed_rsp_reservation_bytes']==expected_reserve and frame['callee_save_push_bytes']==48 and frame['entry_prologue_bytes']==expected_reserve+48
 instructions=[]
 for line in log.decode().splitlines():
  m=re.match(r'^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s*(.*?)\s*$',line)
  if m:instructions.append({'address':int(m[1],16),'mnemonic':m[2],'operands':m[3].split('#',1)[0].strip(),'text':line})
 prologue=frame['prologue'];assert instructions[:len(prologue)]==prologue and prologue[-1]==frame['reservation_instruction']
 assert sum(x['mnemonic']=='push' for x in prologue)==6
 module=read(root/'payload/unsigned.ko');fn=elf_function(module,'jit_ioctl');sub=frame['reservation_instruction']
 assert fn['value']==prologue[0]['address'] and fn['value']<=sub['address']<fn['value']+fn['size']
 offset=fn['section_offset']+sub['address']-fn['section_address'];machine=module[offset:offset+7]
 assert machine==b'\x48\x81\xec'+struct.pack('<I',expected_reserve)
 push_bytes={'rbp':b'\x55','rbx':b'\x53','r12':b'\x41\x54','r13':b'\x41\x55','r14':b'\x41\x56','r15':b'\x41\x57'}
 for x in prologue:
  if x['mnemonic']=='push':
   pb=push_bytes[x['operands']];off=fn['section_offset']+x['address']-fn['section_address'];assert module[off:off+len(pb)]==pb
 frames[label]={'fixed_rsp_reservation_bytes':expected_reserve,'callee_save_push_bytes':48,'entry_prologue_bytes':expected_reserve+48,'reservation_machine_hex':machine.hex(),'elf_symbol':fn,'log_sha256':sha(log)}
assert r['frame_comparison']['fixed_rsp_reservation_reduction_bytes']==r['frame_comparison']['entry_prologue_reduction_bytes']==1208
# Check the full exact source transport and unchanged linked kernel package.
manifest=load(S/'source-sha256.json');state=load(S/'source-state.json');export=load(S/'export-receipt.json');packagepath=Path('/tmp/kdlock-kernel8-build-collection-20261111-01/payload/input/package.json');package=load(packagepath)
assert state=={'files':143,'git_status':'','source_git_head':r['source_git_head'],'transfer_bytes':1614072}
assert len(manifest)==143 and sum(x['bytes'] for x in manifest.values())==1614072
assert len(package['files'])==package['code_file_count']==78 and package['core_git_head']==r['kernel_core_git_head']=='0d42063ead37dc8fc1631fa56c8348890ede9c5f'
assert all(manifest[n]['sha256']==v for n,v in package['files'].items())
source_tar=tar_audit(S/'source.tar',manifest);assert source_tar['sha256']=='3b2512060b7eb3cac27b3a794bb5f0dc833c6ff24cd9866218481b53832a8053'
for n in ['source.tar','source-sha256.json','source-state.json']:
 assert read(S/n)==read(H/n)==read(B/'payload/transport'/n) and len(read(S/n))==recipe['host_source']['transport'][n]['bytes'] and sha(read(S/n))==recipe['host_source']['transport'][n]['sha256']
oldmanifestpath=Path('/tmp/kdlock-kernel8-fixture-source-5c14b483-01/source-sha256.json');oldmanifest=load(oldmanifestpath)
assert set(oldmanifest)==set(manifest)
changed=[n for n in sorted(manifest) if manifest[n]!=oldmanifest[n]]
assert changed==export['changed_from_5c14b483']==['kernel/integration/RWSEM.md','tests/kernel/mmap_api/payload/mmap_jit_profile.inc','tests/kernel/rwsem_killable/README.md']
post=load(H/'postread.json');assert post['status']=='POST_0798_BUILD_IDLE_AND_PRESERVATION_VERIFIED' and post['idle']==expected_idle and post['linked16_and_boot_unchanged'] and post['new_provider_unloaded'] and post['previous_provider_and_K04_failure_recovery_receipts_unchanged'] and post['new_source_files']==143
assert load(H/'launch-return.json')['returncode']==load(B/'payload/driver/return.json')['returncode']==0
assert sha(read(H/'recovery.json'))==r['recovery']['sha256']=='7554d28d150fcc09b391200aa7474d3b871e85c128abe4202aee373decaaf0b6'
audit.update(result={'status':r['status'],'sha256':sha(read(B/'payload/receipts/result.json')),'commands':r['commands'],'warnings':[],'modules':r['modules'],'recipe_sha256':r['recipe_sha256'],'controller_sha256':sha(read(H/'controller.py')),'recovery_sha256':r['recovery']['sha256']},frame_comparison={'old':frames['old'],'new':frames['new'],'entry_and_fixed_reservation_reduction_bytes':1208,'scope':'Fixed jit_ioctl entry reservation and preceding pushes only. Excludes return word, called functions, complete control-path stack use and AUX/scheduler proof.'},source={'head':r['source_git_head'],'files':143,'source_bytes':1614072,'transport':source_tar,'core_files':78,'core_head':package['core_git_head'],'changed_from_5c14b483':changed},previous_provider={'result_sha256':sha(read(O/'payload/receipts/result.json')),'status':prior['status'],'diagnostics':prior['modules']['mmap']['diagnostics'],'source_head':prior['source_git_head'],'separate_committed_archive':'tests/evidence/kernel8-provider-build-runner-ast-20261111'},preservation={'linked_pins':16,'prior_module_and_client_pins':11,'previous_provider_forms':2,'source_files':143,'core_files':78,'private_key_data_recorded':False,'identity':r['identity_after'],'post_build_idle':post,'provider_loaded':False,'mm_execution':'not_exercised','aux_stack_bound':'not_established'})
audit['copied_trees']=[copy_tree(B,'collection'),copy_tree(H,'source-host'),copy_tree(S,'source-export')]
for form in ['unsigned','signed']:copy(O/'payload'/(form+'.ko'),'comparison-inputs/previous-provider/'+form+'.ko')
copy(O/'payload/receipts/result.json','comparison-inputs/previous-provider/result.json')
copy(O/'payload/receipts/mmap-build.log','comparison-inputs/previous-provider/mmap-build.log')
copy(packagepath,'source-export/kernel-package-0d42063e.json')
copy(oldmanifestpath,'source-export/prior-5c14b483-manifest.json')
copy(Path('/tmp/kdlock-kernel8-export-0798c1ab-20261111.py'),'source-export/export-0798c1ab.py')
copy(Path('/tmp/kdlock-mmap-ioctl-stack-fix-5cbd1721.patch'),'source-change/mmap-jit-profile.diff')
copy(Path(__file__),'archive-copy.py')
for p,(ident,digest) in origins.items():
 q=Path(p);assert identity(q)==ident and sha(q.read_bytes())==digest,p
for row in files:
 b=(DRAFT/row['path']).read_bytes();assert len(b)==row['stored_bytes'] and sha(b)==row['stored_sha256']
 raw=gzip.decompress(b) if row['encoding']=='gzip' else b
 assert len(raw)==row['raw_bytes'] and sha(raw)==row['raw_sha256']
audit['copy_summary']={'copied_files':len(files),'raw_bytes':sum(x['raw_bytes'] for x in files),'stored_bytes':sum(x['stored_bytes'] for x in files),'gzip_files':sum(x['encoding']=='gzip' for x in files),'source_bytes_rechecked':True,'duplicate_transport_tars_omitted':0,'active_object_capture_included':False}
dump(DRAFT/'copy-index.json',{'format':'kdlock.lossless-file-copy.v1','files':files});dump(DRAFT/'audit.json',audit)
print(json.dumps({'draft':str(DRAFT),'copy_summary':audit['copy_summary'],'audit_sha256':sha(read(DRAFT/'audit.json')),'copy_index_sha256':sha(read(DRAFT/'copy-index.json'))},indent=2))
