"""One explicit temporary common-source bind or ordinary unbind in the VM."""
import argparse, hashlib, json, os, runpy, stat, subprocess, sys, time
from pathlib import Path
sys.dont_write_bytecode = True
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('action', choices=('bind', 'unbind'))
p.add_argument('--arm', choices=('baseline', 'candidate'), required=True)
p.add_argument('--boot-id', required=True)
p.add_argument('--config', type=Path, required=True)
p.add_argument('--config-sha256', required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--prior', type=Path)
p.add_argument('--prior-sha256')
a = p.parse_args()
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
assert sha(a.config) == a.config_sha256
c = json.loads(a.config.read_bytes()); arm = c['arms'][a.arm]
root = Path('/root/host_fs/kdlock'); recipe = Path(c['harness']['source'])
assert os.geteuid() == 0 and sys.executable == c['python']
assert c['schema'] == 1 and c['harness']['commit'] == '7814c61a0be20f5db3b9fb41b6079ef6d2938b5f'
assert os.uname().release == arm['release']
def boot(): return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot() == a.boot_id
assert [x for x in Path('/proc/cmdline').read_text().split() if x.startswith('kd_mmap=')] == ['kd_mmap=on']
assert sha(c['harness']['manifest']['path']) == c['harness']['manifest']['sha256']
manifest = json.loads(Path(c['harness']['manifest']['path']).read_bytes())
assert manifest['source_commit'] == c['harness']['commit']
for name in ('bench/archive_run.py', 'bench/spin_cacheline/bench_runtime.py'):
    assert sha(recipe/name) == manifest['files'][name]['sha256']
sys.path.insert(0, str(recipe/'bench/spin_cacheline')); import bench_runtime as rt
idle = runpy.run_path(str(recipe/'bench/archive_run.py'))['idle']
idle(recipe, rt.idle); idle(root, rt.idle)
leaves = ('kernel_module/kd_rwsem.c', 'kernel_module/kd_exec.c', 'include/kd_mutex_types.h')
def underlying():
    s = root.stat()
    return dict(device=s.st_dev, inode=s.st_ino, mode=stat.S_IMODE(s.st_mode),
                files={n: sha(root/n) for n in leaves})
assert a.output.is_absolute() and a.output.resolve() == a.output
assert a.output.parent == Path('/mnt/kdlock-builds2/kdlock-evidence/10.176.26.71/tests/writer-queue-mm-source-view-20261031')
a.output.mkdir(parents=True, exist_ok=False)
r = dict(passed=False, completed=False, action=a.action, arm=a.arm, boot_id=a.boot_id,
         config_sha256=a.config_sha256, controller_sha256=sha(__file__), root=str(root),
         recipe=str(recipe), started=time.time(), commands=[], state='STARTING')
def save():
    q=a.output/'result.tmp';q.write_text(json.dumps(r,indent=2)+'\n');q.replace(a.output/'result.json')
def command(argv):
    row=dict(argv=list(map(str,argv)),started=time.time());r['commands'].append(row);save()
    v=subprocess.run(row['argv'],capture_output=True,timeout=30)
    row.update(returncode=v.returncode,stdout=v.stdout.decode(),stderr=v.stderr.decode(),finished=time.time());save()
    assert v.returncode == 0, row
save()
try:
    if a.action == 'bind':
        assert a.prior is None and not root.is_mount() and not root.is_symlink()
        assert sha(root/'kernel_module/kd_rwsem.c') == 'dc1d445c1dd0566bca7833daaa84105e8224d53d36699fc7175c0304437e7b6b'
        r['underlying']=underlying();save()
        command(['mount','--bind',recipe,root])
        command(['mount','-o','remount,bind,ro',root])
        assert root.is_mount() and os.path.samefile(root,recipe) and os.statvfs(root).f_flag & os.ST_RDONLY
    else:
        assert a.prior and sha(a.prior)==a.prior_sha256
        old=json.loads(a.prior.read_bytes())
        assert old['passed'] and old['completed'] and old['action']=='bind'
        assert all(old[k]==r[k] for k in ('arm','boot_id','config_sha256','controller_sha256','root','recipe'))
        assert root.is_mount() and os.path.samefile(root,recipe) and os.statvfs(root).f_flag & os.ST_RDONLY
        r['prior']=dict(path=str(a.prior),sha256=a.prior_sha256);r['underlying']=old['underlying'];save()
        command(['umount',root])
        assert not root.is_mount() and underlying()==old['underlying']
    idle(recipe,rt.idle);idle(root,rt.idle);assert boot()==a.boot_id and sha(a.config)==a.config_sha256
    r.update(passed=True,completed=True,final_idle=True,state='COMPLETE')
except BaseException as error:
    r.update(state='FAILED',error=repr(error));raise
finally:
    r['finished']=time.time();save()
print(json.dumps(r))
