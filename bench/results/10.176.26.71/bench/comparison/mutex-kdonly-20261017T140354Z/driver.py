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

THREADS=[*range(1,9),*range(12,61,4)];GROUPS=('c01-post64','api-pipebytes-query-n16')
lookup={}
for version in ('baseline','compat'):
 for group in GROUPS:
  for s in load(OUT/version/group/'plan.json'):lookup[(group,s['threads'],s['repeat'],version,s['arm'])]=s
order=[]
for group in GROUPS:
 for i,n in enumerate(THREADS):
  for rep in range(3):
   pair=[('baseline','kdlock'),('compat','kdlock')]
   if (i+rep)%2:pair.reverse()
   if rep==0:arms=pair+[('compat','native'),('compat','tclock')]
   elif rep==1:arms=[('compat','tclock'),('compat','native')]+pair
   else:arms=[('compat','native')]+pair+[('compat','tclock')]
   order += [(group,n,rep,v,a) for v,a in arms]
pilot=[60,1,2,4,7,8,16]
order.sort(key=lambda k: (0, pilot.index(k[1]), GROUPS.index(k[0]), k[2]) if k[1] in pilot else (1, GROUPS.index(k[0]), k[1], k[2]))
save(OUT/'control/execution-order.json',order)
state=dict(state='RUNNING',started_utc=utc(),planned=len(order),completed=0,sessions=[]);save(OUT/'status.json',state)
for index,key in enumerate(order):
 group,n,rep,version,arm=key;folder=OUT/version/group;spec=dict(lookup[key],sequence=index)
 if (OUT/'STOP').exists():state.update(state='STOPPED',boundary='drained');save(OUT/'status.json',state);raise SystemExit(2)
 verify_inputs();syn.idle();assert not Path('/sys/module/real_api').exists()
 state.update(current=dict(workload=group,threads=n,repeat=rep,version=version,arm=arm));save(OUT/'status.json',state)
 print(f'[{index+1}/{len(order)}] {group} t{n} r{rep} {version}/{arm}',flush=True)
 if group.startswith('c01'):
  syn_session.PROVIDER=bench_session.PROVIDER=folder/'binaries/kdlock_km.ko'
  syn_session.HERE=bench_session.HERE=folder/'binaries'
  syn_session.TC_MUTEX_MODULE=folder/'binaries/tclock_mutex_backend_km.ko'
  syn_session.GUARD_MODULE=folder/'binaries/tc_allocator_guard.ko'
  session=FrozenSynthetic(folder,spec,workload_module=folder/'variants'/arm/'mutex_cacheline.ko')
 else:session=FrozenAPI(folder,spec)
 try:
  if group.startswith('c01'):syn.execute_session(session,keep_going_no_jit=True)
  else:session.execute()
 except BaseException as error:
  state.update(state='FAILED',error=repr(error),failed_at=utc());save(OUT/'status.json',state)
  raise
 r=session.record;assert r['drained'] and r['execution_status'] in ('OK','NO_JIT')
 m=r['measurement'];whole=m['completed']*1e3/m['wall_ns'];peak=m['peak']['throughput_ops_s']/1e6
 print(f'  whole={whole:.6f} peak={peak:.6f} Mops/s jit={r["jit_bodies"]} drained={r["drained"]}',flush=True)
 state['sessions'].append(dict(sequence=index,workload=group,threads=n,repeat=rep,version=version,arm=arm,name=r['name'],status=r['execution_status'],drained=r['drained'],whole_mops=whole,peak_mops=peak))
 state['completed']=index+1;save(OUT/'status.json',state)
for group in GROUPS:
 for v in ('baseline','compat'):
  f=OUT/v/group
  if group.startswith('c01'):syn.report(f)
  else:save(f/'records.json',[load(f/s['name']/'session.json') for s in load(f/'plan.json')])
verify_inputs();syn.idle();assert not Path('/sys/module/real_api').exists()
state.update(state='COMPLETE',finished_utc=utc());save(OUT/'status.json',state)
print('All 504 fresh sessions finished and drained.',flush=True)
