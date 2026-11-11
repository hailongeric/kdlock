from pathlib import Path
import hashlib,json,os,runpy,subprocess,time
base=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
p=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/host-support-5c14b483-input-01')
d=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/host-checks-5c14b483-driver-01')
args=['/usr/bin/python3', '-B', '/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/host-support-5c14b483-input-01/checks.py']
pins={'source.tar': {'bytes': 1730560, 'sha256': '35e9d05d6a4b88a3d3bffe95ad1f6674388486ff6e06d4be210aece753512989'}, 'source-sha256.json': {'bytes': 19794, 'sha256': '6a14d26236343e37ae43a30c6e441783f979299b426c0a7b9fbbca9154f09645'}, 'source-state.json': {'bytes': 133, 'sha256': '95e3a54def7e87c595164b80ea329751f571a95ae64bf3dae821e1eacc4263cb'}, 'checks.py': {'bytes': 11309, 'sha256': 'a6047e2d327fcffdd7f8a3365c2eae09eb9c7a60492dbd3670e38ba32dfa0a84'}, 'argv.json': {'bytes': 140, 'sha256': '72519c7196a4576b967ac43d8956c81f9ab8918773a12e177ebc2efb3f0c1d7d'}}

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
 b=(p/n).read_bytes();need(len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256'],'frozen AST input differs: '+n)
need(json.loads((p/'argv.json').read_text())==args,'exact argv differs')
need(not os.path.lexists('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/host-checks-5c14b483-01'),'AST output already exists')
d.mkdir(mode=0o700)
def put(n,v):
 with (d/n).open('x') as f:json.dump(v,f,indent=2);f.write(chr(10));f.flush();os.fsync(f.fileno())
 fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
put('command.json',{'argv':args,'helper_sha256':pins['checks.py']['sha256'],'input_pins':pins,'idle':current});start=time.time()
with (d/'stdout').open('xb') as stdout,(d/'stderr').open('xb') as stderr:
 child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True);put('dispatch.json',{'pid':child.pid});print(json.dumps({'event':'DISPATCHED','pid':child.pid}),flush=True)
 try:code=child.wait(timeout=180)
 except subprocess.TimeoutExpired:put('return.json',{'status':'INCOMPLETE_CHILD_RETAINED','pid':child.pid});raise
put('return.json',{'returncode':code,'elapsed_seconds':time.time()-start});print(json.dumps({'event':'RETURNED','returncode':code}),flush=True);raise SystemExit(code)
