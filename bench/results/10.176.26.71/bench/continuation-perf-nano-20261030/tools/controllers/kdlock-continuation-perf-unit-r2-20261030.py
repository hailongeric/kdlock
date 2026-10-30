"""Guest-only selective correction checks and fresh provider build; no live modules.

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
p.add_argument('--prior-unit', type=Path, required=True)
p.add_argument('--prior-unit-sha256', required=True)
p.add_argument('--prior-unit-log-sha256', required=True)
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
PRIOR_COMMIT = '6bf690204fdf954ab9076a762000833ec18e6261'
CURRENT_COMMIT = 'f7a84065e84474380faa37eeadfdf534abd72a68'
PRIOR_HASHES = {
    'owner.json': '313a1ad0a38891530ec29cd2ceb5aa781d1236056b94ea21fbb47738d32a7bea',
    'unit.log': '52068e4078c5491ab420bbc729e7bb844be55fa42f475f8823df26dfb30be757',
    'sync.json': 'e8f8c60840496de5c3636039a214321ce15b8b1f241a929e812c3f1c899b3e43',
    'controller.py': 'e60a9285bca40716fdad9dcd409026471fadbc771508eccab4483797a4247b71',
}
PRIOR_DRIVERS = [
    'spin/test_spin_batch.py', 'spin/test_spin_shadow.py',
    'spin/test_spin_outer_progress.py', 'spin/test_spin_proxy_context.py',
    'spin/test_spin_batch_context.py', 'mutex/test_mutex_origin_instruction.py',
    'execution/test_bench_completion.py',
]
REUSED_DRIVERS = [name for name in PRIOR_DRIVERS
                  if name != 'spin/test_spin_batch_context.py']
ALLOWED_CHANGED = {
    'tests/unit/spin/spin_batch_context_fixture.c',
    'bench/results/10.176.26.71/bench/continuation-nano-20261030/README.md',
}
assert args.commit == CURRENT_COMMIT
assert args.prior_unit.is_absolute() and not args.prior_unit.is_relative_to(root)
prior_dir = args.prior_unit.parent
prior_paths = {name: prior_dir/name for name in PRIOR_HASHES}
prior_paths['owner.json'] = args.prior_unit
assert args.prior_unit_sha256 == PRIOR_HASHES['owner.json']
assert args.prior_unit_log_sha256 == PRIOR_HASHES['unit.log']
assert all(sha(path) == PRIOR_HASHES[name] for name,path in prior_paths.items())
prior = json.loads(args.prior_unit.read_text())
prior_sync = json.loads(prior_paths['sync.json'].read_text())
prior_log = prior_paths['unit.log'].read_text()
assert prior['source_commit'] == PRIOR_COMMIT and prior['completed'] is False
assert prior.get('error') == "AssertionError('unit')" and prior['live_modules'] is False
assert prior['release'] == os.uname().release
assert prior['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert prior['input_sha256'] == {name:PRIOR_HASHES[name]
                                  for name in ('controller.py','sync.json')}
assert [row['name'] for row in prior['blocks']] == ['kernel-identity','unit']
assert all(row['state'] == 'EXITED' for row in prior['blocks'])
assert [row['returncode'] for row in prior['blocks']] == [0,2]
assert prior['blocks'][1]['log_sha256'] == PRIOR_HASHES['unit.log']
assert prior['blocks'][1]['argv'] == ['make','-C',str(root/'tests/unit'),'run',
                                     'PY_TESTS='+' '.join(PRIOR_DRIVERS)]
assert prior['unit_selection'] == {
    'fresh': True, 'prior_checks_reused': False,
    'basic': ['basic/test_control_call','basic/test_daemon_policy'],
    'python_drivers': PRIOR_DRIVERS, 'expected_passes': 9,
}
assert prior_sync['git_head'] == PRIOR_COMMIT and not prior_sync['git_status']
assert prior_sync['synchronization_completed'] is True
assert set(prior_sync['tracked_sha256']) == set(sync['tracked_sha256'])
assert len(sync['tracked_sha256']) == prior['tracked_inputs'] == 5922
changed = {name:dict(prior=old,current=sync['tracked_sha256'][name])
           for name,old in prior_sync['tracked_sha256'].items()
           if old != sync['tracked_sha256'][name]}
assert set(changed) == ALLOWED_CHANGED, changed
assert 'Unit tests: 8 passed, 1 failed' in prior_log
# The basic daemon negative controls deliberately print two missing-file
# tracebacks; only the third is the failed context-mutant compilation.
assert prior_log.count('Traceback (most recent call last):') == 3
assert prior_log.count('FileNotFoundError:') == 2
assert 'missing-generic-refresh-0' in prior_log and '-Werror=unused-function' in prior_log
for evidence in (
    'spin batch PASS: cache invalidation, per-CPU sum/max, physical/virtual prefetch',
    '[PASS] test_spin_shadow',
    'spin outer production progress: 18175 checks, 0 failures',
    'spin proxy context: 256 capture states, IF matches and preserved physical state',
    'origin instruction: production two-thread handshake, retained packet/owner/node, refusal and post-ACK next publication passed',
    'production JIT entry scope: 9846 checks, 0 failures',
):
    assert evidence in prior_log, evidence
out = args.output
out.mkdir(parents=True)
shutil.copyfile(__file__, out/'controller.py')
shutil.copyfile(args.sync, out/'sync.json')
reuse_dir = out/'unit-reuse'
reuse_dir.mkdir()
for name,path in prior_paths.items():
    shutil.copyfile(path,reuse_dir/name)
    assert sha(reuse_dir/name) == PRIOR_HASHES[name]

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

drivers = ['spin/test_spin_batch_context.py']
receipt['unit_selection'] = {
    'fresh': False, 'prior_checks_reused': True,
    'basic': ['basic/test_control_call', 'basic/test_daemon_policy'],
    'python_drivers': drivers, 'expected_passes': 3,
    'reused_python_drivers': REUSED_DRIVERS,
    'effective_selected_checks': 9,
}
receipt['unit_reuse'] = {
    'prior_source_commit': PRIOR_COMMIT, 'current_source_commit': args.commit,
    'prior_owner_completed': False, 'prior_error': prior['error'],
    'prior_unit_returncode': 2, 'prior_unit_log_sha256': PRIOR_HASHES['unit.log'],
    'prior_failure': 'batch context omission mutant compile-only unused accessor',
    'prior_unit_argv': prior['blocks'][1]['argv'],
    'reused_python_drivers': REUSED_DRIVERS, 'reused_python_passes': 6,
    'same_tracked_path_set': True, 'compared_tracked_inputs': len(sync['tracked_sha256']),
    'changed_inputs': changed, 'evidence_directory': 'unit-reuse',
    'retained_sha256': PRIOR_HASHES,
}
save()

try:
    assert 'tests/unit/' + drivers[0] in sync['tracked_sha256']
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
print('COMPLETE selective continuation performance units/build', flush=True)
