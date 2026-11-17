import argparse,json,os,pathlib,signal,subprocess,sys,time
R=pathlib.Path('/mnt/kdlock-builds/main-spin-handoff-1d29a9a1-20261117');B=R/'baseline'
E=B/'layout-control';E.mkdir(exist_ok=False)
sys.path.insert(0,str(B/'bench'));import run_nano as n
mods=[('spin','tclock_backend_km'),('mutex','tclock_mutex_backend_km'),('rwlock','tclock_rwlock_backend_km'),('rwsem','tclock_rwsem_backend_km')]
log=open(E/'points.jsonl','x',buffering=1)
for session,layout in enumerate(('two-way','three-way','three-way','two-way')):
 loaded=[];daemon=None;fd=None;dl=None
 try:
  if layout=='three-way':
   for f,m in mods:subprocess.run(['insmod',str(B/'tc'/f/(m+'.ko'))],check=True);loaded.append(m)
  ko=pathlib.Path('/mnt/kdlock-builds/main-spin-20e9db0c-20261117/repo/bench/kd_bench.ko') if layout=='two-way' else B/'bench/kd_bench.ko'
  subprocess.run(['insmod',str(ko)],check=True);loaded.append('kd_bench')
  (E/('symbols-'+str(session)+'.txt')).write_text('\n'.join(l for l in pathlib.Path('/proc/kallsyms').read_text().splitlines() if '[kd_bench]' in l))
  dl=open(E/('daemon-'+str(session)+'.log'),'x')
  daemon=subprocess.Popen(['/root/kdvenv/bin/python','-u',str(R/'repo/jit/kd_daemon.py'),'--state',str(E/('learned-'+str(session)+'.json'))],stdout=dl,stderr=subprocess.STDOUT)
  time.sleep(.3);fd=os.open('/dev/kdbench',os.O_RDWR)
  for rnd in range(3):
   for be in (('native','kd') if (rnd+session)%2==0 else ('kd','native')):
    a=argparse.Namespace(family='spin',backend=be,lines=1,write_pct=100,post=64,first_cpu=0,per_worker=True)
    assert n.run_once(fd,a,5,250)['ok']
    before=n.kd_stats();x=n.run_once(fd,a,5,1000);after=n.kd_stats()
    x.update(session=session,layout=layout,round=rnd,backend=be,kd_delta={k:after[k]-before.get(k,0) for k in after if k!='delegation'},time=time.time())
    log.write(json.dumps(x)+'\n');print(layout,session,rnd,be,x['ok'],x['mops'],flush=True)
    assert x['ok']
 finally:
  if daemon:daemon.send_signal(signal.SIGINT);daemon.wait(timeout=30);dl.close()
  if fd is not None:os.close(fd)
  for _,m in mods:
   if m in loaded:assert (pathlib.Path('/sys/module')/m/'parameters/quiescent').read_text().strip()=='1'
  for m in reversed(loaded):subprocess.run(['rmmod',m],check=True)
(E/'complete.json').write_text(json.dumps({'complete':True,'modules_unloaded':True}))
