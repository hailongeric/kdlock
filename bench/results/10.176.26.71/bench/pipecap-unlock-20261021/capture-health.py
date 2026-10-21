#!/usr/bin/env python3
"""Retain completion and failed-admission evidence without another test run."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import sys

ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/pipecap-unlock-20261021')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
    import bench_runtime as runtime
    archive = runpy.run_path(str(ROOT/'bench/archive_run.py'))
    archive['idle'](BASE, runtime.idle)
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    transition = read(BASE.parent/'mutex-recovery-followup-20261021/transition-1/result.json')
    assert boot == transition['new_boot_id'] == '88449cfc-cea9-4647-a294-bc601e372146'
    modules = sorted(line.split()[0] for line in Path('/proc/modules').read_text().splitlines())
    assert modules == transition['modules'] and len(modules) == 73
    spec = importlib.util.spec_from_file_location('health_control', ROOT/'bench/mutex_api_compare/unlock_control.py')
    control = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(control)
    # This is an evidence check, not a collector process. Importing both the
    # maintained idle helper and frozen collector would correctly trip the
    # collector's origin guard, so verify its files without loading runners.
    scheduler = control.load(ROOT/'bench/mutex_api_compare/run.py', 'health_scheduler')
    frozen = scheduler.replay_inputs(control.ORIGINAL, BASE/'unused-health-output')
    harness = scheduler.retained_harness(control.ORIGINAL)
    for item in frozen.values():
        scheduler.verify(item['files'])
    scheduler.verify(harness)
    inputs = BASE/'inputs-1/inputs.json'
    candidate = control.validate(scheduler, inputs,
        'daf7f77beda2704d9cc56291f9864489f733c844f6188cd6c8198480539badae')
    for filename, digest in scheduler.REPLAY_ENVIRONMENT_SHA256.items():
        assert sha(control.ORIGINAL/'matrix'/filename) == digest
    checks = read(BASE/'checks-1/result.json')
    assert checks['passed'] and checks['source_unchanged'] and checks['final_idle']
    for name, digest in read(BASE/'checks-1/source-sha256.json').items():
        assert sha(BASE/'checks-1/source'/name) == digest
    task = read(BASE/'task-2/result.json')
    assert task['passed'] and task['drained'] and task['acks'] == 4
    assert sha(BASE/'task-1/kdlock_km.ko') == sha(BASE/'task-2/kdlock_km.ko')
    assert 'Could not allocate 7592 bytes percpu data' in (BASE/'task-1/kernel.log').read_text()
    assert not (BASE/'task-1/result.json').exists()
    refresh = read(BASE/'allocator-refresh-1/result.json')
    assert refresh['passed'] and refresh['idle'] and refresh['failed_attempt_unchanged']
    for name, digest in read(BASE/'allocator-refresh-1/failed-attempt-sha256.json').items():
        assert sha(BASE/'task-1'/name) == digest
    result = read(BASE/'correctness-1/result.json')
    assert result['passed'] and result['final_idle'] and result['completed'] == result['planned'] == 4
    assert result['inputs_sha256'] == sha(inputs) and not result['accepted']
    records, faults = [], []
    for row in result['records']:
        arm = 'outer' if row['comparison_arm'] == 'original-outer' else 'general'
        folder = BASE/'correctness-1'/arm/row['name']
        assert read(folder/'session.json') == row
        work = row['correctness_work']
        assert row['execution_status'] == 'OK' and row['drained'] and work['ok']
        assert row['retired'] == dict(state=2, modules=0, frames=0, writers=0)
        assert row['actual_lock_cacheline_offset'] == row['lock_addr'] % 64 == 32
        assert 0 <= row['jit_completions'] <= row['jit_bodies'] <= work['completed']
        assert (row['jit_completions'] == 0) if row['threads'] == 1 else (row['jit_completions'] > 0)
        assert len(work['workers']) == row['threads'] and work['collector_cpu'] == work['collector_observed_cpu'] == 63
        assert work['collector_error'] == 0 and sum(w['completed'] for w in work['workers']) == work['completed']
        assert all(w['error'] == 0 and w['cpu'] == w['observed_cpu'] and
                   w['completed'] >= row['warmup'] for w in work['workers'])
        assert not (folder/'measure.json').exists() and 'measurement' not in row
        faults += [dict(name=row['name'], line=line) for line in (folder/'kernel.log').read_text().splitlines()
                   if runtime.FAULT.search(line)]
        records.append(dict(name=row['name'], completed=work['completed'], entries=row['jit_bodies'],
                            returns=row['jit_completions'], retired=row['retired'], drained=row['drained']))
    faults += [dict(name='task-2', line=line) for line in (BASE/'task-2/kernel.log').read_text().splitlines()
               if runtime.FAULT.search(line)]
    assert not faults
    timing_log = (BASE/'timing-1-command.log').read_text()
    assert 'strict original QEMU thread identities or placement differ' in timing_log and 'START timing-' not in timing_log
    assert not (BASE/'timing-1/plan.json').exists() and not (BASE/'timing-1/result.json').exists()
    host = BASE/'host-evidence'
    before, after = (read(host/(name+'.log')) for name in ('host-before-timing-1', 'host-after-timing-1'))
    original_tasks = read(control.ORIGINAL/'matrix/host-state.json')['qemu'][0]['tasks']
    for snapshot in (before, after):
        assert len(snapshot['qemu'][0]['tasks']) == 68
        assert all(t in snapshot['qemu'][0]['tasks'] for t in original_tasks)
        assert snapshot['pins_verified'] and snapshot['snapshot_listed']
    assert before['qemu'][0]['tasks'] == after['qemu'][0]['tasks']
    supervisor = read(host/'timing-1-supervisor.json')
    assert supervisor['guest_exit_code'] == 1 and supervisor['endpoint_captured']
    archive['idle'](BASE, runtime.idle)
    health = dict(idle=True, accepted=False, boot_id=boot, kernel_release=os.uname().release,
        matching_runtime_modules=True, sessions=4, drained=4, records=records,
        completed_operations=sum(r['completed'] for r in records), jit_returns=sum(r['returns'] for r in records),
        per_session_kernel_faults=faults, task_retry_binary_sha256=sha(BASE/'task-2/kdlock_km.ko'),
        task_probe=task, failed_task_attempt='task-1: pre-init reserved-percpu allocation failure',
        derivative_manifest_sha256=sha(inputs), provider_sha256=candidate['provider_sha256'],
        derivative_sha256=candidate['derivative_workload_sha256'],
        verified_original_files={p: h for item in frozen.values() for p, h in item['files'].items()},
        verified_retained_harness=harness, timing_sessions=0, timing_status='BLOCKED_HOST_GATE',
        host_before_count=68, host_after_count=68, script_sha256=sha(Path(__file__)),
        regressions={p: 'UNRESOLVED_CAUSE' for p in ('c08-t03', 'c08-t04', 'c08-t05',
                     'pipebytes-t03', 'pipebytes-t05', 'pipecap-t05', 'rcuht-t02')})
    with (BASE/'final-health.json').open('x') as stream:
        json.dump(health, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({k: v for k, v in health.items() if not k.startswith('verified_')}))


if __name__ == '__main__':
    main()
