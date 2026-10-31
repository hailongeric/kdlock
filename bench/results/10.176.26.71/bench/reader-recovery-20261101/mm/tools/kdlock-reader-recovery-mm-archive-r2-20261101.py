#!/usr/bin/env python3
"""Preserve one complete fresh MM arm with maintained archive_run; no timing."""
import argparse,datetime,hashlib,importlib.util,json,os,re,shutil,signal,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
CONFIG='6d950639b6b9ae30049b36fa26f88a2c584418b7bd70a2b96f8a96afb0239003'
STEP='36db793b4c354eed620d579b5689d244c6e95e99e3d43d1a6650bcaf6423942d'
COORDINATOR='12652d93708db2f28b7a15f3de8b4aa061734f7165ef99589a3e2f071dc5775a'
STEPS=('sites','api','mapping','faults','completed','strict-hold','mmap1-identity','mmap1-measure','endpoint')
POLICY='mmap-functional-held-writer-v1'
COUNTS=[*range(1,9),*range(12,61,4)]
MUTATIONS=['different_lock','wrong_caller_return','wrong_wait_return','wrong_adapter_return','running_task','other_wait_channel','rescheduled_task','missing_chain','missing_writer_proof']
ROOT=Path('/root/host_fs/kdlock')
FAULT=re.compile(r'BUG:|\bWARNING:|kernel panic|double fault|soft lockup|hard LOCKUP|unable to handle|general protection fault|Oops:|\[KD_JIT\]\[ERROR\]',re.I)
def need(v,m):
 if not v:raise RuntimeError(m)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def load(p):return json.loads(Path(p).read_bytes())
def checked(r):
 p=Path(r['path']);need(p.is_file()and not p.is_symlink()and sha(p)==r['sha256'],'input differs: '+str(p));return load(p)
def save(p,x):
 t=p.with_name('.'+p.name+'.tmp')
 with t.open('w')as f:json.dump(x,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
 t.replace(p)
def module(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bindings',type=Path,required=True);p.add_argument('--bindings-sha256',required=True);x=p.parse_args()
 actual=checked(dict(path=x.bindings,sha256=x.bindings_sha256));c=checked(actual['config'])
 need(actual.get('schema')==1 and actual['config']['sha256']==CONFIG and c['eligibility_policy']==POLICY and
      actual['arm']in c['arms']and set(actual['owners'])==set(STEPS),'one complete explicit-policy arm required')
 label=actual['arm'];arm=c['arms'][label];boot=actual['boot_id'];h=c['harness'];base=Path(c['campaign'])/label
 control=Path(c['campaign'])/(label+'-archive-control');archives=Path(c['campaign'])/(label+'-archives');keep=base/'preservation-inputs'
 need(os.geteuid()==0 and sys.executable==c['python']and os.uname().release==arm['release'],'intended guest/Python/kernel required')
 def boot_check():need(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot and
      [w for w in Path('/proc/cmdline').read_text().split()if w.startswith('kd_mmap=')]==['kd_mmap=on'],'same KD boot required')
 manifest=checked(h['manifest'])
 def recipe_check():
  need(ROOT.is_mount()and os.path.samefile(ROOT,h['source'])and os.statvfs(ROOT).f_flag&os.ST_RDONLY,'same readonly common harness required')
  need(sha(h['manifest']['path'])==h['manifest']['sha256']and manifest['source_commit']==h['commit'],'common harness manifest differs')
  for n,r in manifest['files'].items():
   need(not Path(n).is_absolute()and'..'not in Path(n).parts and r['kind']=='file'and sha(ROOT/n)==r['sha256'],'common harness bytes differ: '+n)
 boot_check();recipe_check();need(base.is_dir()and not any(z.exists()for z in(control,archives,keep,base/'final-health.json')),'preserve existing attempts')
 control.mkdir();shutil.copyfile(__file__,control/'controller.py');shutil.copyfile(x.bindings,control/'bindings.json');shutil.copyfile(actual['config']['path'],control/'config.json')
 owner=dict(schema=1,state='ADMISSION',completed=False,idle=False,drain_unknown=False,arm=label,boot_id=boot,kernel=arm,
  harness_commit=h['commit'],config_sha256=CONFIG,script_sha256=sha(__file__),bindings_sha256=x.bindings_sha256,
  step_owners=actual['owners'],eligibility_policy=POLICY,performance_accepted=False,automatic_retry=False,started=time.time())
 child=None
 def persist():save(control/'owner.json',owner)
 def interrupted(signum,frame):raise InterruptedError('archive interrupted; child retained')
 for sig in(signal.SIGINT,signal.SIGTERM,signal.SIGHUP):signal.signal(sig,interrupted)
 persist()
 try:
  sys.path.insert(0,str(ROOT/'bench/spin_cacheline'));archive=module('writer_queue_archive',ROOT/'bench/archive_run.py')
  from bench_runtime import idle as common_idle
  archive.idle(base,common_idle)
  bundle_path=Path(arm['bundle']);bundle=checked(dict(path=bundle_path/'manifest.json',sha256=actual['bundle_manifest_sha256']))
  need(bundle['variant']==arm['variant']and bundle['runtime_policy']['mmap_mode']=='on','selected KD bundle differs')
  inputs=checked(c['application']['inputs']);checked(c['application']['preparation'])
  original_prep=Path(c['application']['inputs']['path']).parent
  kernel_files={bundle[k+'_root']+'/'+n:v for k in('source','build')for n,v in bundle[k+'_files'].items()}
  wanted={};owners={};results={};logical={}
  def want(path,digest):
   path=str(path);need(Path(path).is_absolute()and'..'not in Path(path).parts,'absolute original binding required')
   need(path not in wanted or wanted[path]==digest,'original path changed within arm: '+path);wanted[path]=digest
  for step in STEPS:
   op=Path(actual['owners'][step]['path']);o=checked(actual['owners'][step]);rp=Path(o['result']['path']);r=checked(o['result'])
   need(op==Path(o['output'])/'owner.json'and op.parent.parent==base and rp.parent==op.parent/'run','explicit logical step path differs')
   need(o.get('completed')is True and o.get('passed')is True and o.get('drained')is True and o.get('final_idle')is True and
        o.get('drain_unknown')is False and o.get('state')=='COMPLETE'and o['controller_sha256']==STEP and o['config_sha256']==CONFIG and
        o['step']==step and o['arm']==label and o['boot_id']==boot and o['kernel']==arm and
        o['harness_commit']==h['commit']and o['harness_manifest_sha256']==h['manifest']['sha256']and
        o['bundle_manifest_sha256']==actual['bundle_manifest_sha256']and(step=='endpoint'or o['child_returncode']==0),'incomplete or changed logical step: '+step)
   need(r.get('captured')is True if step=='sites'else r.get('passed')is True and r.get('drained')is True,'runner result incomplete: '+step)
   logical[step]=dict(owner=str(op.relative_to(base)),result=str(rp.relative_to(base)))
   owners[step]=o;results[step]=r;want(op,actual['owners'][step]['sha256']);want(rp,o['result']['sha256'])
   for path,digest in o['prerequisite_bindings'].items():want(path,digest)
   if step!='endpoint':want(op.parent/'controller.log',o['child_log_sha256'])
   for prior,reference in o['prerequisite_owners'].items():need(reference==actual['owners'][prior],'logical prerequisite uses another attempt')
   for path,digest in r.get('files',{}).items():want(path,digest)
  grid=results['mmap1-measure'];measure=owners['mmap1-measure'];ep=results['endpoint'];eo=owners['endpoint']
  need(grid.get('state')=='COMPLETE'and grid.get('final_idle')is True and grid.get('single_round')is True and grid.get('planned')==42 and
       grid.get('accepted')is False and grid['binary_sha256']==c['application']['binary_sha256']and
       [(s['model'],s['workers'],s['round'])for s in grid['sessions']]==[(m,n,0)for m in('threads','processes')for n in COUNTS]and
       all(s.get('passed')is True and s.get('drained')is True and s.get('scored')is True and s.get('instrumentation')=='none'for s in grid['sessions']),'exact one-round grid differs')
  mapping=results['mapping'];held=results['strict-hold']
  need(mapping.get('eligibility_policy')=='mmap-functional-v1'and mapping.get('writer_observation')in('observed','inconclusive')and
       [z['name']for z in mapping['cases']]==['00-scope-1','01-cycle-1','02-cycle-16','03-lifetime-1','04-lifetime-16','05-exit-1'],'functional mapping plan differs')
  need(held.get('diagnostic')=='same-mm-held-writer-v1'and held.get('final_idle')is True and held.get('source_unchanged')is True and
       held['diagnostic_commit']==c['strict_diagnostic']['commit']and[case['operation']for case in held['cases']]==['mmap','munmap']and
       all(case.get('passed')is True and case['rejected_mutations']==MUTATIONS for case in held['cases']),'fresh held-writer witnesses incomplete')
  policy=checked(measure['measurement_policy']);want(measure['measurement_policy']['path'],measure['measurement_policy']['sha256'])
  need(policy['eligibility_policy']==POLICY and policy['measurement_result']==measure['result']and policy['mapping_owner']==actual['owners']['mapping']and
       policy['strict_hold_owner']==actual['owners']['strict-hold']and policy['fresh_same_boot_witnesses']is True and
       policy['raw_measurement_changed']is False and policy['measurement_repeated']is False and policy['performance_accepted']is False,'measurement policy differs')
  need(ep.get('completed')is True and ep.get('host_strict_qualified')is True and ep.get('grid_points')==42 and ep.get('rounds_per_point')==1 and
       ep['measure_owner']==actual['owners']['mmap1-measure']and ep['measure_result']==measure['result']and
       ep['measurement_policy']==measure['measurement_policy'],'completed immediate endpoint differs')
  after=load(Path(eo['output'])/'inputs/host-before.json');before=load(Path(measure['output'])/'inputs/host-before.json')
  reference=load(Path(measure['output'])/'inputs/host-reference.json');captured=datetime.datetime.fromisoformat(after['captured_utc'])
  delay=captured.timestamp()-measure['child_finished']
  need(0<=delay<=300 and delay==ep['capture_delay_from_child_exit_seconds']and
       sha(Path(eo['output'])/'inputs/host-before.json')==ep['host_after_sha256']and
       sha(Path(measure['output'])/'inputs/host-before.json')==ep['host_before_sha256'],'original endpoint capture differs')
  platform=module('writer_queue_archive_platform',ROOT/'bench/mmap_fault/mm_platform.py')
  need(platform.compare_host(reference,after,captured,c['pool']['snapshot'],True)==ep['comparison_to_reference']and
       platform.compare_host(before,after,captured,c['pool']['snapshot'],True)==ep['comparison_to_before'],'original endpoint replay differs')
  sequence=checked(actual['sequence'])
  need(sequence.get('completed')is True and sequence.get('coordinator_sha256')==COORDINATOR and
       sequence['controller_sha256']==STEP and sequence['config_sha256']==CONFIG and
       sequence['arm']==label and sequence['boot_id']==boot and sequence['owners']==actual['owners']and
       [r['step']for r in sequence['steps']]==list(STEPS)and
       all(r['completed']and r['owner']==actual['owners'][r['step']]for r in sequence['steps']),
       'completed sequential arm and immediate endpoint differ')
  need(actual['sequence_controller']['sha256']==COORDINATOR and
       sha(actual['sequence_controller']['path'])==COORDINATOR,'exact source-host coordinator differs')
  for r in(actual['sequence'],actual['sequence_controller']):want(r['path'],r['sha256'])
  for r in(actual['config'],h['manifest'],c['mapping_adapter'],c['identity_adapter'],c['strict_diagnostic']['runner'],c['strict_diagnostic']['manifest']):want(r['path'],r['sha256'])
  dm=checked(c['strict_diagnostic']['manifest']);diagroot=Path(c['strict_diagnostic']['runner']['path']).parent
  need(dm['commit']==c['strict_diagnostic']['commit']and set(dm['files'])=={'README.md','run.py','payload/Makefile','payload/api.h','payload/client.c','payload/module.c'},'six exact diagnostic source files required')
  for leaf,digest in dm['files'].items():want(diagroot/leaf,digest)
  keep.mkdir();aliases={};copied=[];delegated={}
  def copy_file(source,relative,digest,alias=True):
   source=Path(source);target=base/relative;need(source.is_file()and sha(source)==digest,'original changed: '+str(source));target.parent.mkdir(parents=True,exist_ok=True)
   if target.exists():need(target.is_file()and sha(target)==digest,'copy collision')
   else:
    with source.open('rb')as original,target.open('xb')as saved:shutil.copyfileobj(original,saved)
   need(sha(target)==digest==sha(source),'copy changed');copied.append(dict(source=str(source),member=str(relative),sha256=digest))
   if alias:need(str(source)not in aliases or aliases[str(source)]==str(relative),'alias collision');aliases[str(source)]=str(relative)
  copy_file(bundle_path/'manifest.json',Path('preservation-inputs/kernel-bundle/manifest.json'),actual['bundle_manifest_sha256'])
  for n,digest in bundle['bundle_files'].items():
   need(not Path(n).is_absolute()and'..'not in Path(n).parts,'bundle relative path differs');copy_file(bundle_path/n,Path('preservation-inputs/kernel-bundle')/n,digest)
  copy_file(actual['config']['path'],Path('preservation-inputs/config.json'),CONFIG)
  copy_file(h['manifest']['path'],Path('preservation-inputs/harness-manifest.json'),h['manifest']['sha256'])
  copy_file(c['strict_diagnostic']['manifest']['path'],Path('preservation-inputs/diagnostic-manifest.json'),c['strict_diagnostic']['manifest']['sha256'])
  for leaf,digest in dm['files'].items():copy_file(diagroot/leaf,Path('preservation-inputs/diagnostic-source')/leaf,digest)
  for path,digest in sorted(wanted.items()):
   source=Path(path)
   if source.is_relative_to(base):need(source.is_file()and sha(source)==digest,'retained arm input changed: '+path)
   elif source.is_relative_to(ROOT)and str(source.relative_to(ROOT))in manifest['files']:
    need(manifest['files'][str(source.relative_to(ROOT))]['sha256']==digest,'tracked common source differs');delegated[path]=dict(sha256=digest,kind='common-harness-manifest')
   elif source.is_relative_to(original_prep):need(sha(source)==digest,'original preparation differs');delegated[path]=dict(sha256=digest,kind='authenticated-original-preparation-support')
   elif path in kernel_files:need(kernel_files[path]==digest,'kernel identity differs');delegated[path]=dict(sha256=digest,kind='runner-verified-kernel-file')
   elif path in inputs['dependencies']:need(inputs['dependencies'][path]==digest,'external dependency differs');delegated[path]=dict(sha256=digest,kind='runner-verified-tool-library')
   elif path not in aliases:copy_file(source,Path('preservation-inputs/external')/(digest+'-'+source.name),digest)
   else:need(sha(base/aliases[path])==digest,'preserved alias differs')
  for row in actual.get('extra_files',[]):
   name=row['name'];need(re.fullmatch('[A-Za-z0-9_.-]+',name)and name not in('.','..'),'simple metadata name required');copy_file(row['path'],Path('preservation-inputs/control-metadata')/name,row['sha256'],False)
  copy_file(x.bindings,Path('preservation-inputs/archive-bindings.json'),x.bindings_sha256,False);copy_file(__file__,Path('preservation-inputs/archive-controller.py'),sha(__file__),False)
  amap=dict(schema=1,arm=label,boot_id=boot,harness_commit=h['commit'],config_sha256=CONFIG,eligibility_policy=POLICY,
   config_member='preservation-inputs/config.json',bundle_member='preservation-inputs/kernel-bundle/manifest.json',
   harness_manifest_member='preservation-inputs/harness-manifest.json',diagnostic_manifest_member='preservation-inputs/diagnostic-manifest.json',
   measurement_policy_member=str(Path(measure['measurement_policy']['path']).relative_to(base)),owners=actual['owners'],logical_steps=logical,aliases=aliases,performance_accepted=False)
  save(control/'alias-map.json',amap);save(keep/'alias-map.json',amap)
  preservation=dict(schema=1,arm=label,boot_id=boot,harness_commit=h['commit'],config_sha256=CONFIG,files=copied,dependencies=delegated,
   alias_map_sha256=sha(control/'alias-map.json'),original_paths_retained=True,performance_accepted=False)
  save(keep/'preservation-map.json',preservation);shutil.copyfile(keep/'preservation-map.json',control/'preservation-map.json')
  recipe_check();archive.idle(base,common_idle);boot_check()
  log=subprocess.run(['dmesg','--color=never'],check=True,capture_output=True,timeout=15);need(not FAULT.search(log.stdout.decode(errors='replace')),'kernel fault in final health');(keep/'final-kernel.log').write_bytes(log.stdout)
  save(base/'final-health.json',dict(schema=1,idle=True,boot_id=boot,arm=label,kernel=arm,checked=time.time(),harness_commit=h['commit'],
   config_sha256=CONFIG,step_owners=actual['owners'],endpoint_sha256=eo['result']['sha256'],preservation_map_sha256=sha(keep/'preservation-map.json'),performance_accepted=False,
   scope='Actual archive-time idle; timing qualification remains the original immediate endpoint'))
  argv=[c['python'],str(ROOT/'bench/archive_run.py'),'--base',str(base),'--output',str(archives),'--health',str(base/'final-health.json'),
   '--kernel-variant',arm['variant'],'--kernel-source',arm['build'],'--kernel-baseline',arm['bundle'],'--timeout-seconds','3600']
  selected={Path(o['output']).name for o in owners.values()}
  need(len(selected)==len(STEPS),'one distinct attempt per logical step required')
  for step,o in owners.items():argv+=['--group',('mmap1'if step=='mmap1-measure'else'checks')+'='+Path(o['output']).name]
  for path in sorted(base.iterdir()):
   if path.is_dir()and path.name not in selected|{'preservation-inputs'}:argv+=['--group','attempts='+path.name]
  argv+=['--group','inputs=preservation-inputs']
  owner.update(state='ARCHIVING',argv=argv,drain_unknown=True,alias_map_sha256=sha(control/'alias-map.json'),preservation_map_sha256=sha(keep/'preservation-map.json'),final_health_sha256=sha(base/'final-health.json'));persist()
  with(control/'archive.log').open('xb')as stream:
   child=subprocess.Popen(argv,cwd=ROOT,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True);owner['pid']=child.pid;persist();code=child.wait(timeout=3660)
  owner['child_returncode']=code;persist();need(code==0,'archive failed; preserve attempt')
  result=load(archives/'archives.json');need(result.get('completed')is True and result.get('guest_idle')is True and result['boot_id']==boot and result['guest_base']==str(base)and result['kernel_variant']==arm['variant'],'archive completion differs')
  recipe_check();archive.idle(base,common_idle);boot_check();need(all(sha(r['path'])==r['sha256']for r in actual['owners'].values()),'logical owner changed')
  owner.update(state='COMPLETE',completed=True,idle=True,drain_unknown=False,archives_sha256=sha(archives/'archives.json'),input_inventory_sha256=sha(archives/'input-inventory.json'),finished=time.time())
 except BaseException as error:
  owner.update(state='FAILED',error=repr(error),finished=time.time())
  if child is not None:owner.update(child_returncode=child.poll(),drain_unknown=True)
  raise
 finally:persist()
 print(json.dumps(owner),flush=True)
if __name__=='__main__':main()
