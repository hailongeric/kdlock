from pathlib import Path
import hashlib,json,os,runpy,subprocess,time
base=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
p=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/mm-provider-ioctl-input-0798c1ab-01')
d=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/mm-provider-ioctl-driver-0798c1ab-01')
args=['/usr/bin/python3', '-B', '/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/mm-provider-ioctl-input-0798c1ab-01/controller.py', '--recipe', '/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/mm-provider-ioctl-input-0798c1ab-01/recipe.json', '--recipe-sha256', 'ea8c428a9a82f1e4d193a33998c949e58be8e22f79e8e07dfa6231007f0341a7', '--recovery-sha256', '7554d28d150fcc09b391200aa7474d3b871e85c128abe4202aee373decaaf0b6']
pins={'source.tar': {'bytes': 1730560, 'sha256': '3b2512060b7eb3cac27b3a794bb5f0dc833c6ff24cd9866218481b53832a8053'}, 'source-sha256.json': {'bytes': 19794, 'sha256': 'a29e77397367173e51ae091edec94f31798d50f5b9d3b6b90ce31dda0e3b823e'}, 'source-state.json': {'bytes': 133, 'sha256': '15e35cb635d7f67350f6a297bd8231435e33e2a29ab685c9c1264a7a5b15c9b5'}, 'controller.py': {'bytes': 21221, 'sha256': '6d166dac84dcf0d48fbaf5f4ae78411c4d34f82ec8fbc459802c912cde4f3136'}, 'recipe.json': {'bytes': 17397, 'sha256': 'ea8c428a9a82f1e4d193a33998c949e58be8e22f79e8e07dfa6231007f0341a7'}, 'recovery.json': {'bytes': 23263, 'sha256': '7554d28d150fcc09b391200aa7474d3b871e85c128abe4202aee373decaaf0b6'}, 'actual-argv.json': {'bytes': 461, 'sha256': '5ec18dfe88e4483e4d35450b2268465e05b5c93038ded8ef45d4e56830a19c56'}}

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
need(not os.path.lexists(base/'mm-provider-ioctl-build-0798c1ab-01'),'build output already exists')

for name,expected in [('managed-killable-receipts-04/result.json','d7b47fa9e366f666d577b906189e5ca806da2ac769692de380884d89c325f488'),('managed-killable-live-03/result.json','56dcf7cfa9e75645d0ab56cb61809550639119ee0701db84af05c34da302005a'),('recovery-killable-final-01/result.json','40872340905c520739493208ba84323e3f16b6aed40e7119cefc08bf8f5fd1f0')]:need(hashlib.sha256((base/name).read_bytes()).hexdigest()==expected,'closed K evidence differs: '+name)
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
