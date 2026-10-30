"""One fresh VM functional phase of an explicit performance-candidate generation.

No timing, automatic retry, source synchronization, reboot or force unload.
All four phases repeat for this source generation, including basic.
Each invocation uses a fresh host capture and immutable unit/source receipts.
"""
import argparse
import datetime
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

ROOT = Path('/root/host_fs/kdlock')
PYTHON = '/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
BOOT = '677b7afa-5358-4ece-a650-5f4a4adecd55'
SNAPSHOT = 'linux70-kdlock1-clean-20261027'
KDIR = '/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build'
BUNDLE = '/root/kdlock-kernel-baselines/linux70-kdlock1-20261027'
UNIT_CONTROLLER = 'fe9208ce981a4e0d524c8366fe7cce78683f45235316e0ef85514c4555fce996'

def require(value, message):
    if not value:
        raise RuntimeError(message)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load(path):
    return json.loads(path.read_text())

REUSE_HASHES = {
    'owner.json': '313a1ad0a38891530ec29cd2ceb5aa781d1236056b94ea21fbb47738d32a7bea',
    'unit.log': '52068e4078c5491ab420bbc729e7bb844be55fa42f475f8823df26dfb30be757',
    'sync.json': 'e8f8c60840496de5c3636039a214321ce15b8b1f241a929e812c3f1c899b3e43',
    'controller.py': 'e60a9285bca40716fdad9dcd409026471fadbc771508eccab4483797a4247b71',
}
REUSED_DRIVERS = [
    'spin/test_spin_batch.py', 'spin/test_spin_shadow.py',
    'spin/test_spin_outer_progress.py', 'spin/test_spin_proxy_context.py',
    'mutex/test_mutex_origin_instruction.py', 'execution/test_bench_completion.py',
]


def verify_unit_reuse(unit, sync, commit, evidence):
    require(unit.get('unit_selection') == {
        'fresh': False, 'prior_checks_reused': True,
        'basic': ['basic/test_control_call', 'basic/test_daemon_policy'],
        'python_drivers': ['spin/test_spin_batch_context.py'], 'expected_passes': 3,
        'reused_python_drivers': REUSED_DRIVERS, 'effective_selected_checks': 9,
    }, 'explicit selective unit coverage differs')
    reuse = unit.get('unit_reuse', {})
    require(reuse.get('prior_source_commit') == '6bf690204fdf954ab9076a762000833ec18e6261' and
            reuse.get('current_source_commit') == commit and
            reuse.get('prior_owner_completed') is False and
            reuse.get('prior_error') == "AssertionError('unit')" and
            reuse.get('prior_unit_returncode') == 2 and
            reuse.get('prior_unit_log_sha256') == REUSE_HASHES['unit.log'] and
            reuse.get('reused_python_drivers') == REUSED_DRIVERS and
            reuse.get('reused_python_passes') == 6 and
            reuse.get('same_tracked_path_set') is True and
            reuse.get('compared_tracked_inputs') == 5922 and
            reuse.get('evidence_directory') == 'unit-reuse' and
            reuse.get('retained_sha256') == REUSE_HASHES,
            'unit reuse must retain the exact failed attempt and six passes')
    require(set(evidence) == set(REUSE_HASHES) and
            all(hashlib.sha256(evidence[name]).hexdigest() == expected
                for name, expected in REUSE_HASHES.items()), 'retained unit-reuse input differs')
    prior = json.loads(evidence['owner.json'])
    old_sync = json.loads(evidence['sync.json'])
    require(prior.get('completed') is False and prior.get('error') == "AssertionError('unit')" and
            prior.get('source_commit') == reuse['prior_source_commit'] and
            prior.get('boot_id') == unit['boot_id'] and
            [row['name'] for row in prior['blocks']] == ['kernel-identity', 'unit'] and
            [row.get('returncode') for row in prior['blocks']] == [0, 2] and
            reuse.get('prior_unit_argv') == prior['blocks'][1]['argv'],
            'failed prior unit status must remain explicit')
    old, current = old_sync['tracked_sha256'], sync['tracked_sha256']
    require(old_sync['git_head'] == reuse['prior_source_commit'] and
            old_sync['git_status'] == '' and old_sync['synchronization_completed'] is True and
            sync['git_head'] == commit and len(old) == len(current) == 5922 and
            set(old) == set(current), 'unit reuse source path set differs')
    changed = {name: dict(prior=before, current=current[name])
               for name, before in old.items() if before != current[name]}
    require(set(changed) == {
        'tests/unit/spin/spin_batch_context_fixture.c',
        'bench/results/10.176.26.71/bench/continuation-nano-20261030/README.md',
    } and reuse.get('changed_inputs') == changed,
            'unit reuse permits only the reviewed fixture and failure-record changes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('basic', 'origin', 'rwsem', 'mixed'))
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--basic-campaign', type=Path)
    parser.add_argument('--commit', required=True)
    for name in ('unit', 'sync', 'host-reference'):
        parser.add_argument('--'+name, type=Path, required=True)
        parser.add_argument('--'+name+'-sha256', required=True)
    parser.add_argument('--host-state', type=Path, required=True)
    args = parser.parse_args()
    if args.basic_campaign is None:
        args.basic_campaign = args.campaign
    require(os.geteuid() == 0 and os.uname().release == '7.0.0-38-kdlock1' and
            sys.executable == PYTHON, 'intended guest and pinned Python required')
    require(re.fullmatch('[0-9a-f]{40}', args.commit), 'explicit commit required')
    require(args.campaign.is_absolute() and not args.campaign.is_relative_to(ROOT),
            'external campaign required')
    require(args.basic_campaign.is_absolute() and not args.basic_campaign.is_relative_to(ROOT),
            'external basic campaign required')
    require(args.phase != 'basic' or args.basic_campaign == args.campaign,
            'basic phase must use its own campaign')
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT,
            'normal-kernel boot changed; preserve attempt and review')
    require(not os.environ.get('KERNELRELEASE') and not os.environ.get('KBUILD_OUTPUT'),
            'unexpected kernel build override')
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(ROOT/'bench/spin_cacheline'), str(ROOT/'bench/basic')]
    import bench_runtime as rt
    functional_host = runpy.run_path(str(ROOT/'bench/basic/run.py'))['functional_host']
    idle = runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle']
    idle(Path('/root'), rt.idle)
    out, control = args.campaign/args.phase, args.campaign/(args.phase+'-control')
    require(not out.exists() and not control.exists(), 'preserve existing output')
    control.mkdir(parents=True)
    receipt = dict(completed=False, source_commit=args.commit, phase=args.phase,
                   boot_id=BOOT, performance_accepted=False, timing_started=False,
                   driver_pid=os.getpid(), started=time.time(),
                   basic_campaign=str(args.basic_campaign))

    def save():
        temporary = control/'owner.tmp'
        temporary.write_text(json.dumps(receipt, indent=2)+'\n')
        temporary.replace(control/'owner.json')

    child = None
    save()
    try:
        for name in ('unit', 'sync', 'host-reference'):
            path = getattr(args, name.replace('-', '_'))
            expected = getattr(args, name.replace('-', '_')+'_sha256')
            require(re.fullmatch('[0-9a-f]{64}', expected) and sha(path) == expected,
                    'reviewed input differs: '+name)
        inputs = {'controller.py':Path(__file__), 'unit.json':args.unit, 'sync.json':args.sync,
                  'host-before.json':args.host_state, 'host-reference.json':args.host_reference}
        for name, path in inputs.items():
            shutil.copyfile(path, control/name)
        receipt['inputs'] = {name:sha(control/name) for name in inputs}
        unit, sync = load(args.unit), load(args.sync)
        require(unit.get('completed') is True and unit.get('final_idle') is True and
                unit.get('source_commit') == args.commit and unit.get('boot_id') == BOOT and
                unit.get('input_sha256', {}).get('sync.json') == args.sync_sha256 and
                unit['input_sha256'].get('controller.py') == UNIT_CONTROLLER and
                sha(args.unit.parent/'controller.py') == UNIT_CONTROLLER,
                'same-generation unit/build evidence required')
        require([x.get('name') for x in unit['blocks']] == ['kernel-identity', 'unit', 'build-provider'] and
                all(x.get('returncode') == 0 for x in unit['blocks']), 'unit/build failed')
        reuse_paths = {name: args.unit.parent/'unit-reuse'/name for name in REUSE_HASHES}
        verify_unit_reuse(unit, sync, args.commit,
                          {name: path.read_bytes() for name, path in reuse_paths.items()})
        for name, path in reuse_paths.items():
            retained = 'unit-reuse-' + name
            shutil.copyfile(path, control/retained)
            receipt['inputs'][retained] = sha(control/retained)
            require(receipt['inputs'][retained] == REUSE_HASHES[name], 'copied reuse evidence differs')
        require(sync['git_head'] == args.commit and sync['git_status'] == '' and
                sync['synchronization_completed'] is True and sync['tracked_sha256'],
                'clean frozen source required')

        def verify_sources():
            for name, expected in sync['tracked_sha256'].items():
                relative = Path(name)
                require(not relative.is_absolute() and '..' not in relative.parts and
                        not (ROOT/relative).is_symlink() and sha(ROOT/relative) == expected,
                        'frozen source changed: '+name)

        verify_sources()
        from provider.prepare import production_files
        require(all(sync['tracked_sha256'].get(str(path)) == sha(ROOT/path)
                    for path in production_files(ROOT)), 'untracked/changed provider input')
        original, current = load(args.host_reference), load(args.host_state)
        receipt['host_admission'] = functional_host(original, current,
            datetime.datetime.now(datetime.timezone.utc), SNAPSHOT)
        require(current['snapshot_listed'] is True and current['recovery_snapshot'] == SNAPSHOT,
                'actual recovery snapshot required')
        if args.phase != 'basic':
            basic_result_path = args.basic_campaign/'basic/result.json'
            basic_owner_path = args.basic_campaign/'basic-control/owner.json'
            basic = load(basic_result_path)
            require(basic.get('passed') is True and basic.get('final_idle') is True and
                    basic.get('boot_id') == BOOT and basic.get('timing_started') is False and
                    [row['family'] for row in basic['results']] == ['spin', 'mutex', 'rwlock', 'rwsem'] and
                    all(row['passed'] and row['drained'] and row['jit_completions'] > 0
                        for row in basic['results']), 'four-family basic check required')
            basic_owner = load(basic_owner_path)
            require(basic_owner.get('completed') is True and basic_owner.get('final_idle') is True and
                    basic_owner.get('source_commit') == args.commit and basic_owner.get('boot_id') == BOOT and
                    basic_owner.get('phase') == 'basic' and basic_owner.get('returncode') == 0 and
                    basic_owner.get('result_sha256') == sha(basic_result_path) and
                    basic_owner.get('inputs', {}).get('sync.json') == args.sync_sha256 and
                    basic_owner['inputs'].get('unit.json') == args.unit_sha256 and
                    basic_owner['inputs'].get('controller.py') == receipt['inputs']['controller.py'] and
                    sha(basic_owner_path.parent/'controller.py') == receipt['inputs']['controller.py'],
                    'basic source/result generation differs')
            receipt['basic_dependency'] = {
                'campaign': str(args.basic_campaign),
                'owner_path': str(basic_owner_path), 'owner_sha256': sha(basic_owner_path),
                'result_path': str(basic_result_path), 'result_sha256': sha(basic_result_path),
            }
        common = ['--kernel-source', KDIR, '--kernel-baseline', BUNDLE, '--kernel-variant', 'kdlock1']
        if args.phase == 'basic':
            command = [PYTHON, 'bench/basic/run.py', *common, '--output', str(out),
                '--host-reference', str(args.host_reference),
                '--host-reference-sha256', args.host_reference_sha256,
                '--host-state', str(args.host_state), '--snapshot-tag', SNAPSHOT]
        else:
            command = [PYTHON, 'tests/kernel/jit_continuation/run.py', *common, '--output', str(out),
                '--cpus', '0-15', '--warmup-iterations', '10000', '--iterations', '10000',
                '--phase-timeout', '120']
            if args.phase == 'rwsem':
                command += ['--family', 'rwsem']
            else:
                command += ['--family', 'mutex', '--mutex-api', 'public',
                            '--origin-instructions' if args.phase == 'origin' else '--mixed-spin']
        receipt['argv'] = command
        env = dict(os.environ, PATH=str(Path(PYTHON).parent)+':'+os.environ['PATH'],
            PYTHONDONTWRITEBYTECODE='1', KDLOCK_RECOVERY_CONFIRMED='1', KDLOCK_SNAPSHOT_TAG=SNAPSHOT)
        with (control/'run.log').open('xb') as log:
            child = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            receipt.update(pid=child.pid, state='RUNNING')
            save()
            code = child.wait(timeout=1800)
        receipt.update(returncode=code, state='EXITED', finished=time.time())
        save()
        require(code == 0, 'phase failed; retain all outputs')
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT, 'boot changed')
        verify_sources()
        result = load(out/'result.json')
        require(result.get('passed') is True and result.get('drained', result.get('final_idle')) is True,
                'phase result incomplete')
        if args.phase != 'basic':
            require(result['origin_service'] == (args.phase != 'mixed') and
                    result['origin_instructions'] == (args.phase == 'origin'), 'service scope differs')
            phases = result['phases']
            require(len(phases) == (7 if args.phase == 'origin' else 5) and
                    all(x['complete'] for x in phases) and
                    all(x['execution_validated'] for x in phases[1:]), 'phase validation incomplete')
            session = load(out/'session/session.json')
            require(session.get('drained') is True and session.get('retired') ==
                    dict(state=2, modules=0, frames=0, writers=0), 'source/frame retirement incomplete')
        idle(out, rt.idle)
        receipt.update(completed=True, final_idle=True, result_sha256=sha(out/'result.json'))
    except BaseException as error:
        receipt['error'] = repr(error)
        if child is not None:
            # An exited child can leave callers/modules behind. Only explicit
            # result, source retirement and final idle checks establish drain.
            receipt.update(child_returncode=child.poll(), drain_unknown=True)
        raise
    finally:
        save()
    print('COMPLETE continuation-perf-live', args.phase, args.commit, flush=True)

if __name__ == '__main__':
    main()
