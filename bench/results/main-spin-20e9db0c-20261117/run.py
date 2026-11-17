import argparse,fcntl,json,os,pathlib,platform,signal,subprocess,sys,time
R=pathlib.Path('/mnt/kdlock-builds/main-spin-20e9db0c-20261117')
sys.path.insert(0,str(R/'repo/bench'))
import run_nano as n
E=R/'evidence'
E.mkdir(exist_ok=False)
log=open(E/'points.jsonl','x',buffering=1)
def save(name,argv):
 p=subprocess.run(argv,capture_output=True,text=True,timeout=30)
 (E/name).write_text(p.stdout+p.stderr)
 if p.returncode: raise RuntimeError((argv,p.returncode))
 return p.stdout
assert platform.release()=='7.0.0-38-kdmainspin1'
for name,argv in [('uname.txt',['uname','-a']),('dmesg-before.txt',['dmesg']),('topology.txt',['lscpu','-e']),('modules-before.txt',['cat','/proc/modules']),('cmdline.txt',['cat','/proc/cmdline']),('preempt.txt',['cat','/sys/kernel/debug/sched/preempt'])]: save(name,argv)
(E/'identity.json').write_text(json.dumps(dict(commit='20e9db0c',kernel=platform.release(),build=platform.version(),start=time.time(),worker_cpus='0..workers-1',post=64,rounds=3,ms=1000)))
save('insmod.txt',['insmod',str(R/'repo/bench/kd_bench.ko')])
fd=os.open('/dev/kdbench',os.O_RDWR)
failed=fcntl.ioctl(fd,n.IOC_APITEST)
(E/'api.json').write_text(json.dumps({'failed_checks':failed}))
assert failed==0

def point(phase,family,backend,workers,lines=1,ms=250,rnd=0):
 a=argparse.Namespace(family=family,backend=backend,lines=lines,write_pct=100,post=64,first_cpu=0,per_worker=True)
 before=n.kd_stats()
 r=n.run_once(fd,a,workers,ms)
 after=n.kd_stats()
 r.update(phase=phase,family=family,backend=backend,workers=workers,lines=lines,ms=ms,round=rnd,time=time.time(),kd_delta={k:after[k]-before.get(k,0) for k in after if k!='delegation'},delegation=after.get('delegation'))
 log.write(json.dumps(r)+'\n')
 print(phase,family,backend,workers,lines,r['ok'],round(r['mops'],3),flush=True)
 assert r['ok'],r
 if workers==1 and family=='spin' and backend=='kd':
  assert r['kd_delta'].get('offered',0)==0,r
 return r

for b in ('native','kd'):
 for w in (1,2,8): point('local-check','spin',b,w)
save('dryrun.txt',['/root/kdvenv/bin/python',str(R/'repo/jit/kd_dryrun.py'),'kspin_w','knest_spin_outer','knest_spin_inner.isra.0','kspin_hb_w','--disasm'])
dlog=open(E/'daemon.log','x')
d=subprocess.Popen(['/root/kdvenv/bin/python','-u',str(R/'repo/jit/kd_daemon.py'),'--state',str(E/'learned.json'),'-v'],stdout=dlog,stderr=subprocess.STDOUT)
(E/'daemon.pid').write_text(str(d.pid))
try:
 time.sleep(1)
 assert d.poll() is None
 for w in (8,32): point('learning','spin','kd',w,ms=1000)
 for f in ('spin','nest_spin','spin_raw','spin_hb'):
  for b in ('native','kd'):
   for w in (2,8): point('correctness',f,b,w)
 for w in (1,2,3,8,32,3,2,1): point('phase-change','spin','kd',w,ms=500)
 for rnd in range(3):
  for lines in (1,16):
   for w in (1,2,3,5,8,32):
    order=('native','kd') if (rnd+w)%2==0 else ('kd','native')
    for b in order:
     point('warmup','spin',b,w,lines,ms=250,rnd=rnd)
     point('timing','spin',b,w,lines,ms=1000,rnd=rnd)
 assert d.poll() is None
finally:
 d.send_signal(signal.SIGINT)
 d.wait(timeout=30)
 dlog.close()
 os.close(fd)
 save('rmmod.txt',['rmmod','kd_bench'])
 save('dmesg-after.txt',['dmesg'])
 save('modules-after.txt',['cat','/proc/modules'])
 save('stats-after.txt',['cat',n.STATS])
 (E/'cleanup.json').write_text(json.dumps({'daemon_rc':d.returncode,'benchmark_unloaded':True}))
log.close()
(E/'complete.json').write_text(json.dumps({'complete':True,'finish':time.time()}))
