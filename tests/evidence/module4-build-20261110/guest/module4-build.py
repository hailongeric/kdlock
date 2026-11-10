#!/usr/bin/env python3
"""VM-only offline fixture build. Authoring this helper performs no build.

Requires actual completed kernel3 pins. Normal-kernel boot is permitted because
make explicitly targets the separate kernel3 output/release; nothing is loaded.
An observer timeout retains the child and its outputs, without a drain claim.
"""
from pathlib import Path
import argparse, ast, datetime, hashlib, json, math, os, subprocess, time

COMMIT='69ba6b030c1eb7e5f1c3f9461b70f5fef6791309'
RELEASE='7.0.0-38-kdrebuild3'

def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as source:
  for block in iter(lambda:source.read(1024*1024),b''):h.update(block)
 return h.hexdigest()

def retained_json(path, expected):
 if path.is_symlink() or digest(path)!=expected:raise ValueError('external input pin differs: '+str(path))
 return json.loads(path.read_text())

def within(path, parent):return path==parent or parent in path.parents

def free_bytes(path):
 value=os.statvfs(path)
 return value.f_bavail*value.f_frsize

def main():
 p=argparse.ArgumentParser()
 for name in ('input','manifest','state','build-inputs','kernel-source','kernel-build','kernel-pins','output','receipts'):
  p.add_argument('--'+name,type=Path,required=True)
 for name in ('manifest-sha256','state-sha256','build-inputs-sha256','kernel-pins-sha256','expected-boot'):
  p.add_argument('--'+name,required=True)
 p.add_argument('--jobs',type=int,required=True)
 p.add_argument('--seconds',type=float,required=True)
 p.add_argument('--space-floor',type=int,required=True)
 a=p.parse_args()
 if os.geteuid()!=0 or os.uname().machine!='x86_64' or os.uname().release not in ('7.0.0-38-kdlock1',RELEASE):raise ValueError('designated VM normal/kernel3 context required')
 if Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=a.expected_boot:raise ValueError('actual boot differs')
 if a.jobs<=0 or a.seconds<=0 or not math.isfinite(a.seconds) or a.space_floor<0:raise ValueError('explicit finite command limits required')
 overrides=sorted(name for name in os.environ if name in {'KCFLAGS','KAFLAGS','KCPPFLAGS','CC','LD'} or name.startswith(('CFLAGS','AFLAGS')))
 if overrides:raise ValueError('unreviewed compiler/assembler/linker environment overrides: '+','.join(overrides))
 if any(line.startswith('kd_runtime_fixture ') for line in Path('/proc/modules').read_text().splitlines()) or any(Path('/dev').glob('kd_runtime_fixture*')):raise ValueError('fixture remains active')
 idle=subprocess.run(['ps','-eo','pid,comm,args'],capture_output=True,text=True,check=True,timeout=5).stdout
 for line in idle.splitlines()[1:]:
  fields=line.split(None,2)
  if len(fields)==3 and (fields[1] in ('make','gcc','gcc-15','cc1','as','ld','objtool') or 'unittest discover' in fields[2] or 'tests/kernel/run_runtime_fixture.py' in fields[2]):raise ValueError('build/test/source activity is not idle: '+line)
 for name in ('input','kernel_source','kernel_build'):
  original=getattr(a,name)
  if original.is_symlink():raise ValueError('direct source/output paths required')
  setattr(a,name,original.resolve(strict=True))
 a.output=a.output.resolve();a.receipts=a.receipts.resolve()
 protected=(a.input,a.kernel_source,a.kernel_build)
 for path in (a.output,a.receipts):
  if path.exists() or any(within(path,other) or within(other,path) for other in protected):raise ValueError('fresh separate module output/receipts required')
 if within(a.output,a.receipts) or within(a.receipts,a.output):raise ValueError('separate output/receipt leaves required')
 manifest=retained_json(a.manifest,a.manifest_sha256)
 state=retained_json(a.state,a.state_sha256)
 inputs=retained_json(a.build_inputs,a.build_inputs_sha256)
 pins=retained_json(a.kernel_pins,a.kernel_pins_sha256)
 if state['commit']!=COMMIT or inputs['source_git_head']!=COMMIT or len(inputs['files'])!=66:raise ValueError('source/kernel input identity differs')
 required={'vmlinux','.config','System.map','Module.symvers','include/config/kernel.release','include/generated/utsrelease.h'}
 if set(pins)!=required:raise ValueError('exact six actual kernel3 output pins required')
 def verify_source():
  actual={}
  for path in a.input.rglob('*'):
   if path.is_symlink():raise ValueError('immutable input contains symlink')
   if path.is_file():actual[path.relative_to(a.input).as_posix()]={'bytes':path.stat().st_size,'sha256':digest(path)}
  if actual!=manifest:raise ValueError('complete immutable source contents differ')
  for name,sha in inputs['files'].items():
   if digest(a.kernel_source/'kernel/kdlock'/name)!=sha:raise ValueError('actual kernel package differs: '+name)
  return len(actual)
 def verify_kernel():
  actual={name:digest(a.kernel_build/name) for name in required}
  if actual!=pins:raise ValueError('actual kernel output pins differ')
  if (a.kernel_build/'include/config/kernel.release').read_text().strip()!=RELEASE or RELEASE not in (a.kernel_build/'include/generated/utsrelease.h').read_text():raise ValueError('output is not kernel3')
  if '__tracepoint_kdlock_observe_tp' not in (a.kernel_build/'Module.symvers').read_text():raise ValueError('actual tracepoint export absent')
  return actual
 before=verify_source();verify_kernel()
 if free_bytes(a.output.parent)<a.space_floor:raise ValueError('module output free-space floor unavailable')
 a.receipts.mkdir(parents=True);a.output.mkdir(parents=True)
 record={'scope':'VM-only AST and external fixture build; no project import, tests, module load or source execution.','source_commit':COMMIT,'kernelrelease':RELEASE,'start_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'boot_id':a.expected_boot,'running_release':os.uname().release,'taint_before':Path('/proc/sys/kernel/tainted').read_text().strip(),'verified_source_before':before,'kernel_pins':pins,'idle_before':idle,'observer_seconds':a.seconds,'space_floor':a.space_floor,'compiler_environment_overrides':overrides}
 command=['make','-C',str(a.kernel_source),'O='+str(a.kernel_build),'M='+str(a.input/'tests/kernel/payload'),'MO='+str(a.output),'KERNELRELEASE='+RELEASE,'-j'+str(a.jobs),'V=1','modules']
 record['argv']=list(command)
 (a.receipts/'command.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
 try:
  ast.parse((a.input/'tests/kernel/run_runtime_fixture.py').read_text(),filename='tests/kernel/run_runtime_fixture.py')
  record['runner_ast']='PASS'
  start=time.monotonic()
  with (a.receipts/'build.log').open('x') as log:
   child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env={**os.environ,'LC_ALL':'C','LANG':'C','PYTHONDONTWRITEBYTECODE':'1'})
   record['pid']=child.pid
   (a.receipts/'command.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
   while child.poll() is None and time.monotonic()-start<a.seconds:
    if free_bytes(a.output)<a.space_floor:
     record['space_floor_crossed']=True
     break
    time.sleep(0.5)
   code=child.poll()
  record.update(returncode=code,elapsed_seconds=time.monotonic()-start,status='RETURNED' if code is not None else 'RUNNING_AFTER_OBSERVER_BOUND')
  if code is not None:
   record['verified_source_after']=verify_source();record['kernel_pins_after']=verify_kernel()
   if code==0:
    module=a.output/'kd_runtime_fixture.ko'
    record['module']={'path':str(module),'bytes':module.stat().st_size,'sha256':digest(module)}
    for label,args in [('modinfo',['modinfo',str(module)]),('symbols',['nm','-S','--defined-only',str(module)])]:
     result=subprocess.run(args,capture_output=True,text=True,check=True,timeout=15)
     (a.receipts/(label+'.txt')).write_text(result.stdout+result.stderr)
    if RELEASE not in (a.receipts/'modinfo.txt').read_text():raise ValueError('module vermagic differs from explicit kernel3 release')
  record['log_sha256_at_observer_end']=digest(a.receipts/'build.log')
  record['taint_after']=Path('/proc/sys/kernel/tainted').read_text().strip()
  record['end_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
  (a.receipts/'result.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
  print(json.dumps(record,indent=2,sort_keys=True))
  return code if code is not None else 124
 except BaseException as error:
  record['status']='FAILED_OR_INCOMPLETE';record['error']=repr(error)
  (a.receipts/'result.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
  raise

if __name__=='__main__':raise SystemExit(main())
