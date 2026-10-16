#!/usr/bin/env python3
"""Alternate frozen pre-change KD and adaptive KD using maintained acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path('/root/host_fs/kdlock')
p=argparse.ArgumentParser(add_help=False)
p.add_argument('--family',choices=('synthetic','api'),required=True)
p.add_argument('--baseline-root',type=Path,required=True)
p.add_argument('--baseline-manifest',type=Path,required=True)
a,remaining=p.parse_known_args()
base=a.baseline_root.resolve()
manifest=json.loads(a.baseline_manifest.read_text())
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def check_source():
 for path,wanted in manifest.items():
  assert digest(base/path)==wanted, path
check_source()
provider=base/'bench/spin_cacheline/.build/provider/kernel_module/kdlock_km.ko'
daemon=base/'daemon/daemon'
binary_hashes={str(f):digest(f) for f in (provider,daemon)}
old_run=base.parent
old_workload=(old_run/'pilot-v2-mutex-c01/variants/kdlock/mutex_cacheline.ko' if a.family=='synthetic' else old_run/'pilot-v2-api-pipebytes-query-n16/build/kdlock-pipebytes/real_api.ko')
binary_hashes[str(old_workload)]=digest(old_workload)
sys.path.insert(0,str(ROOT/('bench/tclock_compare' if a.family=='synthetic' else 'bench/real_api')))
import run as runner
original_plan=runner.make_plan

def plan(args):
 result=[]
 for spec in original_plan(args):
  if spec['arm']!='kdlock':
   result.append(dict(spec,comparison_arm=spec['arm']))
   continue
  variants=['before','adaptive']
  if spec['repeat']%2: variants.reverse()
  for arm in variants:
   row=dict(spec,name=spec['name']+'-'+arm,comparison_arm=arm)
   if arm=='before':
    row.pop('owned_mutex_adaptive')
    row['owned_mutex_object_bytes']=32
    row['owned_mutex_numa']=False
    if 'owned_queue_policy' in row: row['owned_queue_policy']='finite_fifo'
    if 'owned_acquire_policy' in row: row['owned_acquire_policy']='linux_local_first'
    row['baseline_manifest']=str(a.baseline_manifest)
    row['baseline_binary_sha256']=binary_hashes
   result.append(row)
 return result
runner.make_plan=plan

def check_binaries():
 assert {str(f):digest(f) for f in (provider,daemon,old_workload)}==binary_hashes

if a.family=='synthetic':
 class ComparisonSession(runner.BackendSession):
  def __init__(self,*args,**kwargs):
   super().__init__(*args,**kwargs)
   check_binaries()
   if self.record['comparison_arm']=='before':
    self.workload_module=old_workload
    self.translation_source=base
    self.daemon_binary=daemon
    self.save()
  def run(self,args,log,**kwargs):
   if self.record['comparison_arm']=='before' and args[:2]==['insmod',runner.PROVIDER]:
    args=['insmod',provider,*args[2:]]
   return super().run(args,log,**kwargs)
 runner.BackendSession=ComparisonSession
else:
 original_params=runner.owned_mutex_parameters
 def params(spec):
  result=original_params(spec)
  if spec['comparison_arm']=='before': result.pop('owned_mutex_adaptive')
  return result
 runner.owned_mutex_parameters=params
 class ComparisonSession(runner.SyscallSession):
  def __init__(self,*args,**kwargs):
   super().__init__(*args,**kwargs)
   check_binaries()
   if self.record['comparison_arm']=='before': self.workload_module=old_workload
  def run(self,args,log,**kwargs):
   if self.record['comparison_arm']=='before' and args[:2]==['insmod',self.out/'build/kdlock_km.ko']:
    args=['insmod',provider,*args[2:]]
   return super().run(args,log,**kwargs)
  def start_daemon(self):
   if self.record['comparison_arm']!='before': return super().start_daemon()
   workspace=self.path/'workspace'
   (workspace/'daemon').mkdir(parents=True)
   for directory in ('disassem','include'):
    (workspace/directory).symlink_to(base/directory,target_is_directory=True)
   self.daemon_log=(self.path/'daemon.log').open('w')
   env=dict(os.environ,KD_JIT_BODY_WITNESS='1')
   env.pop('KD_DEVICE_FD',None)
   self.daemon=subprocess.Popen([daemon,'--quiet','--metrics','--mode','per-tgid'],
     cwd=workspace/'daemon',env=env,stdout=self.daemon_log,stderr=subprocess.STDOUT,start_new_session=True)
   self.record['daemon_pid']=self.daemon.pid
   self.save()
 runner.SyscallSession=ComparisonSession
sys.argv=[sys.argv[0],*remaining]
try:
 result=runner.main('mutex') if a.family=='synthetic' else runner.main()
finally:
 check_source();check_binaries()
raise SystemExit(result)
