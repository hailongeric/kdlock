"""Guest controller: leased compiler pairs without publication or workload."""
from pathlib import Path
import hashlib
import json
import os
import resource
import runpy
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode=True
request=json.loads(sys.stdin.buffer.read())
root=Path(request['candidate']['root']);baseline=Path('/root/kdlock-inputs/shape-4506f6e4')
assert os.geteuid()==0 and os.uname().release=='7.0.0-38-kdscope5'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==request['boot']['boot_id']
assert request['boot']['verification']['running_build_id']=='5f2fce72a33480f6e79a79b374b21a0db377ecd1'
assert 'kd_mmap=off' in Path('/proc/cmdline').read_text().split()
sys.path.insert(0,str(root/'bench/spin_cacheline'));import bench_runtime as rt
sys.path.insert(0,str(root/'disassem'));import device_session
idle=runpy.run_path(str(root/'bench/archive_run.py'))['idle'];idle(root,rt.idle)
py='/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
assert sys.executable==py
os.sched_setaffinity(0,{63})
assert shutil.disk_usage('/').free>1024**3 and shutil.disk_usage('/mnt/kdlock-builds2').free>2*1024**3
out=Path('/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/core-symbols-26337db1-compiler');out.mkdir(exist_ok=False)
helper=bytes.fromhex(request['child_hex'])
assert hashlib.sha256(helper).hexdigest()==request['child_sha256']
(out/'compiler-child.py').write_bytes(helper)
module=Path(request['provider']['provider'])
assert rt.digest(module)==request['provider']['provider_sha256']=='a9e121b1dfae464e3199b8d6cec07d7539f3aedac62d31a3affd680b1b629f65'
assert not Path('/sys/module/kdlock_km').exists()
for source in (root,baseline):
 manifest=json.loads((source/'source-sha256.json').read_text())
 for name,wanted in manifest.items():assert rt.digest(source/name)==wanted,(str(source),name)
assert rt.digest(root/'source-sha256.json')==request['candidate']['source_manifest_sha256']
assert rt.digest(root/'source-state.json')==request['candidate']['source_state_sha256']
for directory in ('include','kernel_module'):
 old=json.loads((baseline/'source-sha256.json').read_text());new=json.loads((root/'source-sha256.json').read_text())
 assert {name:value for name,value in old.items() if name.startswith(directory+'/')}=={name:value for name,value in new.items() if name.startswith(directory+'/')}
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PATH=str(Path(py).parent)+':/usr/sbin:/usr/bin:/sbin:/bin')
env.pop('KD_DEVICE_FD',None);env.pop('KD_JIT_BODY_WITNESS',None)
result=dict(passed=False,source=request['candidate'],baseline_commit='4506f6e46394133e439f68a04d6fde38aea0885f',
 boot=request['boot'],provider_sha256=rt.digest(module),provider_reused=True,child_sha256=request['child_sha256'],
 no_publication=True,no_workload=True,history='fresh empty CALL and IJ tables for each selected MM root',
 repetitions=1,affinity=sorted(os.sched_getaffinity(0)),pairs=[],module_loaded=False,retirement=None)
def save():(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
def state():
 data=Path('/proc/kallsyms').read_bytes();modules=Path('/proc/modules').read_bytes()
 return dict(table_sha256=hashlib.sha256(data).hexdigest(),table_bytes=len(data),table_lines=data.count(b'\n'),
  modules=modules.decode(),modules_sha256=hashlib.sha256(modules).hexdigest(),source=rt.status(),registry=rt.registry())
save()
subprocess.run(['insmod',str(module),'bench_quiet=1','rwsem_provider_demand=0','service_trace=0','jit_timing=0'],check=True,timeout=20)
result['module_loaded']=True;save()
try:
 result['parameters']=rt.parameters()
 assert result['parameters']['rwsem_provider_demand']=='N'
 result['provider_srcversion']=Path('/sys/module/kdlock_km/srcversion').read_text().strip()
 assert result['provider_srcversion']==subprocess.check_output(['modinfo','-F','srcversion',str(module)],text=True,timeout=10).strip()
 result['before']=state();save()
 assert result['before']['registry']==[]
 for name,entry in (('mmap',0xffffffff817b6f68),('munmap',0xffffffff8181c73b)):
  pair=dict(name=name,entry=entry,arms=[])
  result['pairs'].append(pair);save()
  for kind,source in (('baseline',baseline),('candidate',root)):
   directory=out/name/kind;(directory/'asm').mkdir(parents=True)
   for history in ('callee_table.txt','ij_table.txt'):(directory/'asm'/history).write_text('')
   telemetry=directory/'lookup.json'
   argv=['taskset','-c','63',py,str(out/'compiler-child.py'),str(source),hex(entry),str(telemetry)]
   stdout=(directory/'stdout').open('xb');stderr=(directory/'stderr').open('xb')
   start=time.perf_counter_ns()
   child=subprocess.Popen(argv,cwd=directory,env=env,stdout=stdout,stderr=stderr)
   arm=dict(kind=kind,source=str(source),argv=argv,pid=child.pid,state='RUNNING')
   pair['arms'].append(arm);save()
   # The outer controller has a finite command deadline. On a timeout it keeps
   # the process and provider intact for diagnosis, rather than assuming drain.
   deadline=time.monotonic()+180
   while True:
    waited,status,usage=os.wait4(child.pid,os.WNOHANG)
    if waited:
     break
    if time.monotonic()>=deadline:
     arm['state']='DEADLINE_WITH_LIFETIME_RETAINED';save()
     raise RuntimeError('compiler deadline; retain provider and child for diagnosis')
    time.sleep(0.05)
   elapsed=time.perf_counter_ns()-start
   assert waited==child.pid
   child.returncode=os.waitstatus_to_exitcode(status)
   stdout.close();stderr.close()
   arm.update(state='EXITED',returncode=child.returncode,wall_ns=elapsed,
    user_ns=round(usage.ru_utime*1e9),system_ns=round(usage.ru_stime*1e9),maxrss_kib=usage.ru_maxrss,
    minor_faults=usage.ru_minflt,major_faults=usage.ru_majflt,voluntary_switches=usage.ru_nvcsw,involuntary_switches=usage.ru_nivcsw)
   arm['telemetry']=json.loads(telemetry.read_text())
   arm['artifacts']={leaf:dict(bytes=(directory/'asm'/leaf).stat().st_size,sha256=rt.digest(directory/'asm'/leaf))
    for leaf in ('jit.S','jit.o','jit.bin','bin.txt') if (directory/'asm'/leaf).exists()}
   arm['stdout_sha256']=rt.digest(directory/'stdout');arm['stderr_sha256']=rt.digest(directory/'stderr')
   arm['coverage']=[line for line in (directory/'stderr').read_text().splitlines() if 'reason=DECODED_TEXT_COVERAGE ' in line]
   arm['source_after']=rt.status();save()
   assert child.returncode==0 and len(arm['artifacts'])==4,arm
  first,second=pair['arms']
  pair['artifacts_identical']=first['artifacts']==second['artifacts']
  pair['lookup_results_identical']=[{key:record[key] for key in ('name','default','address')} for record in first['telemetry']['requests']]==[{key:record[key] for key in ('name','default','address')} for record in second['telemetry']['requests']]
  pair['coverage_identical']=first['coverage']==second['coverage']
  save();assert pair['artifacts_identical'] and pair['lookup_results_identical'] and pair['coverage_identical'],pair
 result['after']=state()
 result['observed_table_stable']=result['before']['table_sha256']==result['after']['table_sha256']
 assert result['observed_table_stable']
 assert result['after']['registry']==[]
 assert result['after']['source']['frames']==result['after']['source']['writers']==0
 result['compiler_pairs_passed']=True;save()
finally:
 save()
# Retirement/unload is deliberately after all child exits and artifact checks.
fd=os.open('/dev/kd_dev',os.O_RDONLY|os.O_CLOEXEC)
try:
 device_session.fcntl.ioctl(fd,device_session.RETIRE)
 result['retirement']=device_session.info(fd)
finally:
 os.close(fd)
assert result['retirement']==dict(state=2,modules=0,frames=0,writers=0)
subprocess.run(['rmmod','kdlock_km'],check=True,timeout=20)
result['module_loaded']=False;idle(root,rt.idle)
for source in (root,baseline):
 for name,wanted in json.loads((source/'source-sha256.json').read_text()).items():assert rt.digest(source/name)==wanted
result.update(passed=True,final_idle=True,frozen_inputs_unchanged=True);save()
print(json.dumps(result))
