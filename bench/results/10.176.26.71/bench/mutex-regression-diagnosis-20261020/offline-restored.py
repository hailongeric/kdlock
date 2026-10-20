#!/usr/bin/env python3
"""Audit restored-entry evidence as inert archives on the source host."""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import re
import socket
import sys
from types import SimpleNamespace


COMMIT = 'a768361f91259f35a11743350662b5d862e35292'
HELPER_SHA = '05b87daa59dd00c658b042f8e6bf30ee60d5c811956a5a132053d9708ae4ebf6'
ENTRY_SHA = '0d201fc6fbb0514e1cefdea2237e35ff2b9dc67432db53592224552fd269ace3'
STAGE = 'bench/results/10.176.26.71/bench/mutex-regression-diagnosis-20261020/'
RETIRED = dict(state=2, modules=0, writers=0, frames=0)
DRIVERS = ['mutex/test_mutex_resources.py', 'mutex/test_mutex_api.py',
           'mutex/test_mutex_outer_api.py', 'mutex/test_mutex_wait_clobber.py',
           'execution/test_native_after_outer.py', 'admission/test_clobber_entry.py']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    assert socket.gethostname() == '380G10' and not args.report.exists()
    sys.dont_write_bytecode = True
    helper = args.repo / (
        'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/offline-review.py')
    import hashlib
    assert hashlib.sha256(helper.read_bytes()).hexdigest() == HELPER_SHA
    spec = importlib.util.spec_from_file_location('inert_archive_reader', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    a = module.Audit(SimpleNamespace(**vars(args)))
    groups, links = a.load_archives()
    sources, binaries = a.manifests()
    manifest = a.jread('checks-1/committed-source.json')
    live_manifest = a.jread('live-2/committed-source.json')
    health = a.jread('health.json')
    checks = a.jread('checks-1/result.json')
    tasks = a.jread('live-2/tasks.json')
    plan = a.jread('live-2/task-plan.json')
    a.check(manifest == live_manifest and manifest['commit'] == COMMIT
            == health['source_commit'] == checks['source_revision']
            == tasks['source_commit'] == plan['source_commit'], 'revision_binding')
    names = a.names(COMMIT)
    for path, expected in manifest['files'].items():
        a.check(path in names and module.sha(a.git_bytes(COMMIT, path)) == expected,
                'source_git_hash', path)
    a.check(manifest['files']['kernel_module/lock/mutex_calls.inc'] == ENTRY_SHA,
            'restored_entry_hash')
    for row in sources:
        if row['prepared']:
            continue
        for path, expected in a.jread(row['path']).items():
            a.check(manifest['files'].get(path) == expected, 'snapshot_git_binding',
                    [row['path'], path])
    for target, source in [('checks-1/run-checks.py', 'check-entry-candidate.py'),
                           ('live-2/run-tasks.py', 'run-entry-tasks.py')]:
        a.check(a.files[target] == module.sha(a.git_bytes(COMMIT, STAGE + source)),
                'runner_git_binding', target)
    a.check(checks['passed'] and checks['final_idle'] and checks['source_unchanged']
            and checks['unit_basic'] == 2 and checks['unit_drivers'] == DRIVERS
            and checks['full_suite'] is False and checks['runner_tests'] == []
            and all(c['exit_code'] == 0 for c in checks['commands'])
            and [c['name'] for c in checks['commands']] ==
            ['dependencies', 'provider', 'daemon', 'unit'], 'basic_affected_pass')
    a.check(checks['committed_manifest_sha256'] == a.files['checks-1/committed-source.json']
            and checks['script_sha256'] == a.files['checks-1/run-checks.py']
            and checks['commands'] == a.jread('checks-1/commands.json'), 'check_receipts')
    a.check(tasks['state'] == 'COMPLETE' and tasks['passed'] and tasks['final_idle']
            and [t['name'] for t in tasks['tasks']] ==
            ['mutex-local', 'mutex-outer', 'mutex-public', 'owner-ack']
            and all(t['state'] == 'FINISHED' and t['exit_code'] == 0 for t in tasks['tasks'])
            and tasks['script_sha256'] == a.files['live-2/run-tasks.py'], 'four_task_pass')
    # The archived candidate plan is data only: preserve every task argument.
    previous = json.loads(a.git_bytes(
        '7062887b8aa6e059a429716464e4262f744ea522',
        'bench/results/10.176.26.71/tests/mutex-entry-inline-20261020/live-1/task-plan.json'))
    a.check(plan['tasks'] == previous['tasks'],
            'unchanged_candidate_task_arguments')
    a.check(health['idle'] and health['boot_id'] == tasks['boot_id'] == a.archive['boot_id']
            == 'b65f0205-c8f9-4385-8b13-039cbce243a6'
            and health['checks'] == checks and not health['per_session_kernel_faults']
            and health['verifier_sha256'] == a.files['verify-entry.py'], 'health_binding')
    for target, source in [
            ('verify-entry.py', 'verify-entry.py'),
            ('failure-diagnostics/preserve-restored-failure.py', 'preserve-restored-failure.py'),
            ('allocator-refresh/refresh-restored-allocator.py', 'refresh-restored-allocator.py')]:
        a.check(a.files[target] == module.hashfile(args.repo/STAGE/source),
                'maintained_verifier_bytes', target)
    failure = a.jread('failed-live1-health.json')
    first = a.jread('live-1/tasks.json')
    guard = a.jread('allocator-refresh/result.json')
    a.check(failure['passed'] is False and failure['completed_live_probes'] == 0
            and first['state'] == 'FAILED' and first['failed_task'] == 'mutex-local'
            and len(first['tasks']) == 1 and first['tasks'][0]['exit_code'] == 1
            and failure['original_result'] == a.jread('live-1/mutex-local/result.json')
            and failure['kernel_allocation_failure']['bytes'] == 7592
            and 'Could not allocate 7592 bytes percpu data' in
            a.contents['live-1/mutex-local/kernel.log'].decode(), 'preserved_preparation_failure')
    for path, expected in a.jread('failure-diagnostics/failed-live1-file-sha256.json').items():
        a.check(a.files.get(path) == expected, 'failed_attempt_unchanged', path)
    a.check(guard['passed'] and guard['idle'] and guard['source_unchanged']
            and guard['failed_attempt_unchanged'] and guard['source_commit'] == COMMIT
            and guard['commands'] == [dict(name=n, exit_code=0) for n in ('build', 'load', 'unload')]
            and guard['failure_health_sha256'] == a.files['failed-live1-health.json']
            and health['live_attempt'] == 'live-2'
            and health['previous_attempt']['allocator_refresh'] == guard
            and health['previous_attempt']['passed'] is False, 'allocator_preparation_and_retry')
    rows, prepared = [], []
    for index, task in enumerate(tasks['tasks']):
        name, root = task['name'], 'live-2/' + task['name'] + '/'
        child = a.jread(root + 'result.json')
        a.check(child['passed'] and child['drained'], 'child_pass_drain', name)
        source_map = root + ('sources.json' if name == 'owner-ack' else 'source-sha256.json')
        frozen = a.jread(source_map)
        a.check(task['committed_source_files'] == len(frozen), 'task_source_count', name)
        for path, expected in frozen.items():
            a.check(manifest['files'].get(path) == a.files.get(root+'source/'+path) == expected,
                    'child_snapshot_binding', [name, path])
        log_path = root + ('session/kernel.log' if name in ('mutex-outer', 'mutex-public')
                           else 'kernel.log')
        log = a.contents[log_path].decode()
        a.check(all(s in log for s in (
            'kd_source retire: result=0 state=2 modules=0 frames=0 writers=0',
            'kd kernel module exit', 'active_tasks=0', 'kd_exec invariant_failures=0')),
            'kernel_retirement', name)
        row = dict(name=name, passed=True, drained=True, retired=RETIRED)
        if name == 'owner-ack':
            identity = a.jread(root+'identity.json')
            a.check(a.files[root+'kdlock_km.ko'] == identity['module_sha256']
                    and identity['cpus'] == [0, 32, 33], 'ack_provider_binding')
            a.check(child['orders'] == ['B-A', 'A-B'] and child['acks'] == 4
                    and child['deferred_frees'] == 2 and child['jit_bodies'] == 0
                    and child['jit'] is False and child['registry_stress_workers'] == 3
                    and child['registry_stress_iterations'] == 4096
                    and child['registry_stress_deferred_frees'] == 3, 'exact_ack_oracle')
            a.check(a.jread(root+'retire.log') == RETIRED, 'ack_retirement')
            row['probe'] = child
        elif name == 'mutex-local':
            p = child['probe']
            a.check((p['operations'], p['workers'], p['objects'], p['lock_size'],
                     p['lock_align']) == (160000, 8, 2048, 32, 8)
                    and p['interruptible'] == p['killable'] == 'EINTR'
                    and all(p[k] == 'PASS' for k in (
                        'address_reuse', 'api_helpers', 'containing_layout', 'drain',
                        'io', 'nested_sleep', 'no_aux', 'no_destroy', 'ring_cancel', 'ring_handoff'))
                    and child['jit_bodies'] == 0 and child['final_idle']
                    and child['source_retirement'] == RETIRED, 'local_api_oracle')
            found = re.search(r'KD_LOCAL_PROBE PASS ([^\n]+)', log)
            fields = {k: int(v) if v.isdecimal() else v for k, v in
                      re.findall(r'(\w+)=([^\s]+)', found[1])} if found else {}
            a.check(fields == p, 'local_kernel_receipt')
            row['probe'] = p
        else:
            original = root+'source/'
            changes = a.reconstruct(
                original, a.contents[original+'bench/spin_cacheline/provider/observation.patch'])
            pm = a.jread(root+'prepared-source-sha256.json')
            classes = Counter()
            for path, expected in pm.items():
                if path in ('include/kd_bench.h', 'kernel_module/kd_bench.c'):
                    contents = a.contents[original+'bench/spin_cacheline/provider/'+Path(path).name]
                    kind = 'overlay'
                elif path in changes:
                    contents, kind = changes[path], 'patched'
                else:
                    contents, kind = a.contents[original+path], 'unchanged'
                a.check(module.sha(contents) == expected, 'prepared_reconstruction', [name, path])
                classes[kind] += 1
            a.check(set(changes) <= set(pm), 'prepared_patch_targets', name)
            prepared.append(dict(name=name, classes=dict(classes)))
            session = a.jread(root+'session/session.json')
            a.check(session['execution_status'] == 'OK' and session['accepted']
                    and session['drained'] and session['retired'] == RETIRED
                    and child['phases'] == session['phases'], 'session_accept_drain', name)
            phases = session['phases']
            a.check([p['name'] for p in phases] ==
                    ['cold-warmup', 'cold-delegated', 'hot-escape', 'post-ban'], 'phase_order', name)
            for i, p in enumerate(phases):
                prefix = root+'session/'+p['name']
                a.check(p['complete'] and p['iterations'] == 100000 and len(p['workers']) == 16
                        and not any(p['returncodes']), 'phase_complete', [name, i])
                for cpu, w in enumerate(p['workers']):
                    a.check(w == a.jread(prefix+'-worker-'+str(cpu)+'.json')
                            and w['worker'] == w['cpu'] == cpu
                            and w['iterations'] == w['completed'] == 100000
                            and w['errors'] == 0 and w['reserved'] == [0, 0],
                            'worker_oracle', [name, i, cpu])
                before, after = p['before'], p['after']
                a.check(before == a.jread(prefix+'-before.counts.json')
                        and after == a.jread(prefix+'-after.counts.json')
                        and before['prefix'] == before['suffix'] == i*1600000
                        and after['prefix'] == after['suffix'] == (i+1)*1600000
                        and all(v['failures'] == v['active'] == 0 and v['idle'] == 1
                                for v in (before, after)), 'business_counts', [name, i])
                delta = p['jit_delta']
                a.check(delta == {k: p['counters_after'][k]-v
                                  for k, v in p['counters_before'].items()},
                        'counter_arithmetic', [name, i])
                if i < 2:
                    okay = (delta['bench_jit_bodies'] == delta['bench_jit_completions']
                            and delta['native_escape_count'] == 0
                            and (i == 0 or delta['bench_jit_completions'] > 0))
                elif i == 2:
                    okay = delta == dict(bench_jit_bodies=1, bench_jit_completions=0,
                                         native_escape_count=1)
                else:
                    okay = not any(delta.values())
                a.check(okay, 'phase_execution', [name, i])
            a.check('kd_native stats: started=1 completed=1 unlocks=1' in log,
                    'native_completion_ack', name)
            row['phases'] = [dict(name=p['name'], counters=p['jit_delta']) for p in phases]
        a.check(row == health['tasks'][index], 'health_task_binding', name)
        rows.append(row)
    report = dict(consistent=not a.issues, issues=a.issues, checks=sum(a.counts.values()),
                  check_counts=dict(a.counts), source_commit=COMMIT,
                  members=len(a.members), files=len(a.files), symlinks=len(links),
                  groups=groups, sources=sources, binary_entries=len(binaries),
                  prepared=prepared, tasks=rows,
                  archives_manifest_sha256=module.hashfile(args.raw/'archives.json'),
                  helper_sha256=HELPER_SHA, verifier_sha256=module.hashfile(Path(__file__)))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    print(json.dumps(dict(consistent=report['consistent'], checks=report['checks'],
                          issues=report['issues'], report=str(args.report))))
    return bool(a.issues)


if __name__ == '__main__':
    raise SystemExit(main())
