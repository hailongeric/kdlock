#!/usr/bin/env python3
"""Serial functional smoke for KD spin, public mutex, rwlock and rwsem; no scores."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import kernel_identity
import capture_host

FAMILIES = ('spin', 'mutex', 'rwlock', 'rwsem')
PYTHON = '/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def functional_host(original, host, now, snapshot=None):
    """Permit recorded extra I/O workers only in this unscored functional mode."""
    capture_host.validate(original)
    capture_host.validate(host)
    age = (now - datetime.datetime.fromisoformat(host['captured_utc'])).total_seconds()
    reference_time = datetime.datetime.fromisoformat(original['captured_utc'])
    require(reference_time <= datetime.datetime.fromisoformat(host['captured_utc']),
            'host state predates its selected reference')
    require(0 <= age <= 300 and host['pins_verified'] and host['frequency_verified'] and
            original['pins_verified'] and original['frequency_verified'] and host['snapshot_listed'],
            'fresh verified host placement and recovery snapshot required')
    if snapshot is not None:
        require(host['recovery_snapshot'] == snapshot, 'selected recovery snapshot differs')
    for key in ('cpufreq', 'no_turbo', 'numa', 'recovery_snapshot', 'host_boot_id', 'monitor_path'):
        require(host[key] == original[key], 'host configuration differs: ' + key)
    require(len(host['qemu']) == len(original['qemu']) == 1, 'same single QEMU required')
    old, new = original['qemu'][0], host['qemu'][0]
    require(all(old[k] == new[k] for k in ('pid', 'start_ticks', 'args')),
            'QEMU identity/configuration differs')
    old_tasks = {t['tid']: t for t in old['tasks']}
    new_tasks = {t['tid']: t for t in new['tasks']}
    require(len(old_tasks) == len(old['tasks']) and len(new_tasks) == len(new['tasks']),
            'duplicate host task identity')
    require(all(new_tasks.get(tid) == row for tid, row in old_tasks.items()),
            'original QEMU task identity/placement changed')
    extra = [row for tid, row in new_tasks.items() if tid not in old_tasks]
    require(all(row['comm'] == 'worker' and row['affinity'] == [63] for row in extra),
            'unexpected additional host task or placement')

    require(capture_host.memory_bindings(old) == capture_host.memory_bindings(new),
            'host memory binding changed')
    return dict(mode='FUNCTIONAL_ONLY', performance_accepted=False,
                timing_gate='NOT_APPLICABLE', original_threads=len(old_tasks),
                observed_threads=len(new_tasks), additional_workers=extra,
                memory_bindings=capture_host.memory_bindings(new))


def plan(out, families, kernel_source=None, kernel_baseline=None, kernel_variant='kdlock1'):
    selected = argparse.Namespace(kernel_source=kernel_source, kernel_baseline=kernel_baseline,
                                  kernel_variant=kernel_variant)
    kernel_identity.benchmark_profile(selected)
    common = ['--functional', '--backends', 'kdlock', '--repeats', '1',
              '--iterations', '100000', '--collector-cpu', '63',
              '--kernel-variant', kernel_variant,
              '--kernel-source', str(selected.kernel_source),
              '--kernel-baseline', str(selected.kernel_baseline)]
    rows = []
    for family in families:
        # Use one NUMA-local cohort for the returned-body smoke. Larger mixed
        # cohorts may legitimately stay local and belong in the timed catalog.
        workers = 16
        if family in ('spin', 'mutex'):
            runner = 'bench/tclock_compare/' + ('run.py' if family == 'spin' else 'run_mutex.py')
            arguments = ['--cpus', '0-15', '--workload', 'cacheline', '--cachelines', '1']
            if family == 'mutex':
                arguments += ['--mutex-api', 'public']
        else:
            runner = 'bench/rwlock_compare/run.py'
            arguments = ['--cpus', *map(str, range(workers)), '--lock-kind', family,
                         '--workloads', 'cacheline', '--cachelines', '16' if family == 'rwsem' else '1',
                         '--write-percent', '100' if family == 'rwsem' else '20',
                         '--post-work-rounds', '4', '--delegate', 'on', '--require-jit']
        rows.append(dict(family=family, output=str(out / family),
                         argv=[sys.executable, str(ROOT / runner), *common,
                               '--threads', str(workers), *arguments,
                               '--output', str(out / family)]))
    return rows


def session_result(folder, family):
    specs = load(folder / 'plan.json')
    require(len(specs) == 1 and specs[0]['functional'], 'one functional session required')
    path = folder / specs[0]['name'] / 'session.json'
    row = load(path)
    require(row['execution_status'] == 'OK' and row['drained'] and
            row['measurement']['complete'] and row['measurement']['data_ok'],
            'session correctness or drain failed')
    entries, completed = row['jit_bodies'], row['jit_completions']
    require(type(entries) is int and type(completed) is int and entries >= completed > 0,
            'returned JIT body required; local/partial execution is not delegated support')
    return dict(family=family, passed=True, drained=True, execution='RETURNED_JIT',
                jit_entries=entries, jit_completions=completed,
                operations=row['measurement']['completed'],
                receipt=str(path), receipt_sha256=sha(path), performance_accepted=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--host-state', type=Path)
    parser.add_argument('--host-reference', type=Path, required=True)
    parser.add_argument('--host-reference-sha256', required=True)
    parser.add_argument('--snapshot-tag', default=os.environ.get('KDLOCK_SNAPSHOT_TAG'))
    kernel_identity.benchmark_arguments(parser)
    parser.add_argument('--families', nargs='+', choices=FAMILIES, default=list(FAMILIES))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    require(len(args.families) == len(set(args.families)), 'duplicate family')
    require(bool(re.fullmatch('[0-9a-f]{64}', args.host_reference_sha256)),
            'explicit SHA256 for the selected host reference required')
    require(args.snapshot_tag, 'select --snapshot-tag or KDLOCK_SNAPSHOT_TAG')
    environment_tag = os.environ.get('KDLOCK_SNAPSHOT_TAG')
    require(not environment_tag or environment_tag == args.snapshot_tag,
            'snapshot argument and environment disagree')
    out = args.output.resolve()
    kernel_identity.benchmark_profile(args)
    tasks = plan(out, args.families, args.kernel_source, args.kernel_baseline, args.kernel_variant)
    if args.dry_run:
        print(json.dumps(tasks, indent=2))
        return
    require(ROOT == Path('/root/host_fs/kdlock') and os.geteuid() == 0,
            'verified Linux 7 development guest required')
    kernel_identity.benchmark_profile(args, release=os.uname().release)
    require(sys.executable == PYTHON and
            shutil.which('python3') == sys.executable, 'pinned Python required')
    require(os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1', 'confirmed recovery snapshot required')
    require(args.host_state, 'fresh --host-state required')
    reference_bytes = args.host_reference.read_bytes()
    require(hashlib.sha256(reference_bytes).hexdigest() == args.host_reference_sha256,
            'selected host reference SHA256 differs')
    state_bytes = args.host_state.read_bytes()
    original, current_host = json.loads(reference_bytes), json.loads(state_bytes)
    require(not out.exists() and not out.is_relative_to(ROOT), 'new external output required')
    import bench_runtime as rt
    archive_idle = runpy.run_path(str(ROOT / 'bench/archive_run.py'))['idle']
    with open('/run/lock/kdlock-basic.lock', 'a') as slot:
        fcntl.flock(slot, fcntl.LOCK_EX | fcntl.LOCK_NB)
        archive_idle(Path('/root'), rt.idle)
        identity = kernel_identity.check(args.kernel_source, args.kernel_baseline, variant=args.kernel_variant)
        require(identity.get('ok') is True and identity.get('schema') == 2 and
                identity.get('runtime_policy_verified') is True,
                'verified Linux 7 kernel bundle and live runtime policy required')
        topology = rt.capture_topology(list(range(64)))
        require(topology['online_cpus'] == list(range(64)) and
                topology['role_nodes'] == [0] * 32 + [1] * 32, '64-CPU guest topology required')
        host = functional_host(original, current_host, datetime.datetime.now(datetime.timezone.utc),
                               args.snapshot_tag)
        os.environ['KDLOCK_SNAPSHOT_TAG'] = args.snapshot_tag
        out.mkdir(parents=True)
        (out / 'host-state.json').write_bytes(state_bytes)
        (out / 'reference-host.json').write_bytes(reference_bytes)
        save(out / 'kernel-identity.json', identity)
        save(out / 'plan.json', tasks)
        save(out / 'functional-admission.json', host)
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        result = dict(state='RUNNING', passed=False, final_idle=False, mode='FUNCTIONAL_ONLY',
                      performance_accepted=False, timing_started=False, boot_id=boot,
                      topology=topology, kernel_identity=identity,
                      host_reference_sha256=args.host_reference_sha256,
                      snapshot_tag=args.snapshot_tag, results=[], commands=[])
        controls = [Path(__file__), Path(__file__).with_name('test_run.py'),
                    Path(capture_host.__file__), Path(kernel_identity.__file__)]
        hashes = {str(p): sha(p) for p in controls}
        save(out / 'control-sha256.json', hashes)
        for path in controls:
            shutil.copyfile(path, out / path.name)

        def execute(name, argv, limit):
            record = dict(name=name, argv=list(map(str, argv)), state='STARTING')
            result['commands'].append(record)
            save(out / 'result.json', result)
            with (out / (name + '.log')).open('wb') as log:
                child = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
                record.update(state='RUNNING', pid=child.pid)
                save(out / 'result.json', result)
                # A deadline reports uncertainty; it never kills a live worker.
                try:
                    code = child.wait(timeout=limit)
                except BaseException:
                    record['state'] = 'UNKNOWN_DRAIN'
                    raise
            record.update(state='EXITED', returncode=code)
            save(out / 'result.json', result)
            require(code == 0, name + ' failed; preserve its logs and receipts')
            archive_idle(Path('/root'), rt.idle)
            require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot,
                    'guest boot changed')
            require(all(sha(Path(p)) == h for p, h in hashes.items()), 'smoke controls changed')

        try:
            execute('dependencies', [sys.executable, '-m', 'pip', 'check'], 60)
            execute('basic', ['make', '-C', str(ROOT / 'tests/unit'), 'run', 'PY_TESTS='], 180)
            execute('runner-checks', [sys.executable, ROOT / 'bench/basic/test_run.py'], 120)
            for task in tasks:
                print('FUNCTIONAL', task['family'], flush=True)
                execute(task['family'], task['argv'], 1800)
                result['results'].append(session_result(Path(task['output']), task['family']))
                save(out / 'result.json', result)
            result.update(state='COMPLETE', passed=True, final_idle=True)
        except BaseException as error:
            result.update(state='FAILED', error=repr(error))
            raise
        finally:
            save(out / 'result.json', result)
        print(json.dumps(result['results'], indent=2))


if __name__ == '__main__':
    main()
