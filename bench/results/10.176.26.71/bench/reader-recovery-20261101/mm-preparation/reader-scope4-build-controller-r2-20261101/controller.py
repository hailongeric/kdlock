"""VM-only staged recipe build, after the frozen Nano campaign has drained."""
from pathlib import Path
import hashlib,json,os,runpy,shutil,subprocess,sys,time
root=Path('/root/host_fs/kdlock');py='/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
config=Path('/tmp/kdlock-reader-scope4-kernel-r2-20261101.json');c=json.loads(config.read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert os.geteuid()==0 and os.uname().release==c['running_release'] and Path('/proc/sys/kernel/random/boot_id').read_text().strip()==c['boot_id']
sys.path.insert(0,str(root/'bench/spin_cacheline'));import bench_runtime as rt
idle=runpy.run_path(str(root/'bench/archive_run.py'))['idle'];idle(root,rt.idle)
assert shutil.disk_usage('/mnt/kdlock-builds2').free>50*1024**3
out=Path('/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/reader-scope4-build-controller-r2-20261101');out.mkdir(parents=True,exist_ok=False)
r=dict(completed=False,boot_id=c['boot_id'],source_commit=c['commit'],steps=[],started=time.time());(out/'controller.py').write_bytes(Path(__file__).read_bytes());(out/'config.json').write_bytes(config.read_bytes())
def save():(out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
def run(name,cmd,bound):
 row=dict(name=name,argv=cmd,started=time.time());r['steps'].append(row);save()
 with (out/(name+'.log')).open('xb') as f:
  child=subprocess.Popen(cmd,cwd=root,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PATH=str(Path(py).parent)+':/usr/sbin:/usr/bin:/sbin:/bin'),stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);row['pid']=child.pid;save();row['returncode']=child.wait(timeout=bound)
 row['finished']=time.time();save();assert row['returncode']==0,name
try:
 run('extract',[py,'/tmp/kdlock-reader-scope4-extract-r2-20261101.py'],300)
 extracted=json.loads(Path('/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/reader-scope4-extract-r2-20261101/result.json').read_text());assert extracted['completed'] and extracted['source_commit']==c['commit']
 source=Path('/root/kdlock-build-output/linux-7.0.0-38-kdscope1');target=Path(c['baseline_kernel'])/'build'
 assert source.is_dir() and not source.is_symlink() and sha(source/'.config')=='7131e48d4bb556e54f9fc287c04e6fab33a3de80eb923a215872a01a07609f4b'
 assert target.is_dir() and not target.is_symlink()
 if target.is_mount():assert os.path.samefile(source,target)
 else:
  assert not list(target.iterdir());run('baseline-build-bind',['mount','--bind',str(source),str(target)],30)
 assert target.is_mount() and os.path.samefile(source,target) and sha(target/'.config')==sha(source/'.config')
 for name in ['test_mmap_writer_observation.py','test_mmap_writer_return_sites.py']:
  run(name,[py,str(Path(c['recipe'])/'tests/unit/bench'/name)],600)
 controller='/tmp/kdlock-writer-queue-kernel-20261031.py';assert sha(controller)=='3d9f3c82f60e29b40d96a2207ada07f65081af990bf12b36df00f75ee1ae27ff'
 for phase,bound in [('prepare',4200),('build',4400)]:
  run(phase,[py,controller,phase,'--config',str(config),'--sha256',sha(config)],bound)
  result=json.loads((Path(c['evidence'])/phase/'result.json').read_text());assert result['passed'] and result['state']=='COMPLETE' and not result.get('drain_unknown')
 idle(root,rt.idle);r.update(completed=True,build_result=str(Path(c['evidence'])/'build/result.json'),build_result_sha256=sha(Path(c['evidence'])/'build/result.json'))
except BaseException as e:r['error']=repr(e);raise
finally:r['finished']=time.time();save();print(json.dumps(r),flush=True)
