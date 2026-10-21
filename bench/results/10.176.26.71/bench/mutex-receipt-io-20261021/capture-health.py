#!/usr/bin/env python3
"""Guest-only final checks after the bounded pre-warmup diagnostic drains."""
import json
import os
from pathlib import Path
import runpy
import sys
import time

ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-receipt-io-20261021')
RUN = BASE/'probe-1'
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
    sys.path.insert(0, str(ROOT/'bench/mutex_api_compare'))
    import unlock_control as control
    import prewarmup_control as prewarmup
    scheduler = control.load(ROOT/'bench/mutex_api_compare/run.py', 'prewarmup_health_scheduler')
    frozen = scheduler.replay_inputs(control.ORIGINAL, BASE/'unused-health-output')
    harness = scheduler.retained_harness(control.ORIGINAL)
    for item in frozen.values():
        scheduler.verify(item['files'])
    scheduler.verify(harness)
    candidate = control.validate(scheduler, OLD/'inputs-1/inputs.json',
        'daf7f77beda2704d9cc56291f9864489f733c844f6188cd6c8198480539badae')
    transition = read(RUN/'transition.json')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    modules = sorted(line.split()[0] for line in Path('/proc/modules').read_text().splitlines())
    assert boot == transition['new_boot_id'] and modules == transition['modules'] and len(modules) == 73
    result = read(RUN/'result.json')
    assert result['diagnostic_completed'] and result['final_idle'] and result['planned'] == result['completed'] == 1
    assert result['setup_boundary_probe'] and result['prewarmup_boundary_probe'] and not result['accepted']
    assert read(RUN/'correctness.json') == read(OLD/'correctness-1/result.json')
    row, = result['records']
    folder = RUN/'outer'/row['name']
    assert read(folder/'session.json') == row and row['execution_status'] == 'OK' and row['drained']
    assert row['retired'] == dict(state=2, modules=0, frames=0, writers=0)
    assert row['actual_lock_cacheline_offset'] == row['lock_addr'] % 64 == 32
    assert row['measurement_skipped'] and 'measurement' not in row
    assert not any(k in row for k in ('whole_throughput_ops_s', 'peak_throughput_ops_s'))
    assert not (folder/'measure.json').exists()
    assert read(folder/'check-before.json')['check'] and read(folder/'check-after-boundary.json')['check']
    followup = control.load(ROOT/'bench/mutex_api_compare/recovery_replay.py', 'prewarmup_health_transition')
    def compare(host, environment, topology):
        return followup.compare_environment(scheduler.same_environment, transition,
            read(control.ORIGINAL/'matrix/host-state.json'), host,
            read(control.ORIGINAL/'matrix/environment.json'), environment,
            read(control.ORIGINAL/'matrix/topology.json'), topology)
    assert compare(read(RUN/'host-before.json'), read(RUN/'environment.json'), read(RUN/'topology.json'))['configuration_matches']
    gates = []
    for n, boundary in enumerate(row['boundaries'], 1):
        policy = prewarmup.capture_policy(True, n, boundary['stage'])
        assert boundary['before'] == boundary['after'] and boundary['before']['physical_idle']
        assert boundary['before']['publication']['source'] == dict(state=0, modules=1, frames=0, writers=0)
        counters = boundary['before']['counters']
        assert counters['bench_jit_bodies'] == counters['bench_jit_completions'] and counters['address_guard_count'] == 0
        try:
            compare(boundary['host'], boundary['environment'], boundary['topology'])
            gate = True
        except ValueError as error:
            gate = False
            assert str(error) == boundary['gate']['error']
        assert gate == boundary['gate']['passed']
        gates.append(gate)
        if policy == 'immediate':
            observation, = boundary['observations']
            assert observation['trigger']['kind'] == 'immediate'
            assert observation['trigger_freshness'] is None
    assert result['passed'] == (len(gates) == 2 and all(gates))
    state = row['prewarmup_control']
    assert state['measurement_commands'] == 0
    if gates[0]:
        assert len(gates) == 2 and state['warmup_commands'] == 1 and not state['warmup_skipped']
        warm = row['boundary_warmup']
        assert warm == read(folder/'warmup.json') and warm['ok'] and len(warm['workers']) == 5
        assert sum(w['completed'] for w in warm['workers']) == warm['completed']
        assert [w['cpu'] for w in warm['workers']] == list(range(5))
        assert all(w['error'] == 0 and w['cpu'] == w['observed_cpu'] and w['completed'] >= 48000 and
                   w['finished_ns'] >= warm['started_ns']+1000000000 for w in warm['workers'])
        assert warm['collector_cpu'] == warm['collector_observed_cpu'] == 63 and warm['collector_error'] == 0
        assert prewarmup.validate_transition(row['boundaries'][0]['after'], row['boundaries'][1]['before'], warm) == row['warmup_counter_delta']
        assert (row['boundaries'][0]['finished_ns'] <= state['command_began_ns'] <= warm['started_ns'] <=
                max(w['finished_ns'] for w in warm['workers']) <= state['original_reply_saved_ns'] <=
                state['reply_validation_finished_ns'] <= state['reply_saved_ns'] <=
                row['boundaries'][1]['times']['before_began_ns'] <= row['boundaries'][1]['began_ns'])
    else:
        assert len(gates) == 1 and state['warmup_commands'] == 0 and state['warmup_skipped']
        assert 'boundary_warmup' not in row and not (folder/'warmup.json').exists()
        warm = dict(completed=0)
    faults = [line for line in (folder/'kernel.log').read_text().splitlines() if rt.FAULT.search(line)]
    assert not faults
    checks = read(BASE/'checks-1/result.json')
    assert checks['passed'] and checks['source_unchanged'] and checks['final_idle']
    assert [(c['name'], c['exit_code']) for c in checks['commands']] == [
        ('basic', 0), ('receipt-trace', 0), ('phase-accounting', 0), ('boundary-trigger', 0), ('boundary-protocol', 0), ('prewarmup-control', 0), ('recovery-gate', 0)]
    archive['idle'](BASE, rt.idle)
    health = dict(idle=True, accepted=False, boot_id=boot, kernel_release=os.uname().release,
        run='probe-1', p95='DEFERRED_NOT_THROUGHPUT_GATE', matching_runtime_modules=True, modules=modules, sessions=1, drained=1,
        boundary_gates=gates, diagnostic_completed=True, measurement_sent=False,
        warmup_operations=warm['completed'], warmup_counter_delta=row.get('warmup_counter_delta'),
        states_unchanged=True, retired=row['retired'], per_session_kernel_faults=faults,
        original_inputs_unchanged=True, provider_sha256=candidate['provider_sha256'], captured_ns=time.time_ns(),
        regressions={p: 'UNRESOLVED_CAUSE' for p in ('c08-t03', 'c08-t04', 'c08-t05', 'pipebytes-t03', 'pipebytes-t05', 'pipecap-t05', 'rcuht-t02')})
    with (BASE/'final-health.json').open('x') as stream:
        json.dump(health, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(health))


if __name__ == '__main__':
    main()
