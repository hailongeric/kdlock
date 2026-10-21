#!/usr/bin/env python3
"""Read completed paired evidence and verify final drain; no new workload."""
import importlib.util
import json
import os
from pathlib import Path
import runpy
import sys

ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/pipecap-unlock-followup-20261021')
OLD = BASE.parent/'pipecap-unlock-20261021'


def read(path):
    return json.loads(path.read_text())


def main():
    sys.dont_write_bytecode = True
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
    import bench_runtime as rt
    archive = runpy.run_path(str(ROOT/'bench/archive_run.py'))
    archive['idle'](BASE, rt.idle)
    spec = importlib.util.spec_from_file_location('health_control', ROOT/'bench/mutex_api_compare/unlock_control.py')
    control = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(control)
    scheduler = control.load(ROOT/'bench/mutex_api_compare/run.py', 'health_scheduler')
    frozen = scheduler.replay_inputs(control.ORIGINAL, BASE/'unused-health-output')
    harness = scheduler.retained_harness(control.ORIGINAL)
    for item in frozen.values():
        scheduler.verify(item['files'])
    scheduler.verify(harness)
    candidate = control.validate(scheduler, OLD/'inputs-1/inputs.json',
        'daf7f77beda2704d9cc56291f9864489f733c844f6188cd6c8198480539badae')
    transition = read(BASE/'timing-1/transition.json')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    modules = sorted(line.split()[0] for line in Path('/proc/modules').read_text().splitlines())
    assert boot == transition['new_boot_id'] and modules == transition['modules'] and len(modules) == 73
    result = read(BASE/'timing-1/result.json')
    assert result['passed'] and result['final_idle'] and result['planned'] == result['completed'] == 6
    assert not result['accepted'] and read(BASE/'timing-1/correctness.json') == read(OLD/'correctness-1/result.json')
    order = [(0, 'outer'), (0, 'general'), (1, 'general'), (1, 'outer'), (2, 'outer'), (2, 'general')]
    faults, records = [], []
    for row, (repeat, arm) in zip(result['records'], order):
        assert row['name'] == f'timing-pipecap-t05-r{repeat}-{arm}'
        folder = BASE/'timing-1'/arm/row['name']
        assert read(folder/'session.json') == row and row['execution_status'] == 'OK' and row['drained']
        assert row['retired'] == dict(state=2, modules=0, frames=0, writers=0)
        assert row['actual_lock_cacheline_offset'] == row['lock_addr'] % 64 == 32
        m = row['measurement']
        assert m['ok'] and len(m['workers']) == 5 and sum(w['completed'] for w in m['workers']) == m['completed']
        assert all(w['error'] == 0 and w['cpu'] == w['observed_cpu'] and w['completed'] > 0 for w in m['workers'])
        assert m['collector_cpu'] == m['collector_observed_cpu'] == 63 and m['collector_error'] == 0
        assert row['redirected_calls'] == m['completed'] and row['published_before'] == row['published_after']
        assert 0 <= row['jit_completions'] <= row['jit_bodies'] <= m['completed']
        faults += [dict(name=row['name'], line=line) for line in (folder/'kernel.log').read_text().splitlines() if rt.FAULT.search(line)]
        records.append(dict(name=row['name'], operations=m['completed'], entries=row['jit_bodies'], returns=row['jit_completions'], retired=row['retired']))
    assert not faults
    before = read(BASE/'timing-1/host-before.json')
    after = read(BASE/'host-evidence/host-after-timing-1.json')
    assert len(before['qemu'][0]['tasks']) == 67 and len(after['qemu'][0]['tasks']) == 120
    followup = control.load(ROOT/'bench/mutex_api_compare/recovery_replay.py', 'health_transition')
    args = [scheduler.same_environment, transition, read(control.ORIGINAL/'matrix/host-state.json'),
            before, read(control.ORIGINAL/'matrix/environment.json'), read(BASE/'timing-1/environment.json'),
            read(control.ORIGINAL/'matrix/topology.json'), read(BASE/'timing-1/topology.json')]
    assert followup.compare_environment(*args)['configuration_matches']
    args[3] = after
    try:
        followup.compare_environment(*args)
    except ValueError as error:
        endpoint_error = str(error)
        assert endpoint_error == 'strict original QEMU thread identities or placement differ'
    else:
        raise AssertionError('expected endpoint rejection missing')
    archive['idle'](BASE, rt.idle)
    health = dict(idle=True, accepted=False, boot_id=boot, kernel_release=os.uname().release,
        matching_runtime_modules=True, sessions=6, drained=6, records=records,
        completed_operations=sum(r['operations'] for r in records), entries=sum(r['entries'] for r in records),
        returns=sum(r['returns'] for r in records), per_session_kernel_faults=faults,
        host_preflight_passed=True, host_endpoint_passed=False, host_endpoint_error=endpoint_error,
        host_before_count=67, host_after_count=120, original_inputs_unchanged=True,
        derivative_manifest_sha256=rt.digest(OLD/'inputs-1/inputs.json'),
        provider_sha256=candidate['provider_sha256'], source_sha256=rt.digest(Path(__file__)),
        regressions={p: 'UNRESOLVED_CAUSE' for p in ('c08-t03', 'c08-t04', 'c08-t05', 'pipebytes-t03', 'pipebytes-t05', 'pipecap-t05', 'rcuht-t02')})
    with (BASE/'final-health.json').open('x') as stream:
        json.dump(health, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(health))


if __name__ == '__main__':
    main()
