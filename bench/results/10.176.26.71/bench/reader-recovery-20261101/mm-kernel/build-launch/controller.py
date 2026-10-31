"""VM-only staged recipe build, after the frozen Nano campaign has drained."""
from pathlib import Path
import hashlib,json,os,runpy,shutil,subprocess,sys,time
root=Path('/root/host_fs/kdlock');py='/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
config=Path('/tmp/kdlock-reader-scope4-kernel-r3-20261101.json');c=json.loads(config.read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert os.geteuid()==0 and os.uname().release==c['running_release'] and Path('/proc/sys/kernel/random/boot_id').read_text().strip()==c['boot_id']
sys.path.insert(0,str(root/'bench/spin_cacheline'));import bench_runtime as rt
idle=runpy.run_path(str(root/'bench/archive_run.py'))['idle'];idle(root,rt.idle)
assert shutil.disk_usage('/mnt/kdlock-builds2').free>50*1024**3
out=Path('/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/reader-scope4-build-controller-r3-20261101');out.mkdir(parents=True,exist_ok=False)
r=dict(completed=False,boot_id=c['boot_id'],source_commit=c['commit'],steps=[],started=time.time());(out/'controller.py').write_bytes(Path(__file__).read_bytes());(out/'config.json').write_bytes(config.read_bytes())
def save():(out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
def run(name,cmd,bound):
 row=dict(name=name,argv=cmd,started=time.time());r['steps'].append(row);save()
 with (out/(name+'.log')).open('xb') as f:
  child=subprocess.Popen(cmd,cwd=root,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PATH=str(Path(py).parent)+':/usr/sbin:/usr/bin:/sbin:/bin'),stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);row['pid']=child.pid;save();row['returncode']=child.wait(timeout=bound)
 row['finished']=time.time();save();assert row['returncode']==0,name
try:
 controller='/tmp/kdlock-reader-scope4-kernel-resume-20261101.py';assert sha(controller)=='08bf976c739f412a7cf2753e2cdc041d868d4d77c10c74f72c8653cd83172dc0'
 for phase,bound in [('prepare',4200),('build',4400)]:
  run(phase,[py,controller,phase,'--config',str(config),'--sha256',sha(config)],bound)
  result=json.loads((Path(c['evidence'])/phase/'result.json').read_text());assert result['passed'] and result['state']=='COMPLETE' and not result.get('drain_unknown')
 idle(root,rt.idle);r.update(completed=True,build_result=str(Path(c['evidence'])/'build/result.json'),build_result_sha256=sha(Path(c['evidence'])/'build/result.json'))
except BaseException as e:r['error']=repr(e);raise
finally:r['finished']=time.time();save();print(json.dumps(r),flush=True)
