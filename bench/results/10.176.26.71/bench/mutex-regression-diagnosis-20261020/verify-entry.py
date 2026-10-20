#!/usr/bin/env python3
"""Verify completed entry-candidate checks and four live probes in the idle VM."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import time

ROOT = Path('/root/host_fs/kdlock')
RETIRED = dict(state=2, modules=0, writers=0, frames=0)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path)
    parser.add_argument('--live', choices=('live-1', 'live-2'), default='live-1',
                        help='live-2 additionally requires the preserved load failure and guard receipts')
    args = parser.parse_args()
    base = args.base.resolve()
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    assert not (base/'health.json').exists() and not base.is_relative_to(ROOT)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
    import bench_runtime as rt
    runpy.run_path(str(ROOT/'bench/archive_run.py'))['idle'](base, rt.idle)
    for path in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
        try:
            name = path.read_text().strip()
        except (FileNotFoundError, ProcessLookupError):
            continue
        assert name not in ('ke_worker', 'kg_worker', 'ks_worker'), str(path)
    checks, live = base/'checks-1', base/args.live
    manifest = read(checks/'committed-source.json')
    assert read(live/'committed-source.json') == manifest
    count = 0
    previous = None
    if args.live == 'live-2':
        failure = read(base/'failed-live1-health.json')
        first = read(base/'live-1/tasks.json')
        guard = read(base/'allocator-refresh/result.json')
        assert failure['passed'] is False and failure['completed_live_probes'] == 0
        assert failure['kernel_allocation_failure']['bytes'] == 7592
        assert failure['original_result'] == read(base/'live-1/mutex-local/result.json')
        assert first['state'] == 'FAILED' and first['failed_task'] == 'mutex-local'
        assert len(first['tasks']) == 1 and first['tasks'][0]['exit_code'] == 1
        assert guard['passed'] and guard['idle'] and guard['source_unchanged']
        assert guard['failed_attempt_unchanged']
        assert guard['source_commit'] == failure['source_commit'] == manifest['commit']
        assert guard['boot_id'] == failure['boot_id']
        assert guard['failure_health_sha256'] == sha(base/'failed-live1-health.json')
        failed_hashes = base/'failure-diagnostics/failed-live1-file-sha256.json'
        assert sha(failed_hashes) == failure['failure_inventory_sha256']
        for relative, expected in read(failed_hashes).items():
            assert sha(base/relative) == expected, relative
        for relative, expected in read(base/'allocator-refresh/source-sha256.json').items():
            assert manifest['files'][relative] == expected
            assert sha(base/'allocator-refresh/source'/relative) == expected
        for relative, expected in read(base/'allocator-refresh/binary-sha256.json').items():
            assert sha(base/'allocator-refresh'/relative) == expected
        previous = dict(state='PREPARATION_FAILED', passed=False,
                        failure_health_sha256=sha(base/'failed-live1-health.json'),
                        unchanged_failed_files=len(read(failed_hashes)),
                        allocator_refresh=guard)
    for relative, expected in manifest['files'].items():
        assert sha(ROOT/relative) == expected, relative
        count += 1
    result = read(checks/'result.json')
    assert result['passed'] and result['final_idle'] and result['source_unchanged']
    assert result['unit_basic'] == 2 and len(result['unit_drivers']) == 6
    assert not result['full_suite'] and not result['runner_tests']
    assert result['source_revision'] == manifest['commit']
    assert all(r['exit_code'] == 0 for r in result['commands'])
    assert sha(checks/'run-checks.py') == result['script_sha256']
    for relative, expected in read(checks/'source-sha256.json').items():
        assert manifest['files'][relative] == expected == sha(checks/'source'/relative)
        count += 1
    tasks = read(live/'tasks.json')
    assert tasks['state'] == 'COMPLETE' and tasks['passed'] and tasks['final_idle']
    assert tasks['source_commit'] == manifest['commit']
    assert [t['name'] for t in tasks['tasks']] == [
        'mutex-local', 'mutex-outer', 'mutex-public', 'owner-ack']
    assert sha(live/'run-tasks.py') == tasks['script_sha256']
    rows, faults = [], []
    for task in tasks['tasks']:
        name, folder = task['name'], Path(task['output'])
        assert folder == live/name and task['state'] == 'FINISHED' and task['exit_code'] == 0
        child = read(folder/'result.json')
        assert child['passed'] and child['drained']
        sources = read(folder/('sources.json' if name == 'owner-ack' else 'source-sha256.json'))
        assert len(sources) == task['committed_source_files']
        for relative, expected in sources.items():
            assert manifest['files'][relative] == expected == sha(folder/'source'/relative)
            count += 1
        if name == 'owner-ack':
            identity = read(folder/'identity.json')
            assert sha(folder/'kdlock_km.ko') == identity['module_sha256']
            assert identity['cpus'] == [0, 32, 33]
            assert child['orders'] == ['B-A', 'A-B'] and child['acks'] == 4
            assert child['deferred_frees'] == 2 and child['jit_bodies'] == 0
            assert (child['registry_stress_workers'], child['registry_stress_iterations'],
                    child['registry_stress_deferred_frees']) == (3, 4096, 3)
            count += 1
        else:
            for relative, expected in read(folder/'binary-sha256.json').items():
                path = Path(relative)
                assert sha(path if path.is_absolute() else folder/path) == expected
                count += 1
        log = folder/('session/kernel.log' if name in ('mutex-outer', 'mutex-public')
                      else 'kernel.log')
        text = log.read_text()
        for line in text.splitlines():
            if rt.FAULT.search(line):
                faults.append(dict(task=name, line=line))
        assert 'kd_source retire: result=0 state=2 modules=0 frames=0 writers=0' in text
        assert 'kd kernel module exit' in text and 'active_tasks=0' in text
        assert 'kd_exec invariant_failures=0' in text
        row = dict(name=name, passed=True, drained=True)
        if name in ('mutex-outer', 'mutex-public'):
            session = read(folder/'session/session.json')
            assert session['execution_status'] == 'OK' and session['drained']
            assert session['retired'] == RETIRED and session['accepted']
            phases = session['phases']
            assert [p['name'] for p in phases] == [
                'cold-warmup', 'cold-delegated', 'hot-escape', 'post-ban']
            for index, phase in enumerate(phases):
                assert phase['complete'] and not any(phase['returncodes'])
                assert len(phase['workers']) == 16 and phase['iterations'] == 100000
                for cpu, worker in enumerate(phase['workers']):
                    assert worker['worker'] == worker['cpu'] == cpu
                    assert worker['completed'] == worker['iterations'] == 100000
                    assert worker['errors'] == 0 and worker['reserved'] == [0, 0]
                before, after = phase['before'], phase['after']
                assert before['prefix'] == before['suffix'] == index*1600000
                assert after['prefix'] == after['suffix'] == (index+1)*1600000
                assert all(v['failures'] == v['active'] == 0 and v['idle'] == 1
                           for v in (before, after))
                delta = phase['jit_delta']
                if index < 2:
                    assert delta['bench_jit_bodies'] == delta['bench_jit_completions']
                    assert delta['native_escape_count'] == 0
                    if index == 1:
                        assert delta['bench_jit_completions'] > 0
                elif index == 2:
                    assert delta == dict(bench_jit_bodies=1, bench_jit_completions=0,
                                         native_escape_count=1)
                else:
                    assert not any(delta.values())
            assert 'kd_native stats: started=1 completed=1 unlocks=1' in text
            row.update(retired=session['retired'],
                       phases=[dict(name=p['name'], counters=p['jit_delta']) for p in phases])
        elif name == 'mutex-local':
            assert child['source_retirement'] == RETIRED and child['final_idle']
            assert child['probe']['operations'] == 160000 and child['probe']['workers'] == 8
            assert child['probe']['objects'] == 2048 and child['probe']['lock_size'] == 32
            assert child['jit_bodies'] == 0
            row.update(retired=child['source_retirement'], probe=child['probe'])
        else:
            assert read(folder/'retire.log') == RETIRED
            row.update(retired=RETIRED, probe=child)
        rows.append(row)
    assert not faults, faults
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert boot == tasks['boot_id']
    shutil.copyfile(Path(__file__), base/'verify-entry.py')
    health = dict(idle=True, boot_id=boot, checked_unix=time.time(),
                  verifier_sha256=sha(Path(__file__)),
                  source_commit=manifest['commit'], source_binary_hashes_checked=count,
                  checks=result, tasks=rows, per_session_kernel_faults=faults)
    if previous is not None:
        assert previous['allocator_refresh']['boot_id'] == boot
        health.update(live_attempt=args.live, previous_attempt=previous)
    (base/'health.json').write_text(json.dumps(health, indent=2, sort_keys=True)+'\n')
    print(json.dumps(health, sort_keys=True))


if __name__ == '__main__':
    main()
