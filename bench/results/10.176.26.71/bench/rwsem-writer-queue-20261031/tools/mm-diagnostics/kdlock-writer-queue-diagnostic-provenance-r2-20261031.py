#!/usr/bin/env python3
"""Exact per-arm diagnostic delta; data checks only, never source execution."""
import argparse, ast, hashlib, json, re, subprocess
from pathlib import Path
BASE_COMMIT='7814c61a0be20f5db3b9fb41b6079ef6d2938b5f'
BASE_CONFIG='b15f6ec4b235e46907978e512b2429906f1bdfa937340ac32f0f9fe76181e602'
BASE_MANIFEST='a3f46b1e1006652d2c8c25e083eab93f76d2e2e970f896457a2ca94da4193411'
BASE_DIAGNOSTIC='f4f5f671859be780ee1e6749213aadff1bf518b7'
BASE_DIAGNOSTIC_MANIFEST='84c13c193fe331185d2e1eb1c357862ffff0f664f6e27030e82b90756d2e27d1'
BASE_ADAPTER='61c364342100152b51fb266a5b5ff7c79fc3bdfdf9a36282b6faae90e052c91c'
CANDIDATE_COMMIT='9d10ae77290873df23804293f364862a2b55f385'
CANDIDATE_CONFIG='9fe4313c5fc78470b40a292e1f8f356d8e9dda03742e576e9e2b024e4f0c7a92'
CANDIDATE_MANIFEST='2169e01b6edf22edbb446634268617fe4889b47c12f6e7d91c36458c001ad02c'
CANDIDATE_DIAGNOSTIC='31d3bc28d55abcab3f8af379a0e57c6e80d7d399'
CANDIDATE_DIAGNOSTIC_MANIFEST='ed9fcddaf0b4dba2f4af3afd722cff5f184abcf6611177192d7d1666f9b5172e'
CANDIDATE_ADAPTER='8e303ba5a77799ca6151448e8689f6c29c922a86dc1f66b8a0ed65bad077b64d'
COMPATIBILITY_SCRIPT='64a72d1ae125a43fc9af7fc5902a4b91e85ab72eb50f3bca6fd8e2cac657d3e3'
BASE_ARCHIVE='6b11ca66a1c785cf4a450bf79d9700b858a56efd3260849054e1e19ebcf9d955'
FOCUSED_CHECKS='83881aff2dcef313e81c3c05f114ed7e1a7fc3dbf2e2b19a84d87dfad88a348e'
FINAL_COMMIT='de5e4f06a6d60e531a8b329d3c7f2c5335d5e707'
FINAL_CONFIG='fafaac5315038e45f150feb4d24a45913a848dfaed8e8c51236952d5087c8584'
FINAL_MANIFEST='e3948a7984167827c5dc8e6125a4db9c9b20c0d74ff8aaa1912ae73679804c60'
CONTROLLER='36db793b4c354eed620d579b5689d244c6e95e99e3d43d1a6650bcaf6423942d'
HARNESS_PATHS={'tests/kernel/mmap_writer/README.md','bench/mmap_writer/sites.py','bench/mmap_writer/client.c',
 'tests/kernel/mmap_lock/mapping.py','tests/unit/bench/test_mmap_writer_observation.py','tests/unit/bench/test_mmap_writer_return_sites.py'}
API_PATHS={'tests/kernel/mmap_lock/run.py','tests/kernel/mmap_lock/payload/module.c','tests/kernel/mmap_lock/payload/gate_waiter_layout.h','tests/kernel/mmap_lock/README.md'}
DIAGNOSTIC_PATHS={'README.md','run.py','payload/client.c'}
LEAVES={'README.md','run.py','payload/Makefile','payload/api.h','payload/client.c','payload/module.c'}
FUNCTIONS=('chain_proof','validate','reject_mutations')
TIMED_PATHS=('bench/mmap1/run.py','bench/mmap_writer/linux70.py','bench/mmap_fault/mm_platform.py',
 'bench/mmap_lock/eligibility.py','kernel_module/kd_rwsem.c','kernel_module/kd_mutex_local.c',
 'kernel_module/kd_mutex_local.h','kernel_module/kd_mutex_osq.c')

def need(value,message):
 if not value:raise RuntimeError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def read(reference):
 p=Path(reference['path']);need(p.is_file()and not p.is_symlink(),'regular provenance input required');b=p.read_bytes()
 need(sha(b)==reference['sha256'],'provenance input bytes differ: '+str(p));return b
def functions(source):
 tree=ast.parse(source);found={n.name:ast.dump(n,include_attributes=False)for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))and n.name in FUNCTIONS}
 need(set(found)==set(FUNCTIONS),'three exact observation functions required');return found
def delta(old,new):return {k:dict(before=old.get(k),after=new.get(k))for k in sorted(set(old)|set(new))if old.get(k)!=new.get(k)}
def refs(record):
 rows=[v for arm in record['arms'].values()for v in arm.values()]
 rows += [*record['return_diagnostic'].values(),record['compatibility'],record['focused_checks'],*record['failed_sites'].values(),*record['failed_api'].values(),*record.get('evidence_files',[])]
 seen={}
 for r in rows:
  need(set(r)=={'path','sha256'}and Path(r['path']).is_absolute()and'..'not in Path(r['path']).parts and re.fullmatch('[0-9a-f]{64}',r['sha256']),'exact absolute provenance reference required')
  need(r['path']not in seen or seen[r['path']]==r['sha256'],'conflicting provenance input');seen[r['path']]=r['sha256']
 return [dict(path=p,sha256=h)for p,h in seen.items()]

def validate(record,read_ref=read,git_blob=None):
 need(record.get('schema')==2 and record.get('kind')=='bounded-mm-diagnostic-delta-v2'and set(record['arms'])=={'baseline','candidate'}and
      record['controller_sha256']==CONTROLLER and record['baseline_scores_repeated']is False and record['performance_accepted']is False,'explicit diagnostic-only record required')
 for r in refs(record):need(sha(read_ref(r))==r['sha256'],'referenced provenance bytes differ')
 configs={};maps={};diagnostics={};adapters={}
 for label,r in record['arms'].items():
  need(set(r)=={'config','harness_manifest','diagnostic_manifest','mapping_adapter'},'four per-arm input references required')
  c=json.loads(read_ref(r['config']));m=json.loads(read_ref(r['harness_manifest']));d=json.loads(read_ref(r['diagnostic_manifest']))
  need(c['schema']==1 and m['schema']==1 and m['source_commit']==c['harness']['commit']and r['harness_manifest']['sha256']==c['harness']['manifest']['sha256'],'per-arm complete harness differs')
  need(d['schema']==1 and d['commit']==c['strict_diagnostic']['commit']and set(d['files'])==LEAVES and
       r['diagnostic_manifest']['sha256']==c['strict_diagnostic']['manifest']['sha256']and d['files']['run.py']==c['strict_diagnostic']['runner']['sha256'],'per-arm held diagnostic differs')
  need(re.fullmatch('[0-9a-f]{40}',m['source_commit'])and re.fullmatch('[0-9a-f]{40}',d['commit']),'fixed full source commits required')
  for path,row in m['files'].items():need(not Path(path).is_absolute()and'..'not in Path(path).parts and row['kind']=='file'and re.fullmatch('[0-9a-f]{64}',row['sha256']),'complete regular tracked-file map required')
  need(r['mapping_adapter']['sha256']==c['mapping_adapter']['sha256']and c['mapping_adapter']['base_mapping_sha256']==m['files']['tests/kernel/mmap_lock/mapping.py']['sha256'],'per-arm adapter/base source differs')
  configs[label]=c;maps[label]=m;diagnostics[label]=d;adapters[label]=read_ref(r['mapping_adapter'])
 old,new=configs['baseline'],configs['candidate'];oldrefs=record['arms']['baseline']
 need(oldrefs['config']['sha256']==BASE_CONFIG and oldrefs['harness_manifest']['sha256']==BASE_MANIFEST and
      oldrefs['diagnostic_manifest']['sha256']==BASE_DIAGNOSTIC_MANIFEST and oldrefs['mapping_adapter']['sha256']==BASE_ADAPTER and
      old['harness']['commit']==BASE_COMMIT and old['strict_diagnostic']['commit']==BASE_DIAGNOSTIC,'original baseline generation differs')
 middle_refs=record['return_diagnostic']
 need(set(middle_refs)=={'config','harness_manifest'}and middle_refs['config']['sha256']==CANDIDATE_CONFIG and
      middle_refs['harness_manifest']['sha256']==CANDIDATE_MANIFEST,'original return-diagnostic generation differs')
 middle=json.loads(read_ref(middle_refs['config']));middle_map=json.loads(read_ref(middle_refs['harness_manifest']))
 need(middle['harness']['commit']==middle_map['source_commit']==CANDIDATE_COMMIT and
      middle['strict_diagnostic']==new['strict_diagnostic']and middle['mapping_adapter']==new['mapping_adapter']and
      new['strict_diagnostic']['commit']==CANDIDATE_DIAGNOSTIC and record['arms']['candidate']['diagnostic_manifest']['sha256']==CANDIDATE_DIAGNOSTIC_MANIFEST and
      record['arms']['candidate']['mapping_adapter']['sha256']==CANDIDATE_ADAPTER and new['harness']['commit']==FINAL_COMMIT and record['arms']['candidate']['config']['sha256']==FINAL_CONFIG and record['arms']['candidate']['harness_manifest']['sha256']==FINAL_MANIFEST,'explicit API-diagnostic successor required')
 for key in set(middle)|set(new):
  if key!='harness':need(middle.get(key)==new.get(key),'API successor changed nondiagnostic configuration: '+key)
 need(set(middle)==set(new)and set(middle['harness'])==set(new['harness']),'API successor configuration shape changed')
 api_delta=delta(middle_map['files'],maps['candidate']['files'])
 need(set(api_delta)==API_PATHS and record['api_fixture_delta']==api_delta,'exact API fixture delta differs')
 need(set(middle_map['files'])==set(maps['baseline']['files'])|{'tests/unit/bench/test_mmap_writer_return_sites.py'}and
      set(maps['candidate']['files'])==set(middle_map['files'])|{'tests/kernel/mmap_lock/payload/gate_waiter_layout.h','tests/kernel/mmap_lock/README.md'},'diagnostic tracked path additions differ')
 need(set(delta(maps['baseline']['files'],middle_map['files']))==HARNESS_PATHS,'return-diagnostic intermediate delta differs')
 for key in set(old)|set(new):
  if key not in ('harness','strict_diagnostic','mapping_adapter'):need(old.get(key)==new.get(key),'nondiagnostic configuration changed: '+key)
 need(set(old)==set(new)and set(old['harness'])==set(new['harness'])and set(old['strict_diagnostic'])==set(new['strict_diagnostic'])and
      set(old['mapping_adapter'])==set(new['mapping_adapter']),'configuration shape changed')
 hd=delta(maps['baseline']['files'],maps['candidate']['files']);dd=delta(diagnostics['baseline']['files'],diagnostics['candidate']['files'])
 need(set(hd)==HARNESS_PATHS|API_PATHS and set(dd)==DIAGNOSTIC_PATHS,'diagnostic delta exceeds exact reviewed path set')
 need(functions(adapters['baseline'])==functions(adapters['candidate']),'adapter observation functions changed')
 unchanged={p:maps['baseline']['files'][p]['sha256']for p in TIMED_PATHS}
 need(all(maps['candidate']['files'][p]['sha256']==h for p,h in unchanged.items()),'timed/runtime inputs changed')
 need(record['harness_delta']==hd and record['diagnostic_delta']==dd and record['unchanged_timed_runtime']==unchanged,'recorded diagnostic delta differs')
 if git_blob:
  for path,row in middle_map['files'].items():need(sha(git_blob(CANDIDATE_COMMIT,path))==row['sha256'],'intermediate Git source differs: '+path)
  for label in ('baseline','candidate'):
   m=maps[label];d=diagnostics[label]
   for path,row in m['files'].items():need(sha(git_blob(m['source_commit'],path))==row['sha256'],'tracked Git source differs: '+label+'/'+path)
   for leaf,h in d['files'].items():need(sha(git_blob(d['commit'],'tests/kernel/mmap_writer/strict_hold/'+leaf))==h,'held diagnostic Git source differs')
   need(functions(git_blob(m['source_commit'],'tests/kernel/mmap_lock/mapping.py'))==functions(adapters[label]),'adapter differs from maintained observation functions')
 focused=json.loads(read_ref(record['focused_checks']))
 need(record['focused_checks']['sha256']==FOCUSED_CHECKS and focused.get('passed')is True and focused.get('completed')is True and
      focused.get('drained')is True and focused.get('final_idle')is True and focused.get('drain_unknown')is False and
      focused['source_commit']==CANDIDATE_COMMIT and focused['manifest_sha256']==CANDIDATE_MANIFEST and
      [z['name']for z in focused['checks']]==['test_mmap_writer_return_sites.py','test_mmap_writer_observation.py']and
      all(z['passed']is True and z['returncode']==0 and not z['remaining_processes']for z in focused['checks']),'actual focused diagnostic checks differ')
 compatibility=json.loads(read_ref(record['compatibility']))
 need(compatibility.get('kind')=='writer-sites-baseline-compatibility'and compatibility.get('replay_only')is True and compatibility.get('timing')is False and
      compatibility.get('performance_accepted')is False and compatibility.get('passed')is True and compatibility.get('completed')is True and compatibility.get('drained')is True and
      compatibility.get('final_idle')is True and compatibility.get('baseline_harness_commit')==BASE_COMMIT and
      compatibility.get('candidate_harness_commit')==CANDIDATE_COMMIT and compatibility.get('baseline_scores_repeated')is False and
      compatibility.get('legacy_argument_form_unchanged')is True and compatibility.get('observation_functions_unchanged')is True,'actual legacy-form compatibility evidence required')
 pyrows=compatibility['replayed_python_positive_chains'];crows=compatibility['replayed_c_positive_chains']
 need(compatibility['script_sha256']==COMPATIBILITY_SCRIPT and compatibility['baseline_archive_sha256']==BASE_ARCHIVE and
      compatibility['drain_unknown']is False and compatibility['complete_site_receipt_unchanged']is True and compatibility['original_receipts_unchanged']is True and
      compatibility['final_idle_scope']=='replay compiler and classifier children only'and len(pyrows)==3 and len(crows)==2 and
      sum(z['full_proc_input_retained']is True for z in pyrows)==2 and sum(z['full_proc_input_retained']is False for z in pyrows)==1 and
      {z['caller']for z in crows}=={'vm_mmap_pgoff','__vm_munmap'}and
      {(z['input'],z['caller'],z['waiter'],z['wait_return_offset'])for z in crows}==
      {(z['input'],z['caller'],z['waiter'],z['wait_return_offset'])for z in pyrows if z['full_proc_input_retained']},'exact retained three-Python/two-C compatibility scope differs')
 for label in ('baseline','candidate'):
  for name,digest in compatibility['input_sha256'][label+'_source'].items():
   need(maps[label]['files'][name]['sha256']==digest,'unchanged compatibility input differs')
   if label=='candidate':need(middle_map['files'][name]['sha256']==digest,'original9d compatibility input differs')
 for check in focused['checks']:
  name='tests/unit/bench/'+check['name'];need(middle_map['files'][name]['sha256']==maps['candidate']['files'][name]['sha256']==check['script_sha256'],'focused unit input changed')
 failed=json.loads(read_ref(record['failed_sites']['owner']));idle=json.loads(read_ref(record['failed_sites']['idle']))
 need(failed.get('state')=='FAILED'and failed.get('passed')is False and failed.get('completed')is False and failed['step']=='sites'and
      failed['arm']=='candidate'and failed['controller_sha256']==CONTROLLER and failed['config_sha256']==BASE_CONFIG and
      failed['harness_commit']==BASE_COMMIT and failed['kernel']==new['arms']['candidate']and idle.get('idle')is True and
      idle['boot_id']==failed['boot_id']and sha(read_ref(record['failed_sites']['log']))==failed['child_log_sha256'],'original failed site attempt/independent idle differ')
 need(set(record['failed_sites'])=={'owner','log','idle'}and record['failed_sites']['owner']['path']==failed['output']+'/owner.json','failed owner original path changed')
 api_failed=json.loads(read_ref(record['failed_api']['owner']));retired=json.loads(read_ref(record['failed_api']['retirement']))
 need(set(record['failed_api'])=={'owner','log','retirement'}and api_failed.get('state')=='FAILED'and api_failed.get('passed')is False and
      api_failed.get('completed')is False and api_failed['step']=='api'and api_failed['arm']=='candidate'and
      api_failed['config_sha256']==CANDIDATE_CONFIG and api_failed['harness_commit']==CANDIDATE_COMMIT and api_failed['controller_sha256']==CONTROLLER and
      api_failed['kernel']==new['arms']['candidate']and record['failed_api']['owner']['path']==api_failed['output']+'/owner.json'and
      sha(read_ref(record['failed_api']['log']))==api_failed['child_log_sha256']and retired.get('passed')is True and
      retired.get('completed')is True and retired.get('final_idle')is True and retired.get('drained')is True and retired.get('returncode')==0 and
      retired.get('failed_evidence_unchanged')is True and retired.get('worker_tasks')==[]and retired['boot_id']==api_failed['boot_id']and
      retired['failed_input_sha256']['owner.json']==record['failed_api']['owner']['sha256']and retired['failed_input_sha256']['controller.log']==record['failed_api']['log']['sha256'],'original API failure/separate normal retirement differs')
 return dict(configs=configs,harness_manifests=maps,diagnostic_manifests=diagnostics,harness_delta=hd,diagnostic_delta=dd,
             unchanged_timed_runtime=unchanged,compatibility=compatibility,focused_checks=focused,failed_sites=failed,failed_api=api_failed,failed_api_retirement=retired,api_fixture_delta=api_delta,return_diagnostic_manifest=middle_map)

def main():
 p=argparse.ArgumentParser(description='Source-host-only exact diagnostic provenance builder')
 for n in ('spec','trusted-checkout','output'):p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--spec-sha256',required=True);x=p.parse_args();spec=json.loads(read(dict(path=str(x.spec),sha256=x.spec_sha256)))
 local=spec['local_files'];r=spec['record'];need(not x.output.exists(),'new output required')
 def source(ref):return read(dict(path=local[ref['path']],sha256=ref['sha256']))
 maps={label:json.loads(source(z['harness_manifest']))for label,z in r['arms'].items()};diags={label:json.loads(source(z['diagnostic_manifest']))for label,z in r['arms'].items()}
 middle_map=json.loads(source(r['return_diagnostic']['harness_manifest']))
 r['api_fixture_delta']=delta(middle_map['files'],maps['candidate']['files'])
 r['harness_delta']=delta(maps['baseline']['files'],maps['candidate']['files']);r['diagnostic_delta']=delta(diags['baseline']['files'],diags['candidate']['files'])
 r['unchanged_timed_runtime']={p:maps['baseline']['files'][p]['sha256']for p in TIMED_PATHS}
 # cat-file batches exact objects into a stream; it never executes source or compiles.
 cache={}
 allmaps=[*maps.values(),middle_map]
 for commit in {m['source_commit']for m in allmaps}|{d['commit']for d in diags.values()}:
  wanted=set(next((m['files']for m in allmaps if m['source_commit']==commit),{}))
  wanted|={'tests/kernel/mmap_writer/strict_hold/'+leaf for d in diags.values()if d['commit']==commit for leaf in d['files']}
  with subprocess.Popen(['git','-C',str(x.trusted_checkout),'cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)as child:
   for path in sorted(wanted):
    child.stdin.write((commit+':'+path+'\n').encode());child.stdin.flush();header=child.stdout.readline().split();need(len(header)==3 and header[1]==b'blob','exact Git blob missing');size=int(header[2]);data=child.stdout.read(size);need(len(data)==size and child.stdout.read(1)==b'\n','truncated Git blob');cache[commit,path]=data
   child.stdin.close();need(child.wait(timeout=60)==0,'Git source read failed')
 validate(r,source,lambda commit,path:cache[commit,path]);x.output.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
 print(json.dumps(dict(path=str(x.output),sha256=sha(x.output.read_bytes()),harness_paths=len(r['harness_delta']),diagnostic_paths=len(r['diagnostic_delta']),performance_accepted=False)))
if __name__=='__main__':main()
