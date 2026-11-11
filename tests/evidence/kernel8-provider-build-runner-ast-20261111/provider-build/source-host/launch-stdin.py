from pathlib import Path
import hashlib,json,os,runpy,subprocess,time
base=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
p=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/mm-provider-context-input-de76da8a-01')
d=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/mm-provider-context-driver-de76da8a-01')
args=['/usr/bin/python3', '-B', '/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/mm-provider-context-input-de76da8a-01/controller.py', '--recipe', '/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/mm-provider-context-input-de76da8a-01/recipe.json', '--recipe-sha256', '8534523d3e9af0d3f27be329692c3ced75c8ce6e3b7a18f7ac6ca98f0c9c5c30', '--recovery-sha256', '430e21491f050b3584a327f9ab62ff519efe70a64a22f45344dd7a856e9fd30d']
pins={'source.tar': {'bytes': 1710080, 'sha256': 'ac7e533e1b3cefef7a78d9cdcbe48dbc53fc759bb577d36f7b1335f4ba0863c9'}, 'source-sha256.json': {'bytes': 19793, 'sha256': '71d4362e06dd6e4c3ecbb1c7b42e8d859b3c1c76d1ef4c44767b1e874e04fa60'}, 'source-state.json': {'bytes': 133, 'sha256': '3d396f46e1a26618f1afd6e5dd9480ca9f0c3cb88d54851600e032851846d01f'}, 'controller.py': {'bytes': 16159, 'sha256': 'f560a2215cb3a6b86ca7d2a8e58d12c332cbd6ea09a277bffacf304d2107ba84'}, 'recipe.json': {'bytes': 13785, 'sha256': '8534523d3e9af0d3f27be329692c3ced75c8ce6e3b7a18f7ac6ca98f0c9c5c30'}, 'recovery.json': {'bytes': 23263, 'sha256': '430e21491f050b3584a327f9ab62ff519efe70a64a22f45344dd7a856e9fd30d'}, 'actual-argv.json': {'bytes': 465, 'sha256': 'd403884905b0bb8575abe2a0cc73ddb59aecc9bc6b5581609c269ca00d5f0754'}}

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
 b=(p/n).read_bytes();need(len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256'],'frozen provider input differs: '+n)
need(json.loads((p/'actual-argv.json').read_text())==args,'exact argv differs')
need(not os.path.lexists(base/'mm-provider-context-build-de76da8a-01'),'build output already exists')
d.mkdir(mode=0o700)
def put(n,v):
 with (d/n).open('x') as f:json.dump(v,f,indent=2);f.write(chr(10));f.flush();os.fsync(f.fileno())
 fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
put('command.json',{'argv':args,'helper_sha256':pins['controller.py']['sha256'],'input_pins':pins,'idle':current});start=time.time()
with (d/'stdout').open('xb') as out,(d/'stderr').open('xb') as err:
 child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True);put('dispatch.json',{'pid':child.pid});print(json.dumps({'event':'DISPATCHED','pid':child.pid}),flush=True)
 try:code=child.wait(timeout=960)
 except subprocess.TimeoutExpired:put('return.json',{'status':'INCOMPLETE_CHILD_RETAINED','pid':child.pid});raise
put('return.json',{'returncode':code,'elapsed_seconds':time.time()-start});print(json.dumps({'event':'RETURNED','returncode':code}),flush=True);raise SystemExit(code)
