from pathlib import Path
import hashlib,json,os,runpy,subprocess,time
base=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
p=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01/receipts/repeat-kdrebuild8-mm-input-02')
d=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01/receipts/repeat-kdrebuild8-mm-preflight-driver-02')
args=['/usr/bin/python3', '-B', '/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01/receipts/repeat-kdrebuild8-mm-input-02/repeat.py', '--helper-sha256', '54c5c48385e459e71d17061920463c5d29983327135442635d303c30cc7f99e9', '--plan-sha256', '35f093be246a4959e4e495d4e3e96d54dd9324257c27ad661881e7d1831b5ae9', '--phase', 'preflight', '--recovery-sha256', 'd1db07ce20e2b15c1c4a5056806354a25efa48c0de7ae49897870be466cdd3af']
pins={'repeat.py': {'bytes': 21163, 'sha256': '54c5c48385e459e71d17061920463c5d29983327135442635d303c30cc7f99e9'}, 'plan.json': {'bytes': 7916, 'sha256': '35f093be246a4959e4e495d4e3e96d54dd9324257c27ad661881e7d1831b5ae9'}, 'reference-state.json': {'bytes': 101103, 'sha256': '759208ec01cb280364a8a558bae8e49cdaec88733f5bd72f342d91697268516d'}, 'recovery.json': {'bytes': 23263, 'sha256': 'd1db07ce20e2b15c1c4a5056806354a25efa48c0de7ae49897870be466cdd3af'}}

def need(ok,message):
 if not ok: raise RuntimeError(message)
need(os.geteuid()==0,'VM root required')
need((os.uname().release,Path('/proc/sys/kernel/random/boot_id').read_text().strip(),Path('/proc/sys/kernel/tainted').read_text().strip())==('7.0.0-38-kdrebuild8','e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0','4096'),'exact boot/release/taint differs')
h=base/'native-api-input-01/controller.py';need(hashlib.sha256(h.read_bytes()).hexdigest()=='2c2082e0bf7c807819ec7e28f744c34aaa94f38aa07faf5be1a197b1baced074','idle helper differs')
native=runpy.run_path(str(h));current=native['idle']()
need({line.split()[0] for line in current['modules'].splitlines()}=={'nls_iso8859_1'},'module set differs')
actors=[]
for e in Path('/proc').iterdir():
 if not e.name.isdigit() or int(e.name)==os.getpid():continue
 try:
  comm=(e/'comm').read_text().strip();argv=(e/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
  if comm.startswith('kd-kill') or comm=='mmap-userspace' or any(t in argv for t in ('tests/kernel/rwsem_killable/runner.py','tests/kernel/mmap_api/runner.py')):actors.append({'pid':int(e.name),'comm':comm,'argv':argv})
 except (FileNotFoundError,ProcessLookupError):continue
need(not actors,'prior workload remains: '+repr(actors))
for name in ('kd_rwsem_killable_fixture','kd_rwsem_runtime_fixture','kd_runtime_fixture','kd_rwsem_api','kd_mmap_api'):
 for suffix in ('','_ctl','_events'):need(not (Path('/dev')/(name+suffix)).exists(),'fixture/API device remains')


for n,row in pins.items():
 data=(p/n).read_bytes();need(len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'],'frozen repeat input differs: '+n)
d.mkdir(mode=0o700)
def put(n,value):
 with (d/n).open('x') as f:json.dump(value,f,indent=2);f.write(chr(10));f.flush();os.fsync(f.fileno())
 fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
put('command.json',{'argv':args,'input_pins':pins,'idle':current});start=time.time()
with (d/'stdout').open('xb') as out,(d/'stderr').open('xb') as err:
 child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True);put('dispatch.json',{'pid':child.pid});print(json.dumps({'event':'DISPATCHED','pid':child.pid}),flush=True)
 try:code=child.wait(timeout=240)
 except subprocess.TimeoutExpired:put('return.json',{'status':'INCOMPLETE_CHILD_RETAINED','pid':child.pid});raise
put('return.json',{'returncode':code,'elapsed_seconds':time.time()-start});print(json.dumps({'event':'RETURNED','returncode':code}),flush=True);raise SystemExit(code)
