from pathlib import Path
import ast,datetime,hashlib,json,os,subprocess,sys,time
base=Path(sys.argv[1]);repo=base/'input';out=base/'module-build';receipts=base/'build-receipts'
receipts.mkdir(mode=0o700);out.mkdir(mode=0o700)
manifest=json.loads((base/'source-manifest.json').read_text())
def digest(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for data in iter(lambda:f.read(1048576),b''):h.update(data)
 return h.hexdigest()
def verify_source():
 actual={p.relative_to(repo).as_posix():{'bytes':p.stat().st_size,'sha256':digest(p)} for p in repo.rglob('*') if p.is_file()}
 if actual!=manifest:raise ValueError('immutable source manifest differs')
 return len(actual)
kernel=Path('/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f')
pins={'vmlinux':'7de39e303412b36ea7dd36f7260183669bc4d2829569dd1e3ac9bc2426e91809','.config':'31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483','System.map':'47cc1e87e95f2e118f9a20ff01ec8e31dee1f9d0f650ef9649392a25db98395f','Module.symvers':'2533c2a4becc4f99f8dacc38e9480608c9032e4c0f3d06a9b4a2fe51fda6752b'}
if os.uname().release!='7.0.0-38-kdrebuild2':raise ValueError('wrong target kernel')
if any(l.startswith('kd_runtime_fixture ') for l in Path('/proc/modules').read_text().splitlines()):raise ValueError('fixture remains loaded')
if any(Path('/dev').glob('kd_runtime_fixture*')):raise ValueError('fixture devices remain')
if {n:digest(kernel/'build'/n) for n in pins}!=pins:raise ValueError('kernel pins differ')
files_before=verify_source();ast.parse((repo/'tests/kernel/run_runtime_fixture.py').read_text())
args=['make','-C',str(kernel/'source'),'O='+str(kernel/'build'),'M='+str(repo/'tests/kernel/payload'),'MO='+str(out),'-j8','V=1','modules']
record={'argv':args,'source_state':json.loads((base/'source-state.json').read_text()),'start_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'taint_before':Path('/proc/sys/kernel/tainted').read_text().strip(),'kernel_pins':pins,'verified_source_before':files_before,'runner_ast':'PASS','observer_seconds':180,'policy':'Normal target compiler flags; observer timeout retains child and establishes no drain. No module load.'}
(receipts/'command.json').write_text(json.dumps(record,indent=2)+'\n')
start=time.monotonic()
with (receipts/'build.log').open('x') as log:
 child=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'LC_ALL':'C','LANG':'C'},start_new_session=True)
 record['pid']=child.pid
 (receipts/'command.json').write_text(json.dumps(record,indent=2)+'\n')
 while child.poll() is None and time.monotonic()-start<180:time.sleep(1)
 code=child.poll()
record.update(returncode=code,elapsed_seconds=time.monotonic()-start,end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='RETURNED' if code is not None else 'RUNNING_AFTER_OBSERVER_DEADLINE',taint_after=Path('/proc/sys/kernel/tainted').read_text().strip())
if code is not None:
 record['verified_source_after']=verify_source()
 record['kernel_pins_after']={n:digest(kernel/'build'/n) for n in pins}
 if record['kernel_pins_after']!=pins:raise ValueError('kernel outputs changed')
 if code==0:
  module=out/'kd_runtime_fixture.ko'
  record['module']={'path':str(module),'bytes':module.stat().st_size,'sha256':digest(module)}
  for label,argv in [('modinfo',['modinfo',str(module)]),('symbols',['nm','-S','--defined-only',str(module)])]:
   result=subprocess.run(argv,capture_output=True,text=True,timeout=15,check=True)
   (receipts/(label+'.txt')).write_text(result.stdout+result.stderr)
record['build_log_sha256']=digest(receipts/'build.log')
(receipts/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2));print((receipts/'build.log').read_text()[-5000:])
raise SystemExit(code if code is not None else 124)
