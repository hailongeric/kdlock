import argparse,fcntl,json,os,pathlib,platform,signal,subprocess,sys,time
R=pathlib.Path('/mnt/kdlock-builds2/main-spin-local-4669a085-20261117')
variant='main-queue-rwcheck'
# Set before freezing the runner: (parameter, ordered values).
POLICY_CASES = []
SOURCE_IDENTITY = json.loads((R/'main-queue-identity.json').read_text())
assert len(SOURCE_IDENTITY['commit']) == 40
BOOT_ID = pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
os.sched_setaffinity(0,{38,39})
B=R/'main-queue-repo'; E=R/'evidence-main-queue-rwcheck'; E.mkdir(exist_ok=False)
sys.path.insert(0,str(B/'bench'))
import run_nano as n
assert platform.release()=='7.0.0-38-kdlocalspin5'
assert pathlib.Path('/sys/class/block/vda/serial').read_text().strip()=='kd16-root'
assert pathlib.Path('/sys/class/block/vdb/serial').read_text().strip()=='kd16-builds-current'
initial_taint=int(pathlib.Path('/proc/sys/kernel/tainted').read_text())
assert initial_taint in (0,4096), initial_taint
assert {l.split()[0] for l in pathlib.Path('/proc/modules').read_text().splitlines()} <= {'nls_iso8859_1'}
assert not any(m in pathlib.Path('/proc/modules').read_text() for m in ('kd_bench','tclock_','kd_nano'))
assert pathlib.Path('/sys/kernel/debug/tracing/current_tracer').read_text().strip()=='nop'
os.environ['PYTHONPATH']=str(R/'python')
PARAM=pathlib.Path('/sys/module/kernel/parameters')
mods=[('spin','tclock_backend_km'),('mutex','tclock_mutex_backend_km'),('rwlock','tclock_rwlock_backend_km'),('rwsem','tclock_rwsem_backend_km')]
loaded=[];fd=None;daemon=None;dlog=None
log=open(E/'points.jsonl','x',buffering=1)
params={k:(PARAM/k).read_text().strip() for k in ('kd_adapt','kd_deleg_enter','kd_deleg_exit')}
for key in ('kd_batch','kd_numa','kd_numa_after','kd_spin_phase_wait','kd_spin_queue_phase'):
 params[key]=(PARAM/key).read_text().strip()
for key,values in POLICY_CASES:
 assert key.startswith('kd_') and '/' not in key and values
 params[key]=(PARAM/key).read_text().strip()
assert params['kd_spin_phase_wait']=='0', 'queue experiment requires polling off'
REQUIRED_COUNTS=('offered','delegated','handback','sessions','stop_plain','numa_deferred')
assert set(REQUIRED_COUNTS) <= set(n.kd_stats()), 'required counters unavailable'
def cmd(name,argv):
 p=subprocess.run(argv,capture_output=True,text=True,timeout=45)
 (E/name).write_text(p.stdout+p.stderr)
 if p.returncode:raise RuntimeError((argv,p.returncode))
 return p.stdout

def tc_idle():
 for _,m in mods:
  if m in loaded:
   assert (pathlib.Path('/sys/module')/m/'parameters/quiescent').read_text().strip()=='1',m


def checked_run(fd,args,workers,ms):
 import struct
 req=struct.pack(n.IN_FMT,n.FAMILY[args.family],n.BACKEND[args.backend],args.lines,args.write_pct,args.post,workers,args.first_cpu,ms,0,0)
 buf=bytearray(req+bytes(struct.calcsize(n.RUN_FMT)-len(req)))
 fcntl.ioctl(fd,n.IOC,buf,True)
 f=struct.unpack(n.RUN_FMT,buf)
 elapsed,ops,writes,bad,delta=f[10:15]
 wops=list(f[15:15+workers]);wwr=list(f[15+n.MAXW:15+n.MAXW+workers])
 return dict(ok=elapsed>0 and all(wops) and sum(wops)==ops and sum(wwr)==writes and bad==0 and delta==writes*args.lines,
             mops=ops/elapsed*1e3 if elapsed else 0,elapsed_ns=elapsed,ops=ops,writes=writes,torn_reads=bad,sum_delta=delta,
             worker_ops=wops,worker_writes=wwr,min_worker_ops=min(wops),max_worker_ops=max(wops))

def point(phase,backend,w,lines=1,post=64,first=None,ms=300,rnd=0,family='spin',policy='default',write_pct=100):
 if first is None: first=4 if w==32 else 0
 a=argparse.Namespace(family=family,backend=backend,lines=lines,write_pct=write_pct,post=post,first_cpu=first,per_worker=True)
 effective={key:(PARAM/key).read_text().strip() for key in ('kd_spin_phase_wait','kd_spin_queue_phase','kd_numa')}
 assert effective['kd_spin_phase_wait']=='0'
 before=n.kd_stats(); t=time.time(); r=checked_run(fd,a,w,ms);after=n.kd_stats()
 r.update(phase=phase,backend=backend,workers=w,lines=lines,write_pct=write_pct,parameters=effective,post=post,first_cpu=first,ms=ms,round=rnd,family=family,policy=policy,time=t,variant=variant,kernel=platform.release(),kd_delta={k:after[k]-before.get(k,0) for k in after if k!='delegation'},delegation=after.get('delegation'))
 r['execution_counts']={key:r['kd_delta'][key] for key in REQUIRED_COUNTS}
 r['reads']=r['ops']-r['writes']
 r['worker_reads']=[ops-writes for ops,writes in zip(r['worker_ops'],r['worker_writes'])]
 if family=='rwlock' and write_pct==20:
  r['ok']=r['ok'] and all(x>0 for x in r['worker_reads']) and all(x>0 for x in r['worker_writes']) and sum(r['worker_reads'])==r['reads']
 log.write(json.dumps(r)+'\n');print(phase,policy,backend,w,lines,post,first,r['ok'],round(r['mops'],3),json.dumps(r['execution_counts'],sort_keys=True),flush=True)
 assert r['ok'],r
 current_log=subprocess.check_output(['dmesg'],text=True)
 assert not any(x in current_log for x in ('BUG:','soft lockup','hard LOCKUP','WARNING:','Oops:')), 'kernel warning; campaign stopped'
 if backend=='tclock':tc_idle()
 if backend=='kd' and w==1 and family=='spin':assert r['kd_delta'].get('offered',0)==0
 return r

# This is a separate, drained supplement to the frozen throughput campaign.
# Multiple counters are required for the reader consistency comparison loop.
parent=R/'evidence-main-queue'
parent_identity=json.loads((parent/'identity.json').read_text())
parent_cleanup=json.loads((parent/'cleanup.json').read_text())
assert (parent/'measurements-complete.json').exists()
assert parent_identity['source']==SOURCE_IDENTITY['commit']
assert parent_identity['boot_id']==parent_cleanup['boot_id']==BOOT_ID
assert parent_cleanup['daemon_rc']==0
for path in pathlib.Path('/proc').iterdir():
 if not path.name.isdigit():continue
 try:args=(path/'cmdline').read_bytes().split(b'\0')
 except (FileNotFoundError,PermissionError):continue
 assert not any(arg.endswith(b'/kd_daemon.py') for arg in args),'translator already active'

try:
 (PARAM/'kd_spin_phase_wait').write_text('0')
 (PARAM/'kd_spin_queue_phase').write_text('1')
 for name,argv in [('uname.txt',['uname','-a']),('dmesg-before.txt',['dmesg']),('topology.txt',['lscpu','-e']),('modules-before.txt',['cat','/proc/modules']),('preempt.txt',['cat','/sys/kernel/debug/sched/preempt'])]:cmd(name,argv)
 (E/'identity.json').write_text(json.dumps(dict(variant=variant,source=SOURCE_IDENTITY['commit'],source_identity=SOURCE_IDENTITY,boot_id=BOOT_ID,kernel=platform.release(),build=platform.version(),params=params,parent_evidence=str(parent),start=time.time(),purpose='Mixed rwlock reader consistency with sixteen counters; no throughput comparison claim.')))
 for family,m in mods:
  cmd('insmod-'+family+'.txt',['insmod',str(B/'local-tclock'/family/(m+'.ko'))]);loaded.append(m)
 cmd('insmod-bench.txt',['insmod',str(B/'bench/kd_bench.ko')]);loaded.append('kd_bench')
 tc_idle();fd=os.open('/dev/kdbench',os.O_RDWR)
 cmd('dryrun.txt',[sys.executable,str(B/'jit/kd_dryrun.py'),'krwl_w','--disasm'])
 dlog=open(E/'daemon.log','x')
 daemon=subprocess.Popen([sys.executable,'-u',str(B/'jit/kd_daemon.py'),'--state',str(E/'learned.json'),'-v'],stdout=dlog,stderr=subprocess.STDOUT)
 (E/'daemon.pid').write_text(str(daemon.pid));time.sleep(1);assert daemon.poll() is None
 for w in (8,32):point('learning','kd',w,lines=16,family='rwlock',ms=500,write_pct=100)
 for setting in (0,1):
  (PARAM/'kd_spin_queue_phase').write_text(str(setting))
  failures=fcntl.ioctl(fd,n.IOC_APITEST)
  (E/('api-policy-'+str(setting)+'.json')).write_text(json.dumps({'failed_checks':failures,'kd_spin_queue_phase':setting,'kd_spin_phase_wait':0}));assert failures==0
  for w in (8,32):
   for be in ('native','kd'):
    point('rwlock-mixed-sixteen-check',be,w,lines=16,family='rwlock',write_pct=20,ms=500,policy='kd_spin_queue_phase='+str(setting))
 assert daemon.poll() is None
 assert pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT_ID
 (E/'measurements-complete.json').write_text(json.dumps({'complete':True,'mixed_points':8,'learning_points':2,'finish':time.time()}))
finally:
 for k,v in params.items():(PARAM/k).write_text(v)
 if daemon is not None:
  daemon.send_signal(signal.SIGINT);daemon.wait(timeout=30)
  dlog.close()
 if fd is not None:os.close(fd)
 tc_idle()
 for m in reversed(loaded):cmd('rmmod-'+m+'.txt',['rmmod',m])
 cmd('dmesg-after.txt',['dmesg']);cmd('modules-after.txt',['cat','/proc/modules']);cmd('stats-after.txt',['cat',n.STATS])
 (E/'cleanup.json').write_text(json.dumps({'daemon_rc':daemon.returncode if daemon else None,'unloaded':loaded,'restored_params':params,'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()}))
log.close()
