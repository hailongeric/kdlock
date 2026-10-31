"""One VM-only kernel preparation or build step from an exact frozen recipe."""
import argparse,hashlib,json,os,runpy,shutil,stat,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','build'));p.add_argument('--config',type=Path,required=True);p.add_argument('--sha256',required=True);a=p.parse_args()
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(4*1024**2),b''):h.update(b)
 return h.hexdigest()
assert sha(a.config)==a.sha256
c=json.loads(a.config.read_text());root=Path(c['recipe']);manifest=Path(c['manifest']);source=Path(c['source']);build=Path(c['build']);old=Path(c['baseline_kernel']);base=source.parent;out=Path(c['evidence'])/a.phase
assert os.geteuid()==0 and sys.executable==c['python'] and os.uname().release==c['running_release']
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==c['boot_id']
assert sha(manifest)==c['manifest_sha256'];m=json.loads(manifest.read_text());assert m['source_commit']==c['commit']
def recipe_check():
 for n,r in m['files'].items():
  q=root/n;assert q.is_file() and not q.is_symlink() and sha(q)==r['sha256'] and stat.S_IMODE(q.stat().st_mode)==r['mode'],n
recipe_check();sys.path.insert(0,str(root/'bench/spin_cacheline'))
import bench_runtime as rt
idle=runpy.run_path(str(root/'bench/archive_run.py'))['idle'];idle(root,rt.idle);idle(Path('/root/host_fs/kdlock'),rt.idle)
assert shutil.disk_usage('/').free>2*1024**3 and shutil.disk_usage(base.parent).free>(50 if a.phase=='prepare' else 34)*1024**3
out.mkdir(parents=True,exist_ok=False);shutil.copy2(a.config,out/'config.json');shutil.copy2(__file__,out/'controller.py');shutil.copy2(manifest,out/'recipe-manifest.json')
r=dict(passed=False,state='STARTING',phase=a.phase,source_commit=c['commit'],provider_commit=c['provider_commit'],boot_id=c['boot_id'],release=c['release'],source=str(source),build=str(build),blocks=[],installed=False)
def save():
 t=out/'result.tmp';t.write_text(json.dumps(r,indent=2)+'\n');t.replace(out/'result.json')
env={k:v for k,v in os.environ.items() if not k.startswith('LC_') and k not in ('LANG','LANGUAGE','KERNELRELEASE')};env.update(LANG='C',LC_ALL='C',PYTHONDONTWRITEBYTECODE='1',PATH=str(Path(c['python']).parent)+':'+os.environ['PATH'])
def group_members(group):
 rows=[]
 for path in Path('/proc').glob('[0-9]*/stat'):
  try:
   fields=path.read_text().rsplit(')',1)[1].split()
   if int(fields[2])==group:rows.append(dict(pid=int(path.parent.name),state=fields[0]))
  except (FileNotFoundError,ProcessLookupError):pass
 return rows
def run(name,argv,timeout=600):
 row=dict(name=name,argv=list(map(str,argv)),started=time.time());r['blocks'].append(row);save()
 with (out/(name+'.log')).open('xb') as f:
  child=subprocess.Popen(row['argv'],cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);row['pid']=child.pid;row['process_group']=child.pid;r['drain_unknown']=True;save()
  try:rc=child.wait(timeout=timeout)
  except subprocess.TimeoutExpired:row['timed_out']=True;save();raise
 row.update(returncode=rc,remaining_processes=group_members(child.pid),finished=time.time(),log_sha256=sha(out/(name+'.log')));save()
 assert not row['remaining_processes'],name
 r['drain_unknown']=False;save();assert rc==0,name
make=['make','-C',source,'O='+str(build),'ARCH=x86','CC=x86_64-linux-gnu-gcc','KERNELRELEASE='+c['release']]
try:
 if a.phase=='prepare':
  assert not base.exists();ub=Path(c['ubuntu']);mm=Path(c['mmap_prepare']);api=Path(c['api_prepare']);assert not mm.exists() and not api.exists()
  old_comp=json.loads((old/'composition.json').read_text());assert old_comp['passed']
  old_named=old_comp['final_source_files'];assert all(sha(old/'source'/n)==h for n,h in old_named.items())
  for label,script in [('identity','tests/unit/infrastructure/test_linux70_identity.py'),('scope-identity','tests/unit/infrastructure/test_linux70_scope_identity.py'),('profiles','tests/unit/bench/test_kernel_profiles.py'),('shared-mm','bench/mmap_writer/test_linux70.py'),('mmap1','tests/unit/bench/test_mmap1.py')]:
   run('unit-'+label,[c['python'],script],600)
  run('prepare-mmap',[c['python'],'kernel_integration/linux70/prepare_mmap.py','--source',ub/'linux-7.0.0','--output',mm])
  run('prepare-api',[c['python'],'kernel_integration/real_api/prepare.py','--source',ub/'linux-7.0.0','--output',api])
  run('compose',[c['python'],'kernel_integration/linux70/compose_scope.py','--source',ub/'linux-7.0.0','--output',base,'--mmap-prepare',mm/'prepare.json','--api-prepare',api/'prepare.json','--acquisition',ub/'source-acquisition.json','--source-archives',ub/'downloads'],900)
  comp=json.loads((base/'composition.json').read_text());assert comp['passed'];named=comp['final_source_files'];assert named.keys()==old_named.keys()
  delta={n:dict(before=old_named[n],after=h) for n,h in named.items() if h!=old_named[n]}
  assert set(delta)==set(c['expected_changed_generated_files']),delta
  r['generated_source_delta']=delta;r['source_named_sha256']=named
  assert all(sha(source/n)==h for n,h in named.items())
  build.mkdir();shutil.copy2(old/'build/.config',build/'.config');sign=source/'debian/scripts/sign-module';before=sha(sign);sign.chmod(sign.stat().st_mode|0o100);assert sha(sign)==before
  run('configure',[source/'scripts/config','--file',build/'.config','--set-str','VERSION_SIGNATURE',c['signature']])
  run('rustavailable',make+['rustavailable'],120);run('olddefconfig',make+['olddefconfig'],180)
  v=runpy.run_path(str(root/'kernel_integration/linux70/verify.py'));oc,nc=v['config_values'](old/'build/.config'),v['config_values'](build/'.config')
  diff={k:dict(before=oc.get(k),after=nc.get(k)) for k in oc.keys()|nc.keys() if oc.get(k)!=nc.get(k)}
  assert diff=={'CONFIG_VERSION_SIGNATURE':dict(before='"KDLock Ubuntu 7.0.0-38.38 kdscope1 7.0.14"',after='"'+c['signature']+'"')},diff
  v['check_variant_config'](nc,c['variant_native']);r['config_delta']=diff;r['config_sha256']=sha(build/'.config')
  run('prepare',make+['prepare']);run('affected-objects',make+['-j32','fs/file.o','fs/pipe.o','fs/locks.o','fs/proc/fd.o','io_uring/openclose.o','kernel/watch_queue.o','kernel/locking/kd_api/','kernel/locking/kd_mmap/'],1200)
 else:
  prior_dir=Path(c['evidence'])/'prepare';prior=json.loads((prior_dir/'result.json').read_text())
  assert sha(prior_dir/'config.json')==a.sha256 and prior['passed'] and prior['state']=='COMPLETE' and prior['phase']=='prepare' and not prior.get('drain_unknown')
  assert prior['source_commit']==c['commit']
  assert all(prior[k]==c[k] for k in ('provider_commit','boot_id','release','source','build'))
  assert sha(build/'.config')==prior['config_sha256'];assert all(sha(source/n)==h for n,h in prior['source_named_sha256'].items())
  r['config_sha256']=prior['config_sha256'];r['source_named_sha256']=prior['source_named_sha256']
  run('kernel',make+['-j32','bzImage','modules'],4200)
  r['outputs']={n:dict(bytes=(build/n).stat().st_size,sha256=sha(build/n)) for n in ('vmlinux','arch/x86/boot/bzImage','System.map','Module.symvers','.config','modules.order','include/config/kernel.release','include/generated/utsrelease.h')}
  assert (build/'include/config/kernel.release').read_text().strip()==c['release']
  assert '#define LINUX_VERSION_CODE 458766' in (build/'include/generated/uapi/linux/version.h').read_text()
 assert sha(build/'.config')==r['config_sha256'] and all(sha(source/n)==h for n,h in r['source_named_sha256'].items())
 recipe_check();idle(root,rt.idle);assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==c['boot_id']
 r.update(passed=True,state='COMPLETE',recipe_unchanged=True,source_named_unchanged=True,data_free=shutil.disk_usage(base).free)
except BaseException as e:r.update(state='FAILED',error=repr(e));raise
finally:r['finished']=time.time();save()
print(json.dumps(dict(passed=r['passed'],phase=a.phase,output=str(out))))
