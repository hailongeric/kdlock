import argparse,hashlib,json,runpy,sys,time,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('base',type=Path);a=p.parse_args();base=a.base
root=Path('/root/host_fs/kdlock');sys.dont_write_bytecode=True;sys.path.insert(0,str(root/'bench/spin_cacheline'))
import bench_runtime as rt
runpy.run_path(str(root/'bench/archive_run.py'))['idle'](base,rt.idle)
for p in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
 try:name=p.read_text().strip()
 except(FileNotFoundError,ProcessLookupError):continue
 assert name not in ('ke_worker','kg_worker','ks_worker'),str(p)
records=[];count=0;faults=[]
for task in json.loads((base/'tasks.json').read_text())['tasks']:
 folder=Path(task['output']);session=json.loads((folder/'session/session.json').read_text())
 assert session['drained'],str(folder)
 for name,expected in json.loads((folder/'source-sha256.json').read_text()).items():
  assert hashlib.sha256((folder/'source'/name).read_bytes()).hexdigest()==expected,name
  count+=1
 for name,expected in json.loads((folder/'binary-sha256.json').read_text()).items():
  assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==expected,name
  count+=1
 log=folder/'session/kernel.log';assert log.is_file()
 for line in log.read_text().splitlines():
  if rt.FAULT.search(line):faults.append({'task':task['name'],'line':line})
 records.append({'name':task['name'],'exit_code':task['exit_code'],'execution_status':session['execution_status'],'drained':session['drained'],'retired':session.get('retired')})
assert not faults,faults
record={'idle':True,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'checked_unix':time.time(),'tasks':records,'per_session_kernel_faults':faults,'frozen_source_binary_hashes_checked':count,'scope':'preserved completed and failed tasks, independent idle and frozen hashes; no pass assigned to failed task'}
(base/'health.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
