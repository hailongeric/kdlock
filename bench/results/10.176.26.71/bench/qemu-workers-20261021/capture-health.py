#!/usr/bin/env python3
"""Validate completed single-session evidence and current drain in the same VM."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import runpy
import re
import sys

ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/qemu-workers-20261021')
OLD = BASE.parent/'pipecap-unlock-20261021'


def read(path):
    return json.loads(path.read_text())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True)
    a = p.parse_args()
    assert re.fullmatch(r'phase-[0-9]+', a.run)
    run = BASE/a.run
    sys.dont_write_bytecode = True
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
    import bench_runtime as rt
    archive = runpy.run_path(str(ROOT/'bench/archive_run.py'))
    archive['idle'](BASE, rt.idle)
    spec = importlib.util.spec_from_file_location('worker_health_control', ROOT/'bench/mutex_api_compare/unlock_control.py')
    control = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(control)
    scheduler = control.load(ROOT/'bench/mutex_api_compare/run.py', 'worker_health_scheduler')
    frozen = scheduler.replay_inputs(control.ORIGINAL, BASE/'unused-health-output')
    harness = scheduler.retained_harness(control.ORIGINAL)
    for item in frozen.values():
        scheduler.verify(item['files'])
    scheduler.verify(harness)
    candidate = control.validate(scheduler, OLD/'inputs-1/inputs.json',
        'daf7f77beda2704d9cc56291f9864489f733c844f6188cd6c8198480539badae')
    transition = read(run/'transition.json')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    modules = sorted(line.split()[0] for line in Path('/proc/modules').read_text().splitlines())
    assert boot == transition['new_boot_id'] and modules == transition['modules'] and len(modules) == 73
    result = read(run/'result.json')
    assert result['passed'] and result['final_idle'] and result['planned'] == result['completed'] == 1
    assert result['phase_single_outer'] and not result['accepted']
    assert read(run/'correctness.json') == read(OLD/'correctness-1/result.json')
    row, = result['records']
    folder = run/'outer'/row['name']
    assert row['name'] == 'timing-pipecap-t05-r0-outer'
    assert read(folder/'session.json') == row and row['execution_status'] == 'OK' and row['drained']
    assert row['retired'] == dict(state=2, modules=0, frames=0, writers=0)
    assert row['actual_lock_cacheline_offset'] == row['lock_addr'] % 64 == 32
    measurement = row['measurement']
    assert measurement['ok'] and len(measurement['workers']) == 5
    assert sum(w['completed'] for w in measurement['workers']) == measurement['completed'] == row['redirected_calls']
    assert all(w['error'] == 0 and w['cpu'] == w['observed_cpu'] and w['completed'] > 0 for w in measurement['workers'])
    assert measurement['collector_cpu'] == measurement['collector_observed_cpu'] == 63 and measurement['collector_error'] == 0
    assert row['published_before'] == row['published_after']
    assert 0 <= row['jit_completions'] <= row['jit_bodies'] <= measurement['completed']
    faults = [line for line in (folder/'kernel.log').read_text().splitlines() if rt.FAULT.search(line)]
    assert not faults
    before = read(run/'host-before.json')
    followup = control.load(ROOT/'bench/mutex_api_compare/recovery_replay.py', 'worker_health_transition')
    comparison = followup.compare_environment(scheduler.same_environment, transition,
        read(control.ORIGINAL/'matrix/host-state.json'), before,
        read(control.ORIGINAL/'matrix/environment.json'), read(run/'environment.json'),
        read(control.ORIGINAL/'matrix/topology.json'), read(run/'topology.json'))
    assert comparison['configuration_matches'] and len(before['qemu'][0]['tasks']) == 67
    archive['idle'](BASE, rt.idle)
    health = dict(idle=True, accepted=False, boot_id=boot, kernel_release=os.uname().release,
        run=a.run, matching_runtime_modules=True, sessions=1, drained=1, operations=measurement['completed'],
        entries=row['jit_bodies'], returns=row['jit_completions'], retired=row['retired'],
        per_session_kernel_faults=faults, original_inputs_unchanged=True,
        provider_sha256=candidate['provider_sha256'], source_sha256=rt.digest(Path(__file__)),
        regressions={p: 'UNRESOLVED_CAUSE' for p in ('c08-t03', 'c08-t04', 'c08-t05', 'pipebytes-t03', 'pipebytes-t05', 'pipecap-t05', 'rcuht-t02')})
    with (BASE/'final-health.json').open('x') as stream:
        json.dump(health, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(health))


if __name__ == '__main__':
    main()
