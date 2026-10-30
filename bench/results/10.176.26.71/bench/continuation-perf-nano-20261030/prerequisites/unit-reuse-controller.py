"""Guest-only fresh basic and affected continuation performance checks; no live modules.

Every attempted block is retained. A timeout never establishes drain. Inputs
are the separately reviewed immutable synchronization receipt and commit.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--commit', required=True)
p.add_argument('--sync', type=Path, required=True)
p.add_argument('--sync-sha256', required=True)
p.add_argument('--output', type=Path, required=True)
args = p.parse_args()
root = Path('/root/host_fs/kdlock')
python = '/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
assert os.geteuid() == 0 and os.uname().release == '7.0.0-38-kdlock1'
assert sys.executable == python and re.fullmatch('[0-9a-f]{40}', args.commit)
assert args.output.is_absolute() and not args.output.is_relative_to(root)
assert not args.output.exists()
assert not os.environ.get('KERNELRELEASE') and not os.environ.get('KBUILD_OUTPUT')
sys.dont_write_bytecode = True
sys.path.insert(0, str(root/'bench/spin_cacheline'))
import bench_runtime as rt
idle = runpy.run_path(str(root/'bench/archive_run.py'))['idle']
idle(Path('/root'), rt.idle)
for proc in Path('/proc').glob('[0-9]*'):
    try:
        words = (proc/'cmdline').read_bytes().split(b'\0')
    except (FileNotFoundError, ProcessLookupError):
        continue
    assert not words or Path(os.fsdecode(words[0])).name not in ('make', 'gmake', 'cc1', 'ld.bfd')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

assert sha(args.sync) == args.sync_sha256
sync = json.loads(args.sync.read_text())
assert sync['git_head'] == args.commit and not sync['git_status']
assert sync['synchronization_completed'] is True and sync['tracked_sha256']

def source_unchanged():
    for name, expected in sync['tracked_sha256'].items():
        relative = Path(name)
        assert not relative.is_absolute() and '..' not in relative.parts
        assert not (root/relative).is_symlink() and sha(root/relative) == expected, name

source_unchanged()
out = args.output
out.mkdir(parents=True)
shutil.copyfile(__file__, out/'controller.py')
shutil.copyfile(args.sync, out/'sync.json')
boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
receipt = dict(completed=False, source_commit=args.commit, boot_id=boot,
               release=os.uname().release, blocks=[], live_modules=False,
               performance_accepted=False, tracked_inputs=len(sync['tracked_sha256']),
               input_sha256={'controller.py':sha(out/'controller.py'), 'sync.json':sha(out/'sync.json')})
env = dict(os.environ, PATH=str(Path(python).parent)+':'+os.environ['PATH'],
           PYTHONDONTWRITEBYTECODE='1',
           KDLOCK_KERNEL_SOURCE='/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/source')

def save():
    temporary = out/'owner.tmp'
    temporary.write_text(json.dumps(receipt, indent=2)+'\n')
    temporary.replace(out/'owner.json')

def run(name, command, limit=600):
    block = dict(name=name, argv=command, started=time.time(), state='STARTING')
    receipt['blocks'].append(block)
    save()
    with (out/(name+'.log')).open('xb') as log:
        child = subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        block.update(pid=child.pid, state='RUNNING')
        save()
        try:
            code = child.wait(timeout=limit)
        except BaseException:
            block.update(state='UNKNOWN_DRAIN', child_returncode=child.poll())
            save()
            raise
    block.update(returncode=code, state='EXITED', finished=time.time(),
                 log_sha256=sha(out/(name+'.log')))
    save()
    assert code == 0, name
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot
    source_unchanged()

drivers = [
    'spin/test_spin_batch.py',
    'spin/test_spin_shadow.py',
    'spin/test_spin_outer_progress.py',
    'spin/test_spin_proxy_context.py',
    'spin/test_spin_batch_context.py',
    'mutex/test_mutex_origin_instruction.py',
    'execution/test_bench_completion.py',
]
receipt['unit_selection'] = {
    'fresh': True, 'prior_checks_reused': False,
    'basic': ['basic/test_control_call', 'basic/test_daemon_policy'],
    'python_drivers': drivers, 'expected_passes': 2 + len(drivers),
}
for name in drivers:
    assert name.startswith(('spin/', 'mutex/', 'execution/'))
    assert 'tests/unit/' + name in sync['tracked_sha256'], name
save()

try:
    run('kernel-identity', [python, 'kernel_integration/linux70/verify.py', '--running'])
    run('unit', ['make', '-C', str(root/'tests/unit'), 'run',
                 'PY_TESTS='+' '.join(drivers)], limit=1200)
    assert f"Unit tests: {2 + len(drivers)} passed, 0 failed" in (out/'unit.log').read_text()
    from provider.prepare import prepare, production_files
    selected = {str(path):sha(root/path) for path in production_files(root)}
    assert selected and all(sync['tracked_sha256'].get(name) == value
                            for name,value in selected.items()), 'untracked/changed provider input'
    overlay = {name:sync['tracked_sha256']['bench/spin_cacheline/provider/'+name]
               for name in ('observation.patch', 'kd_bench.c', 'kd_bench.h')}
    manifest = prepare(out/'provider', root)
    assert manifest['production'] == selected and manifest['observation'] == overlay
    receipt['provider_variant'] = 'benchmark observation overlay; selftest=0; diagnostics=0'
    receipt['provider_manifest_sha256'] = sha(out/'provider/manifest.json')
    run('build-provider', ['make', '-C', str(out/'provider/kernel_module'),
        'KDIR=/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build', 'W=1', 'KDLOCK_SELFTEST=0',
        'KDLOCK_NUMA=1', 'KDLOCK_SPIN_BATCH=1024', 'KDLOCK_MUTEX_BATCH=1024',
        'KDLOCK_MUTEX_NUMA_BOUNDARY=1024', 'KDLOCK_MUTEX_DIAGNOSTICS=0', 'UBSAN_SANITIZE=n'])
    idle(out, rt.idle)
    source_unchanged()
    receipt.update(completed=True, final_idle=True,
        provider_sha256=sha(out/'provider/kernel_module/kdlock_km.ko'))
except BaseException as error:
    receipt['error'] = repr(error)
    raise
finally:
    save()
print('COMPLETE fresh continuation performance units/build', flush=True)
