RUN='mutex-kdonly-20261017T140354Z'
from pathlib import Path
from datetime import datetime, timezone
import os,sys,json,time,hashlib,importlib.util,subprocess,fcntl,struct
ROOT=Path('/root/host_fs/kdlock');OUT=Path('/root/kdlock-evidence/10.176.26.71/bench')/RUN/'matrix7'
PY='/root/kdlock-evidence/clobber-20260918/venv/bin/python3'
os.environ.update(PATH=str(Path(PY).parent)+':'+os.environ['PATH'],PYTHONDONTWRITEBYTECODE='1',LC_ALL='C',KDLOCK_RECOVERY_CONFIRMED='1',KDLOCK_SNAPSHOT_TAG='before-'+RUN)
sys.path.insert(0,str(ROOT/'bench/tclock_compare'));import run as syn
import session as syn_session
import bench_session
sp=importlib.util.spec_from_file_location('real_api',ROOT/'bench/real_api/run.py');api=importlib.util.module_from_spec(sp);sp.loader.exec_module(api)
def load(p):return json.loads(p.read_text())
def save(p,v):p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def utc():return datetime.now(timezone.utc).isoformat()
assert load(OUT/'control/prepared.json')['passed']

FROZEN=load(OUT/'control/prepared-inputs-sha256.json')
SOURCE=load(OUT/'control/source-sha256.json')
def verify_inputs():
 for n,h in FROZEN.items():assert sha(OUT/n)==h,n
 for n,h in SOURCE.items():assert sha(ROOT/n)==h,n

def image_state():
 fd=os.open('/dev/kd_dev',os.O_RDONLY|os.O_CLOEXEC)
 try:
  packet=bytearray(16);fcntl.ioctl(fd,0x80104b73,packet,True)
  caps=struct.unpack('<IIII',packet);assert caps==(5,27,256,8192),caps
  data=os.read(fd,64*511);assert len(data)==64,len(data)
  row=struct.unpack('<iiiiQQQQIIQ',data)
  assert row[0]==0 and row[1]==0 and row[3]==2 and row[5] and row[8:]==(2,0,1),row
  return dict(capabilities=list(caps),entry=row[4],code=row[5],abi=row[8],requirements=row[9],generation=row[10])
 finally:os.close(fd)

class FrozenSynthetic(syn.BackendSession):
 def start_daemon(self):
  workspace=self.path/'workspace';(workspace/'daemon').mkdir(parents=True)
  for directory in ('disassem','include'):(workspace/directory).symlink_to(self.path.parent/'source'/directory,target_is_directory=True)
  self.daemon_log=(self.path/'daemon.log').open('w')
  env=dict(os.environ,KD_JIT_BODY_WITNESS='1');env.pop('KD_DEVICE_FD',None)
  self.daemon=subprocess.Popen([self.path.parent/'binaries/daemon','--quiet','--metrics','--mode','per-tgid'],cwd=workspace/'daemon',env=env,stdout=self.daemon_log,stderr=subprocess.STDOUT,start_new_session=True)
  self.record['daemon_pid']=self.daemon.pid;self.save()
 def measure(self):
  check=self.loaded_kd and self.record['mutex_version']=='compat'
  if check:
   address=self.record['layout']['lock_addr']
   address=int(address,0) if isinstance(address,str) else address
   assert address%128==0,hex(address)
   self.record['image_generation_before']=image_state()
  super().measure()
  if check:
   self.record['image_generation_after']=image_state()
   assert self.record['image_generation_before']==self.record['image_generation_after']
   self.save()
class FrozenAPI(api.SyscallSession):
 def measure(self):
  check=self.loaded_kd and self.record['mutex_version']=='compat'
  if check:self.record['image_generation_before']=image_state()
  super().measure()
  if check:
   self.record['image_generation_after']=image_state()
   assert self.record['image_generation_before']==self.record['image_generation_after']
   self.save()


import shutil,re,statistics
CHECK=OUT.parent/'recheck-matrix7'
assert load(OUT/'status.json')['state']=='COMPLETE'
assert not CHECK.exists()
CHECK.mkdir()
# Prespecified trigger: every main-grid median loss worse than 5%, nine new pairs.
# Keep the original grid intact and report this repeat separately.
select=[]
state=load(OUT/'status.json'); buckets={}
for r in state['sessions']:
 if r['arm']=='kdlock':buckets.setdefault((r['workload'],r['threads'],r['version']),[]).append(r['whole_mops'])
for group,n in sorted({(g,n) for g,n,v in buckets}):
 a=statistics.median(buckets[group,n,'baseline']);b=statistics.median(buckets[group,n,'compat'])
 if b/a < .95:select.append(dict(workload=group,threads=n,initial_change_pct=100*(b/a-1)))
save(CHECK/'selection.json',dict(rule='all full-grid points with median KD-only loss greater than 5 percent',extra_pairs_per_point=9,points=select,initial_sessions_retained=True))
lookup={};folders={};order=[]
for group in sorted({r['workload'] for r in select}):
 for version in ('baseline','compat'):
  src=OUT/version/group;dst=CHECK/version/group;dst.mkdir(parents=True);folders[version,group]=dst
  directories=('source','binaries','variants','kernel-baseline','kernel-inputs') if group.startswith('c01') else ('source','build','kernel-inputs')
  for name in directories:
   if (src/name).exists():shutil.copytree(src/name,dst/name)
  for p in src.iterdir():
   if p.is_file() and p.name not in ('plan.json','records.json','records.csv','summary.json','summary.csv','README.md'):
    shutil.copy2(p,dst/p.name)
  if group.startswith('api'):
   binary=load(dst/'binaries.json')
   for name,row in binary.items():
    assert sha(dst/'build'/name)==row['sha256'];row['path']=str(dst/'build'/name)
   save(dst/'binaries.json',binary)
  plan=[]
  for point in select:
   if point['workload']!=group:continue
   n=point['threads'];template=next(r for r in load(src/'plan.json') if r['threads']==n and r['arm']=='kdlock')
   for rep in range(9):
    spec=dict(template,repeat=rep,name=re.sub(r'-r[0-9]+-',f'-r{rep:02d}-',template['name']))
    lookup[group,n,rep,version]=spec;plan.append(spec)
  save(dst/'plan.json',plan)
for point in select:
 group,n=point['workload'],point['threads']
 for rep in range(9):
  versions=['baseline','compat'] if rep%2==0 else ['compat','baseline']
  order.extend((group,n,rep,v) for v in versions)
save(CHECK/'execution-order.json',order)
status=dict(state='RUNNING',started_utc=utc(),planned=len(order),completed=0,sessions=[]);save(CHECK/'status.json',status)
for i,key in enumerate(order):
 group,n,rep,version=key;folder=folders[version,group];spec=dict(lookup[key],sequence=i)
 verify_inputs();syn.idle();assert not Path('/sys/module/real_api').exists()
 print(f'[{i+1}/{len(order)}] recheck {group} t{n} r{rep} {version}/kdlock',flush=True)
 if group.startswith('c01'):
  syn_session.PROVIDER=bench_session.PROVIDER=folder/'binaries/kdlock_km.ko'
  syn_session.HERE=bench_session.HERE=folder/'binaries'
  syn_session.TC_MUTEX_MODULE=folder/'binaries/tclock_mutex_backend_km.ko'
  syn_session.GUARD_MODULE=folder/'binaries/tc_allocator_guard.ko'
  session=FrozenSynthetic(folder,spec,workload_module=folder/'variants/kdlock/mutex_cacheline.ko')
 else:session=FrozenAPI(folder,spec)
 try:
  if group.startswith('c01'):syn.execute_session(session,keep_going_no_jit=True)
  else:session.execute()
 except BaseException as error:
  status.update(state='FAILED',error=repr(error),failed_at=utc());save(CHECK/'status.json',status);raise
 r=session.record;assert r['drained'] and r['execution_status'] in ('OK','NO_JIT')
 m=r['measurement'];whole=m['completed']*1e3/m['wall_ns'];peak=m['peak']['throughput_ops_s']/1e6
 print(f'  whole={whole:.6f} peak={peak:.6f} Mops/s jit={r["jit_bodies"]} drained={r["drained"]}',flush=True)
 status['sessions'].append(dict(sequence=i,workload=group,threads=n,repeat=rep,version=version,name=r['name'],status=r['execution_status'],drained=True,whole_mops=whole,peak_mops=peak));status['completed']=i+1;save(CHECK/'status.json',status)
for (v,g),f in folders.items():
 if g.startswith('c01'):syn.report(f)
 else:save(f/'records.json',[load(f/s['name']/'session.json') for s in load(f/'plan.json')])
verify_inputs();syn.idle();assert not Path('/sys/module/real_api').exists()
status.update(state='COMPLETE',finished_utc=utc());save(CHECK/'status.json',status)
print('Recheck complete:',len(order),'fresh drained sessions',flush=True)
