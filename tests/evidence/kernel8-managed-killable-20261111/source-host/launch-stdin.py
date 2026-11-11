from pathlib import Path
import hashlib,json,os,runpy,subprocess,time
base=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
p=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/managed-killable-input-04')
d=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/managed-killable-driver-04')
args=['/usr/bin/python3', '-B', '/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/managed-killable-input-04/controller.py', '--host-checks-sha256', '3fc26667154f5232125e0e02ea40e11084a39fd475e5a44367d30514bc7d2de0', '--recovery-sha256', '86e4eb06f9b478f3907a3d78b0d2a216d9e3bbbfdf3898a3f628f983b735ac13']
pins={'controller.py': {'bytes': 24520, 'sha256': 'd760565b7ca37b1ed5cd3a8404ca8e4448e4203050e9007e467737bd1ee6789d'}, 'limits.json': {'bytes': 1112, 'sha256': '23f2208dd9fe4f0d55df3cfe7955d10005a99b22995cb2b2e8f744b270a68cb8'}, 'recovery.json': {'bytes': 23263, 'sha256': '86e4eb06f9b478f3907a3d78b0d2a216d9e3bbbfdf3898a3f628f983b735ac13'}, 'actual-argv.json': {'bytes': 328, 'sha256': '6522127c034f90be5a795f00df3ce952683321cc3d73b8f55de032e4f3ec6c39'}}

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
 b=(p/n).read_bytes();need(len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256'],'frozen K04 input differs: '+n)
need(json.loads((p/'actual-argv.json').read_text())==args,'exact argv differs')
need(not os.path.lexists('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/managed-killable-receipts-04') and not os.path.lexists('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/managed-killable-live-04'),'K04 output/runtime leaf already exists')
d.mkdir(mode=0o700)
def put(n,v):
 with (d/n).open('x') as f:json.dump(v,f,indent=2);f.write(chr(10));f.flush();os.fsync(f.fileno())
 fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
put('command.json',{'argv':args,'helper_sha256':pins['controller.py']['sha256'],'input_pins':pins,'idle':current});start=time.time()
with (d/'stdout').open('xb') as stdout,(d/'stderr').open('xb') as stderr:
 child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True);put('dispatch.json',{'pid':child.pid});print(json.dumps({'event':'DISPATCHED','pid':child.pid}),flush=True)
 try:code=child.wait(timeout=1260)
 except subprocess.TimeoutExpired:put('return.json',{'status':'INCOMPLETE_CHILD_RETAINED','pid':child.pid});raise
put('return.json',{'returncode':code,'elapsed_seconds':time.time()-start});print(json.dumps({'event':'RETURNED','returncode':code}),flush=True);raise SystemExit(code)
