"""Read-only saved-receipt audit. No project import, compilation or VM action."""
from pathlib import Path, PurePosixPath
import hashlib, json, sys, tarfile
r=Path(sys.argv[1]).resolve()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def load(n): return json.loads((r/n).read_text())
i=load('copy-index.json'); closure=load('collection.json')
assert i['count']==216 and i['bytes']==10061323 and closure['status']=='COMPLETE'
assert sha(r/'copy-index.json')=='a8a01ccbf66791bec294f2f285f0866f22a8f52641596036c1a3220426706e86'
before=load('.collection/inventory-before.json'); after=load('.collection/inventory-after.json')
assert before['files']==after['files'] and before['directories']==after['directories']
assert before['count']==after['count']==i['count']
for row in i['files']:
 p=PurePosixPath(row['path']); assert not p.is_absolute() and '..' not in p.parts
 f=r/row['path']; assert f.is_file() and not f.is_symlink() and f.stat().st_size==row['bytes'] and sha(f)==row['sha256']
 assert before['files'][row['name']]=={'bytes':row['bytes'],'identity':row['identity'],'path':row['guest_path'],'sha256':row['sha256']}
with tarfile.open(r/'.collection/copy.tar') as stream:
 members=list(stream); assert len(members)==216 and {m.name for m in members}=={x['name'] for x in i['files']}
 for m in members:
  assert m.isfile() and m.name in {x['name'] for x in i['files']}
  row=next(x for x in i['files'] if x['name']==m.name)
  assert m.size==row['bytes'] and hashlib.sha256(stream.extractfile(m).read()).hexdigest()==row['sha256']
old=load('payload/attempt01/receipts/result.json'); good=load('payload/checks/result.json')
assert sha(r/'payload/attempt01/receipts/result.json')=='223392b879bd1aaad6ffc3e40f322706be8bd94039abd0a50c16afe238ffa37c'
assert sha(r/'payload/checks/result.json')=='cb3871c710e7085c3c9ae4d2cc9e1dcd41b3e5c8d4c3ebb3fb8fbf309b6a3693'
assert old['status']=='FAILED_OR_INCOMPLETE' and len(old['commands'])==37
assert all(x['returncode']==0 for x in old['commands'][:36]) and old['commands'][-1]['returncode']==1
assert old['commands'][-1]['label']=='source-boundary-eight'
assert good['status']=='AFFECTED_MODULES_CLIENT_AND_BASIC_CHECKS_COMPLETE'
assert [(x['label'],x['returncode']) for x in good['commands']]==[('corrected-source-boundary-eight',0),('linked-gs-five',0)]
for base,record in [('payload/attempt01/receipts',old),('payload/checks',good)]:
 for row in record['commands']: assert sha(r/base/(row['label']+'.log'))==row['log_sha256']
assert good['prior_result_sha256']==sha(r/'payload/attempt01/receipts/result.json')
assert good['checks']=={'linked_gs_skips':0,'linked_gs_tests':5,'new_runner_ast':2,'new_runner_ast_reexecuted':False,'source_boundary_skips':0,'source_boundary_tests':8,'unselected_baseline_reexecuted':False}
assert good['core_pins_after']==old['core_pins_before'] and len(good['core_pins_after'])==16
for new,prev in [('protected_after','protected_before'),('kernel_source_after','kernel_source_before'),('boot_after','boot_before')]: assert good[new]==old[prev]
for label,mod in old['modules'].items():
 for kind in ('signed','unsigned'): assert sha(r/'payload/binaries'/(label+'-'+kind+'.ko'))==mod[kind]['sha256']
assert len(old['modules'])==5 and sha(r/'payload/binaries/client')==old['client']['sha256']=='bae90760f57f3930e1ff48443140eb096ea316c1fed00ae1840127f6985a4cd2'
assert good['client_mode']==old['client_mode']=='exact_prior_binary_reuse'
assert good['unselected_syscall_baseline']==old['client_reuse']['baseline']
manifest=load('payload/attempt01/transport/source-sha256.json'); corrected=load('payload/checks-input/source-sha256.json')
assert len(manifest)==len(corrected)==140 and [n for n in manifest if manifest[n]!=corrected[n]]==['tests/test_source_boundaries.py']
with tarfile.open(r/'payload/attempt01/transport/source.tar') as stream:
 members=list(stream); assert len(members)==140 and {m.name for m in members}==set(manifest)
 for m in members:
  assert m.isfile(); data=stream.extractfile(m).read(); item=manifest[m.name]
  assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256']
  assert sha(r/'payload/attempt01/input'/m.name)==item['sha256']
a=(r/'payload/attempt01/input/tests/test_source_boundaries.py').read_bytes()
b=(r/'payload/checks-input/test_source_boundaries.py').read_bytes()
assert b==a.replace(b'RuntimeExit(ExitKind.LOCK_OPERATION,',b'RuntimeExit(int(ExitKind.LOCK_OPERATION),').replace(b'0x1000, ExitPhase.TARGET_READY),',b'0x1000, int(ExitPhase.TARGET_READY)),')
assert hashlib.sha256(b).hexdigest()==good['corrected_test_sha256']
for record in [old,good]:
 assert record['linked_build_id']=='a33dd4d11d0f0c6649107507e685b6e86e716c1a'
 assert record['kernel_core_git_head']=='0d42063ead37dc8fc1631fa56c8348890ede9c5f'
 assert record['running_candidate_proof'] is False
for name in ['identity_before','identity_after']:
 v=good[name]; assert v['boot']=='afb0c5cd-96b7-488b-bcb4-4a31cbb4e50e' and v['release']=='7.0.0-38-kdlock1' and v['taint']=='0' and not v['busy'] and not v['blocked']
assert good['gs_checks']['tests']==5 and not good['gs_checks']['running_proof']
result={'status':'SAVED_BYTES_AND_AFFECTED_RECEIPTS_VERIFIED','scope':'Offline standard-library saved-file audit only. No test/build/VM execution.', 'guest_payload_files':i['count'],'guest_payload_bytes':i['bytes'],'collection_index_sha256':sha(r/'copy-index.json'),'original_failed_receipt_sha256':sha(r/'payload/attempt01/receipts/result.json'),'continuation_receipt_sha256':sha(r/'payload/checks/result.json'),'original_commands':37,'original_rc0_commands':36,'continuation_commands':2,'checks':good['checks'],'warnings':{k:v['diagnostics'] for k,v in old['modules'].items()},'linked_build_id':good['linked_build_id'],'source_git_head':old['source_git_head'],'corrected_test_git_head':good['corrected_test_git_head'],'client_sha256':old['client']['sha256'],'client_mode':old['client_mode'],'prior_baseline_reexecuted':False,'native_or_generated_execution_established':False,'raw_transport_inventory_and_archive_verified':True,'protected_source_and_installed_maps_unchanged':True}
print(json.dumps(result,indent=2,sort_keys=True))
