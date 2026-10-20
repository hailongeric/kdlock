import argparse,hashlib,json,re,runpy,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('base',type=Path);a=p.parse_args();base=a.base
root=Path('/root/host_fs/kdlock');sys.dont_write_bytecode=True;sys.path.insert(0,str(root/'bench/spin_cacheline'))
import bench_runtime as rt
runpy.run_path(str(root/'bench/archive_run.py'))['idle'](base,rt.idle)
manifest=json.loads((base/'committed-source.json').read_text())['files']
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
for name,h in manifest.items():assert digest(root/name)==h,name
records=[];count=0;faults=[];generated_total=0
for task in json.loads((base/'tasks.json').read_text())['tasks']:
 assert task['exit_code'] in (0,1),task
 folder=Path(task['output']);source=json.loads((folder/'source-sha256.json').read_text())
 generated={n:h for n,h in source.items() if n not in manifest}
 if generated:
  target=base/(task['name']+'-audit-provider')
  prepared=runpy.run_path(str(root/'bench/spin_cacheline/provider/prepare.py'))['prepare'](target,root)
  prefix='bench/spin_cacheline/.build/provider/'
  expected={prefix+n:h for n,h in prepared['prepared'].items()};expected[prefix+'manifest.json']=digest(target/'manifest.json')
  assert generated==expected,task['name'];generated_total+=len(generated)
 for name,h in source.items():
  assert digest(folder/'source'/name)==h,name
  if name not in generated:assert manifest[name]==h,name
  count+=1
 for name,h in json.loads((folder/'binary-sha256.json').read_text()).items():
  path=Path(name)
  if path.is_relative_to(root):path=folder/'binaries'/path.name
  else:assert path.is_relative_to(folder),path
  assert digest(path)==h,path;count+=1
 plan=json.loads((folder/'plan.json').read_text())
 for spec in plan:
  session=folder/spec['name'];s=json.loads((session/'session.json').read_text())
  assert s['execution_status'] in ('OK','PREPARATION_FAILED'),session
  assert (task['exit_code']==0)==(s['execution_status']=='OK'),session
  retired=s.get('retired')
  if not s['drained']:
   assert s['execution_status']=='PREPARATION_FAILED' and s['cleanup_error']=='translator has not exited',session
   later=json.loads((base/'post-failure-drain.json').read_text())
   assert later['complete'] and later['final_idle'] and later['counts']['active']==0
   assert later['before_retire']['frames']==later['before_retire']['writers']==0
   retired=later['retired']
   start=min(int(line.split(',')[2])/1e6 for line in (session/'kernel.log').read_text().splitlines() if re.match(r'\d+,\d+,\d+,',line))
   for line in (base/'post-failure-dmesg.log').read_text().splitlines():
    timestamp=re.search(r'\[\s*(\d+\.\d+)\]',line)
    if timestamp and float(timestamp[1])>=start and rt.FAULT.search(line):faults.append(dict(session=str(session),line=line))
  else:assert not s.get('cleanup_error'),session
  assert retired==dict(state=2,modules=0,frames=0,writers=0),session
  for line in (session/'kernel.log').read_text().splitlines():
   if rt.FAULT.search(line):faults.append(dict(session=str(session),line=line))
  records.append(dict(task=task['name'],name=spec['name'],status=s['execution_status'],passed=s['execution_status']=='OK',original_drained=s['drained'],independent_drain_confirmed=True,jit_bodies=s.get('jit_bodies'),jit_completions=s.get('jit_completions'),retired=retired))
assert not faults,faults
record=dict(idle=True,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),checked_unix=time.time(),sessions=records,per_session_kernel_faults=faults,committed_source_hashes_checked=len(manifest),frozen_source_binary_hashes_checked=count,reconstructed_provider_files=generated_total,scope='Exact committed source plus independently reconstructed generated observation overlay; retained session outcomes, not a rewritten supervisor status')
(base/'health.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
