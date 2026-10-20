#!/usr/bin/env python3
"""Audit a completed shared-lock archive and report fresh, separate comparisons.

Run only on the source host. Imports are limited to two hash-pinned, maintained
inert archive/arithmetic readers. No archived program or workload is executed.
"""
import argparse
from collections import Counter
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import socket
import sys
from types import SimpleNamespace


SOURCE = 'f48b90e42e1538a5204d215b573a238ebd95f391'
RESTORED = 'a768361f91259f35a11743350662b5d862e35292'
BASE = 'bench/results/10.176.26.71/bench/'
STAGE = BASE+'shared-lock-followup-20261020/'
HELPERS = {
    'archive': (BASE+'mutex32-native-tclock-20261020/offline-review.py',
                '05b87daa59dd00c658b042f8e6bf30ee60d5c811956a5a132053d9708ae4ebf6'),
    'arithmetic': (BASE+'rwsem-optimization-20261018/independent-replay.py',
                   '425e5bf0b637e9a20dede0ecda32ef085cdd9ae15d59f1c011c506785a4ee1cc'),
}
REFERENCE = {
    'host-state.json': '478e0dfa20602093ff849ae2c195bc5248101d9190d70fe63dd269e41633ba0a',
    'environment.json': '7c19cf8989a5cf56d78edec014f991354ec0ba929f8bd5d1f495fd5ae942bbf5',
    'topology.json': 'a1375dd2e696fdc379fe2d3bddbd77247638d6a82946aa9ff14da45384d41816',
}
RETIRED = dict(state=2, modules=0, writers=0, frames=0)


def load(repo, name):
    relative, expected = HELPERS[name]
    path = repo/relative
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    spec = importlib.util.spec_from_file_location('inert_'+name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def memory_configuration(qemu):
    rows = []
    for line in qemu['numa_maps'].splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1].startswith('bind:'):
            values = dict(field.split('=', 1) for field in fields[2:] if '=' in field)
            rows.append((fields[0], fields[1], int(values['kernelpagesize_kB'])))
    assert rows
    return rows


def environments(a, health):
    original_host = a.jread('reference-environment/host-state.json')
    original_env = a.jread('reference-environment/environment.json')
    original_topology = a.jread('reference-environment/topology.json')
    checks = {}
    for endpoint in ('before', 'after'):
        host = a.jread('host-'+endpoint+'.json')
        env = a.jread('preflight/environment.json' if endpoint == 'before' else 'environment-after.json')
        topology = a.jread('preflight/topology.json' if endpoint == 'before' else 'topology-after.json')
        start = len(a.issues)
        for key in ('cpufreq', 'numa', 'recovery_snapshot'):
            a.check(host[key] == original_host[key], 'host_configuration', [endpoint, key])
        a.check(len(host['qemu']) == len(original_host['qemu']) == 1,
                'single_qemu', endpoint)
        original, current = original_host['qemu'][0], host['qemu'][0]
        for key in ('pid', 'args'):
            a.check(current[key] == original[key], 'qemu_identity', [endpoint, key])
        pins = lambda q: sorted((t['comm'], t['affinity']) for t in q['tasks'])
        a.check(pins(current) == pins(original), 'qemu_thread_placement', endpoint)
        a.check(memory_configuration(current) == memory_configuration(original),
                'host_memory_binding', endpoint)
        for key in ('boot_id', 'cmdline', 'preemption', 'packages', 'python',
                    'snapshot_tag', 'collector_topology'):
            a.check(env[key] == original_env[key], 'guest_environment', [endpoint, key])
        a.check(topology == original_topology, 'guest_topology', endpoint)
        passed = len(a.issues) == start
        a.check(passed == health['host_endpoints'][endpoint]['passed'],
                'health_environment_result', endpoint)
        checks[endpoint] = dict(passed=passed, qemu_threads=len(current['tasks']),
                                original_threads=len(original['tasks']),
                                captured_utc=host['captured_utc'])
    return checks


def comparisons(run):
    points = []
    keys = sorted({(g['workload'], g['cachelines'], g['write_percent'], g['threads'])
                   for g in run['groups']})
    controls = ('native', 'tclock') if 'tclock' in run['per_arm'] else ('native',)
    for key in keys:
        groups = {arm: [g for g in run['groups'] if
                        (g['workload'], g['cachelines'], g['write_percent'], g['threads']) == key
                        and g['arm'] == arm] for arm in ('kdlock', *controls)}
        for control in controls:
            row = dict(workload=key[0], cachelines=key[1], write_percent=key[2], threads=key[3],
                       comparator=control, status='INCOMPLETE', reason='', groups={
                           arm: [dict(jit_status=g['jit_status'], rounds=g['valid_rounds'],
                                      samples=g['samples']) for g in groups[arm]]
                           for arm in ('kdlock', control)})
            selected = {}
            for arm in ('kdlock', control):
                gs = groups[arm]
                if len(gs) != 1 or gs[0]['valid_rounds'] != 3:
                    row['reason'] = 'SPLIT_EXECUTION_CLASSES_OR_MISSING_REPETITIONS'
                    break
                if gs[0]['jit_status'] not in ('PASS', 'NO_JIT', 'NATIVE'):
                    row['reason'] = 'PARTIAL_OR_UNMEASURED_JIT'
                    break
                selected[arm] = gs[0]
            if not row['reason']:
                kd, other = selected['kdlock'], selected[control]
                row.update(
                    kd_class=kd['jit_status'],
                    whole_ratio=kd['whole_median_ops_s']/other['whole_median_ops_s'],
                    peak_ratio=kd['best_peak_ops_s']/other['best_peak_ops_s'],
                    separated_loss_5pct=kd['whole_max_ops_s'] < .95*other['whole_min_ops_s'])
                row['status'] = 'PASS' if min(row['whole_ratio'], row['peak_ratio']) >= 1 else 'FAIL'
                for arm, value in (('kd', kd), ('control', other)):
                    for metric in ('whole_min_ops_s', 'whole_median_ops_s', 'whole_max_ops_s',
                                   'peak_min_ops_s', 'peak_median_ops_s', 'peak_max_ops_s',
                                   'worker_cpu_ns_per_op_median'):
                        row[arm+'_'+metric] = value[metric]
                    row[arm+'_whole_spread_pct'] = (
                        value['whole_max_ops_s']-value['whole_min_ops_s'])*100/value['whole_min_ops_s']
            points.append(row)
    return points


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--raw', type=Path, required=True, help='one family archive directory')
    parser.add_argument('--report', type=Path, required=True, help='new report directory')
    args = parser.parse_args()
    assert socket.gethostname() == '380G10' and not args.report.exists()
    sys.dont_write_bytecode = True
    helper, arithmetic = load(args.repo, 'archive'), load(args.repo, 'arithmetic')
    a = helper.Audit(SimpleNamespace(**vars(args)))
    archive_groups, links = a.load_archives()
    source_maps, binaries = a.manifests()
    tasks, plan, manifest, health = (a.jread(n+'.json') for n in
                                     ('tasks', 'task-plan', 'committed-source', 'health'))
    phase = tasks['phase']
    assert phase in ('rwsem', 'rwlock')
    group, count = ('rwsem-grid', 756) if phase == 'rwsem' else ('rwlock-reference', 270)
    root = group+'/'
    a.check(manifest['commit'] == tasks['source_commit'] == plan['source_commit'] ==
            health['source_commit'] == SOURCE, 'source_identity')
    a.check(len(manifest['files']) == plan['source_files'] == 497, 'source_count')
    for path, digest in manifest['files'].items():
        a.check(helper.sha(a.git_bytes(SOURCE, path)) == digest, 'committed_source_hash', path)
        a.check(helper.sha(a.git_bytes(RESTORED, path)) == digest, 'validated_source_hash', path)
    a.check(tasks['state'] == 'COMPLETE' and tasks['passed'] and tasks['final_idle']
            and len(tasks['tasks']) == 1, 'completed_supervisor')
    task = tasks['tasks'][0]
    a.check(task['name'] == group and task['state'] == 'FINISHED' and task['exit_code'] == 0
            and task['completed_sessions'] == count, 'completed_child')
    a.check(a.files['run-tasks.py'] == tasks['script_sha256'] == plan['supervisor_sha256']
            == helper.sha(a.git_bytes(SOURCE, plan['supervisor'])), 'supervisor_binding')
    a.check(a.files['committed-source.json'] == plan['source_manifest_sha256'],
            'source_manifest_binding')
    a.check(a.jread('preflight/task-plan.json') == plan and
            a.jread('preflight/committed-source.json') == manifest and
            a.jread('preflight/host-state.json') == a.jread('host-before.json'), 'preflight_inputs')
    pf = a.jread('preflight/result.json')
    a.check(pf['passed'] and pf['idle'] and pf['source_unchanged'] and
            pf['source_files'] == 497 and pf['source_commit'] == SOURCE and
            pf['planned_sessions'] == count and pf['phase'] == phase and
            pf['script_sha256'] == a.files['preflight/preflight.py'], 'preflight_pass')
    for path, digest in a.jread(root+'source-sha256.json').items():
        a.check(manifest['files'].get(path) == digest, 'snapshot_source_binding', path)
    original = root+'source/'
    prepared = a.jread(root+'build/provider/manifest.json')
    changes = a.reconstruct(original, a.contents[original+'bench/spin_cacheline/provider/observation.patch'])
    categories = Counter()
    a.check(prepared['complete'], 'prepared_complete')
    for path, digest in prepared['prepared'].items():
        if path in ('include/kd_bench.h', 'kernel_module/kd_bench.c'):
            data = a.contents[original+'bench/spin_cacheline/provider/'+Path(path).name]
            category = 'overlay'
        elif path in changes:
            data, category = changes[path], 'patched'
        else:
            data, category = a.contents[original+path], 'unchanged'
        a.check(helper.sha(data) == digest == a.files.get(root+'build/provider/'+path),
                'prepared_reconstruction', path)
        categories[category] += 1
    a.check(set(changes) <= set(prepared['prepared']), 'all_patch_targets_retained')
    a.check(health['source_hashes_checked'] == len(manifest['files']) +
            len(a.jread(root+'source-sha256.json')) + len(prepared['prepared']) and
            health['binary_hashes_checked'] == len(binaries), 'health_input_counts')
    for category, prefix in [('production', original),
                             ('observation', original+'bench/spin_cacheline/provider/')]:
        for path, digest in prepared[category].items():
            a.check(a.files.get(prefix+path) == digest, 'prepared_'+category, path)
    records, child_plan = a.jread(root+'records.json'), a.jread(root+'plan.json')
    dry = a.jread('preflight/planned-sessions.json')
    a.check(len(records) == len(child_plan) == len(dry) == count, 'exact_session_count')
    retirements, fault_lines = [], []
    for row, spec, dry_spec in zip(records, child_plan, dry):
        name = row['name']
        a.check(all(spec.get(k) == v for k, v in dry_spec.items()), 'preflight_plan_binding', name)
        saved = a.jread(root+name+'/session.json')
        a.check(all(row.get(k) == v for k, v in saved.items()) and set(row)-set(saved) <=
                {'whole_ops_s', 'read_ops_s', 'write_ops_s', 'peak_ops_s'}, 'session_binding', name)
        raw = a.jread(root+name+'/measure.json')
        a.check({k: v for k, v in row['measurement'].items() if k != 'peak'} ==
                {k: v for k, v in raw.items() if k != 'peak'}, 'raw_measurement_binding', name)
        if row['arm'] == 'kdlock':
            a.check(row['retired'] == RETIRED, 'exact_retirement', name)
            retirements.append(dict(name=name, retired=row['retired']))
        for line in a.contents[root+name+'/kernel.log'].decode().splitlines():
            if helper.FAULT.search(line):
                fault_lines.append(dict(name=name, line=line))
    a.check(not fault_lines and health['per_session_kernel_faults'] == fault_lines, 'kernel_logs')
    a.check(retirements == health['exact_retirements'] and
            len(retirements) == (378 if phase == 'rwsem' else 90), 'retirement_receipts')
    a.check(health['sessions'] == health['functionally_valid'] == health['drained'] == count and
            health['idle'] and health['boot_id'] == tasks['boot_id'] == pf['boot_id'] ==
            a.archive['boot_id'] == 'b65f0205-c8f9-4385-8b13-039cbce243a6', 'health_outcome_binding')
    a.check(health['verifier_sha256'] == a.files['verify-comparison.py'] ==
            helper.hashfile(args.repo/STAGE/'verify-comparison.py'), 'verifier_binding')
    for name, digest in REFERENCE.items():
        a.check(a.files['reference-environment/'+name] == digest ==
                health['reference_environment_sha256'][name], 'original_environment_hash', name)
    preservation_issues = list(a.issues)
    endpoints = environments(a, health)
    env_issues = a.issues[len(preservation_issues):]
    matrix_archive = next(g['file'] for g in a.archive['groups']
                          if a.prefix+group in g['roots'])
    math_audit = arithmetic.Audit()
    # This selector specifies only the old matrix geometry, never its source/run.
    selector = 'followup-grid' if phase == 'rwsem' else 'final-reference'
    run = arithmetic.replay_run(selector, args.raw/matrix_archive, math_audit)
    run.update(run_id='shared-lock-followup-20261020/'+Path(a.archive['guest_base']).name,
               family=phase, source_commit=SOURCE, geometry_selector=selector)
    for name, digest in run['input_sha256'].items():
        a.check(digest == a.files[root+name], 'arithmetic_input_binding', name)
    a.check(run['totals'] == dict(completed=health['totals']['operations'],
                                **{k: health['totals'][k] for k in
                                   ('reads', 'writes', 'jit_entries', 'jit_completions')}),
            'health_totals_binding')
    a.check(run['jit_session_counts'] == health['execution_classes'], 'health_class_binding')
    points = comparisons(run)
    run['comparisons'] = points
    run['comparison_counts'] = dict(Counter(p['comparator']+':'+p['status'] for p in points))
    run['separated_losses_5pct'] = [p for p in points if p.get('separated_loss_5pct')]
    run['class_gaps'] = [p for p in points if p['status'] == 'INCOMPLETE']
    output = dict(
        consistent=not a.issues and not math_audit.failures,
        evidence_integrity_passed=not preservation_issues and not math_audit.failures
            and not a.issues[len(preservation_issues)+len(env_issues):],
        checks=dict(a.counts), issues=a.issues,
        arithmetic_checks=dict(math_audit.counts), arithmetic_failures=math_audit.failures,
        archive_groups=archive_groups, source_maps=source_maps, binary_entries=len(binaries),
        symlinks=len(links), files=len(a.files), prepared_reconstruction=dict(categories),
        archives_manifest_sha256=helper.hashfile(args.raw/'archives.json'),
        regular_file_hash_map_sha256=helper.canonical(a.files),
        host_endpoints=endpoints, run=run, overall_acceptance='OPEN',
        script_sha256=helper.hashfile(Path(__file__)), helpers=HELPERS,
        limits=[
            'Fresh within-family comparison only; no historical source/environment pooling.',
            'Every ratio needs three repetitions per arm in a single execution class.',
            'PASS is the runner label for at least one completed KD body; NO_JIT remains separate.',
            'PARTIAL_JIT or unmeasured KD evidence has no score; TCLock delegation is UNMEASURED.',
            'Whole-interval JIT counters do not establish the execution mix inside the selected peak window.',
            'Throughput parity requires median whole and best peak ratios at least one.',
            'Three-repetition spreads/ranges are observed variance, not confidence intervals.',
            'Any failed endpoint check remains failed; runtime interference and p95 latency are unmeasured.',
            'The seven separate public-mutex regressions remain unresolved.'])
    args.report.mkdir(parents=True)
    (args.report/'offline-review.json').write_text(json.dumps(output, indent=2, sort_keys=True)+'\n')
    fields = list(dict.fromkeys(k for p in points for k in p if k != 'groups'))
    with (args.report/'comparisons.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fields, extrasaction='ignore', lineterminator='\n')
        writer.writeheader()
        writer.writerows(points)
    print(json.dumps(dict(
        consistent=output['consistent'], evidence_integrity_passed=output['evidence_integrity_passed'],
        checks=sum(a.counts.values())+sum(math_audit.counts.values()),
        issues=Counter(i['check'] for i in a.issues), arithmetic_failures=len(math_audit.failures),
        run_id=run['run_id'], valid_sessions=run['valid_sessions'], totals=run['totals'],
        comparisons=run['comparison_counts'], class_gaps=len(run['class_gaps']),
        separated_losses_5pct=len(run['separated_losses_5pct']),
        archives_manifest_sha256=output['archives_manifest_sha256']), sort_keys=True))


if __name__ == '__main__':
    main()
