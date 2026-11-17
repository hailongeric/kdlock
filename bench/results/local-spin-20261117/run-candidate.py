import argparse,fcntl,json,os,pathlib,platform,signal,subprocess,sys,time
R=pathlib.Path('/mnt/kdlock-builds2/main-spin-local-4669a085-20261117')
variant='local-candidate'
os.sched_setaffinity(0,{38,39})
B=R/'candidate-repo'; E=R/'evidence-candidate'; E.mkdir(exist_ok=False)
sys.path.insert(0,str(B/'bench'))
import run_nano as n
assert platform.release()=='7.0.0-38-kdlocalspin2'
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
if (PARAM/'kd_spin_min_batch').exists():params['kd_spin_min_batch']=(PARAM/'kd_spin_min_batch').read_text().strip()
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

def point(phase,backend,w,lines=1,post=64,first=None,ms=300,rnd=0,family='spin',policy='default'):
 if first is None: first=4 if w==32 else 0
 a=argparse.Namespace(family=family,backend=backend,lines=lines,write_pct=100,post=post,first_cpu=first,per_worker=True)
 before=n.kd_stats(); t=time.time(); r=checked_run(fd,a,w,ms);after=n.kd_stats()
 r.update(phase=phase,backend=backend,workers=w,lines=lines,post=post,first_cpu=first,ms=ms,round=rnd,family=family,policy=policy,time=t,variant=variant,kernel=platform.release(),kd_delta={k:after[k]-before.get(k,0) for k in after if k!='delegation'},delegation=after.get('delegation'))
 log.write(json.dumps(r)+'\n');print(phase,policy,backend,w,lines,post,first,r['ok'],round(r['mops'],3),flush=True)
 assert r['ok'],r
 current_log=subprocess.check_output(['dmesg'],text=True)
 assert not any(x in current_log for x in ('BUG:','soft lockup','hard LOCKUP','WARNING:','Oops:')), 'kernel warning; campaign stopped'
 if backend=='tclock':tc_idle()
 if backend=='kd' and w==1 and family=='spin':assert r['kd_delta'].get('offered',0)==0
 return r

def timed(phase,backends,workers,lines_set=(1,16),post=64,first=None,rounds=3,policy='default'):
 for rnd in range(rounds):
  for lines in lines_set:
   for w in workers:
    k=(rnd+w)%len(backends)
    for be in backends[k:]+backends[:k]:
     point(phase+'-warmup',be,w,lines,post,first,ms=250,rnd=rnd,policy=policy)
     point(phase,be,w,lines,post,first,ms=1000,rnd=rnd,policy=policy)

try:
 for name,argv in [('uname.txt',['uname','-a']),('dmesg-before.txt',['dmesg']),('topology.txt',['lscpu','-e']),('modules-before.txt',['cat','/proc/modules']),('preempt.txt',['cat','/sys/kernel/debug/sched/preempt'])]:cmd(name,argv)
 (E/'identity.json').write_text(json.dumps(dict(variant=variant,source='200c4effb5dce0c0baa7283cb061da1ea8defc50',kernel_core='200c4effb5dce0c0baa7283cb061da1ea8defc50',boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),kernel=platform.release(),build=platform.version(),params=params,start=time.time())))
 for family,m in mods:
  cmd('insmod-'+family+'.txt',['insmod',str(B/'local-tclock'/family/(m+'.ko'))]);loaded.append(m)
 cmd('insmod-bench.txt',['insmod',str(B/'bench/kd_bench.ko')]);loaded.append('kd_bench')
 entries=[l.split()[0] for l in pathlib.Path('/proc/kallsyms').read_text().splitlines() if l.split()[2:] == ['t_spin','[kd_bench]']]
 assert len(entries)==1
 (pathlib.Path('/sys/module/tclock_backend_km/parameters/target_lock')).write_text('0x'+entries[0])
 tc_idle();fd=os.open('/dev/kdbench',os.O_RDWR)
 failures=fcntl.ioctl(fd,n.IOC_APITEST);(E/'api.json').write_text(json.dumps({'failed_checks':failures}));assert failures==0
 for be in ('native','kd','tclock'):
  for w in (1,2,5,8,32):point('local-check',be,w)
 for fam in ('nest_spin','spin_raw','spin_hb'):
  for be in ('native','kd'):
   for w in (2,8):point('local-check',be,w,family=fam)
 timed('daemon-off',('native','kd'),(5,8,32),lines_set=(1,))
 cmd('dryrun.txt',[sys.executable,str(B/'jit/kd_dryrun.py'),'kspin_w','knest_spin_outer','kspin_hb_w','--disasm'])
 dlog=open(E/'daemon.log','x')
 daemon=subprocess.Popen([sys.executable,'-u',str(B/'jit/kd_daemon.py'),'--state',str(E/'learned.json'),'-v'],stdout=dlog,stderr=subprocess.STDOUT)
 (E/'daemon.pid').write_text(str(daemon.pid));time.sleep(1);assert daemon.poll() is None
 for w in (8,32):point('learning','kd',w,ms=1000)
 for w in (1,2,3,8,32,3,2,1):point('phase-change','kd',w,ms=500)
 for fam in ('nest_spin','spin_raw','spin_hb'):
  for w in (2,8):point('delegation-check','kd',w,family=fam)
 timed('three-way',('native','kd','tclock'),(1,2,3,5,8,16,32))
 timed('outside-work',('native','kd','tclock'),(1,5,8,32),post=0,rounds=2)
 # Thirty-two workers already use balanced CPUs 4..35 in every grid.
 timed('numa-packed',('native','kd','tclock'),(32,),first=0,rounds=3)
 if 'kd_spin_min_batch' in params:
  for rnd in range(3):
   for minimum in ((0,2) if rnd%2==0 else (2,0)):
    (PARAM/'kd_spin_min_batch').write_text(str(minimum))
    for lines in (1,16):
     for w in (5,8,32):
      point('policy-warmup','kd',w,lines,ms=250,rnd=rnd,policy=str(minimum))
      point('policy','kd',w,lines,ms=1000,rnd=rnd,policy=str(minimum))
  (PARAM/'kd_spin_min_batch').write_text(params['kd_spin_min_batch'])
 (PARAM/'kd_adapt').write_text('0')
 for w in (2,8):point('forced-check','kd',w)
 (PARAM/'kd_adapt').write_text(params['kd_adapt'])
 (E/'profiling-status.json').write_text(json.dumps({'status':'not_run','reason':'Timing and functional validation first; no profile is claimed.'}))
 assert daemon.poll() is None
 (E/'measurements-complete.json').write_text(json.dumps({'complete':True,'finish':time.time()}))
finally:
 for k,v in params.items():(PARAM/k).write_text(v)
 if daemon is not None:
  daemon.send_signal(signal.SIGINT);daemon.wait(timeout=30)
  dlog.close()
 if fd is not None:os.close(fd)
 tc_idle()
 if 'tclock_backend_km' in loaded:(pathlib.Path('/sys/module/tclock_backend_km/parameters/target_lock')).write_text('0')
 for m in reversed(loaded):cmd('rmmod-'+m+'.txt',['rmmod',m])
 cmd('dmesg-after.txt',['dmesg']);cmd('modules-after.txt',['cat','/proc/modules']);cmd('stats-after.txt',['cat',n.STATS])
 (E/'cleanup.json').write_text(json.dumps({'daemon_rc':daemon.returncode if daemon else None,'unloaded':loaded,'restored_params':params,'boot_id':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()}))
log.close()
