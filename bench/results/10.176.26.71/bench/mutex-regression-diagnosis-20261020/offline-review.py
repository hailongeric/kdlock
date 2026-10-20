#!/usr/bin/env python3
"""Audit observed reproduction and pinned original archives as inert data."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import posixpath
import socket
from statistics import median
import sys
import tarfile
from types import SimpleNamespace

HELPER = 'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/offline-review.py'
HELPER_SHA = '05b87daa59dd00c658b042f8e6bf30ee60d5c811956a5a132053d9708ae4ebf6'
ORIGINAL_SHA = '7b7dad099d06b2c8964d9e1831b9e02e7f0bba0e209420982a5904972330c3c4'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--raw-parent', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    output = args.report/'offline-review.json'
    assert not output.exists()
    sys.dont_write_bytecode = True
    helper_path = args.repo/HELPER
    assert hashlib.sha256(helper_path.read_bytes()).hexdigest() == HELPER_SHA
    spec = importlib.util.spec_from_file_location('maintained_inert_reader', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    original_raw = args.raw_parent/'mutex-public-20261020-r2'
    assert helper.hashfile(original_raw/'archives.json') == ORIGINAL_SHA
    original_manifest = json.loads((original_raw/'archives.json').read_text())
    original_inventory = json.loads((original_raw/'input-inventory.json').read_text())
    assert helper.hashfile(original_raw/'input-inventory.json') == original_manifest['input_inventory_sha256']

    class JointAudit(helper.Audit):
        def retained_target(self, target):
            # Only the current archive and the pinned original archive may
            # satisfy a link. Resolve path components in memory, including
            # workspace -> replay view -> original bundle chains.
            roots = {self.guest_base.rstrip('/'): self.inventory,
                     original_manifest['guest_base']: original_inventory}
            seen = set()
            for _ in range(32):
                target = posixpath.normpath(target)
                if target in seen:
                    return False
                seen.add(target)
                root = next((r for r in roots if target == r or target.startswith(r+'/')), None)
                if root is None:
                    return False
                relative = target[len(root):].lstrip('/')
                if not relative:
                    return True
                if not helper.safe_relative(relative):
                    return False
                parts = relative.split('/')
                inventory = roots[root]
                for length in range(1, len(parts)+1):
                    name = '/'.join(parts[:length])
                    item = inventory.get(name)
                    if item is None:
                        return False
                    if item.get('link') is not None:
                        link = item['link']
                        target = (link if link.startswith('/') else
                                  posixpath.join(root, posixpath.dirname(name), link))
                        if length < len(parts):
                            target = posixpath.join(target, *parts[length:])
                        break
                else:
                    return relative in inventory
            return False

        def check(self, value, label, detail=None):
            if label == 'symlink_target_retained':
                value = self.retained_target(detail['target'])
            return super().check(value, label, detail)

    original = JointAudit(SimpleNamespace(repo=args.repo, raw=original_raw, report=args.report))
    replay = JointAudit(SimpleNamespace(repo=args.repo,
        raw=args.raw_parent/'mutex-public-20261020-observed-1', report=args.report))
    audits = {'original': original, 'observed': replay}
    archive_details = {}
    for key, audit in audits.items():
        groups, links = audit.load_archives()
        archive_details[key] = dict(groups=groups, symlinks=len(links),
            members=len(audit.members), manifest_sha256=helper.hashfile(audit.raw/'archives.json'))
    replay.windows = []
    health = replay.jread('health.json')
    provenance = replay.jread('replay-provenance.json')
    replay.equal('original_manifest_binding', replay.files['original-archives.json'], ORIGINAL_SHA)
    replay.expect('final_health', health['idle'] is True and health['accepted'] ==
        health['sessions'] == health['drained'] == 120 and not health['per_session_kernel_faults'])
    replay.equal('same_boot', [a.archive['boot_id'] for a in audits.values()], [health['boot_id']]*2)
    for path, field in [('frozen-inputs.json', 'frozen_inputs_manifest_sha256'),
                        ('harness-inputs.json', 'harness_manifest_sha256')]:
        replay.equal('pinned_original_manifest', original.files[path], provenance[field], path)
    replay.equal('replayed_frozen_manifest', replay.files['frozen-inputs.json'], original.files['frozen-inputs.json'])
    replay.equal('scheduler_git_binding', replay.files['replay-scheduler.py'],
        helper.sha(replay.git_bytes('bc72912', 'bench/mutex_api_compare/run.py')))
    replay.equal('scheduler_provenance', replay.files['replay-scheduler.py'], provenance['scheduler_sha256'])
    checked = {p: h for b in original.jread('frozen-inputs.json').values() for p, h in b['files'].items()}
    harness = {original.guest_base+'harness/'+p.removeprefix('/root/host_fs/kdlock/'): h
               for p, h in original.jread('harness-inputs.json').items()}
    replay.equal('health_exact_original_set', health['verified_original_files'], checked)
    replay.equal('health_exact_harness_set', health['verified_retained_harness'], harness)
    replay.equal('health_input_counts', [len(checked), len(harness)], [4088, 336])
    replay.equal('retained_collector_provenance', provenance['retained_collector_files'], harness)
    for path, digest in {**checked, **harness}.items():
        replay.expect('input_within_original', path.startswith(original.guest_base), path)
        replay.equal('original_retained_input_hash', original.files.get(path.removeprefix(original.guest_base)), digest, path)
    original_host = original.jread('matrix/host-state.json')
    hosts = {name: replay.jread(path) for name, path in (
        ('before', 'host-state.json'), ('after', 'host-observation/host-after.json'),
        ('final', 'host-observation/host-final.json'))}
    pins = lambda h: sorted((t['comm'], t['affinity']) for t in h['qemu'][0]['tasks'])
    for name, host in hosts.items():
        for key in ('cpufreq', 'numa', 'recovery_snapshot'):
            replay.equal('host_configuration', host[key], original_host[key], [name, key])
        replay.equal('single_qemu', len(host['qemu']), 1, name)
        for key in ('pid', 'args'):
            replay.equal('qemu_identity', host['qemu'][0][key], original_host['qemu'][0][key], [name, key])
        replay.equal('qemu_thread_placement', pins(host), pins(original_host), name)
    for key in ('boot_id', 'cmdline', 'preemption', 'packages', 'python', 'snapshot_tag', 'collector_topology'):
        replay.equal('guest_configuration', replay.jread('environment.json')[key],
                     original.jread('matrix/environment.json')[key], key)
    replay.equal('guest_topology', replay.jread('topology.json'), original.jread('matrix/topology.json'))
    replay.expect('environment_comparison', replay.jread('environment-comparison.json')['configuration_matches'])
    records, plan, state = (replay.jread(p+'.json') for p in ('records', 'plan', 'status'))
    points = {(r['comparison_workload'], r['threads']) for r in plan}
    original_records = [r for r in original.jread('matrix/records.json')
                        if (r['comparison_workload'], r['threads']) in points]
    order = [r for r in original.jread('matrix/execution-order.json') if tuple(r[:2]) in points]
    replay.equal('complete_state', [state['state'], state['completed'], state['planned']], ['COMPLETE', 120, 120])
    replay.equal('counts', [len(records), len(plan), len(state['sessions'])], [120]*3)
    replay.equal('unique_names', len({r['name'] for r in records}), 120)
    replay.equal('filtered_original_order', replay.jread('execution-order.json'), order)
    by_name = {r['name']: r for r in original_records}
    binding = ('comparison_workload', 'threads', 'repeat', 'comparison_arm', 'arm',
               'source_identity', 'caller_shell', 'cookie_storage', 'cpus', 'cpu_nodes',
               'collector_cpu', 'collector_shared', 'duration_ms', 'peak_window_ms',
               'peak_settle_ms', 'sample_ms', 'warmup_iterations_per_worker', 'warmup',
               'warmup_ms', 'warmup_policy', 'warmup_pause_seconds', 'entries', 'value_size',
               'file_descriptions', 'syscalls_per_op', 'post_work_rounds', 'numa_policy',
               'spin_entry_ratio_limit', 'spin_prefetch', 'delegation_batch_limit',
               'kd_provider_ubsan', 'diagnostic', 'pmu', 'perf_record')
    grouped = defaultdict(list)
    classes = Counter()
    for i, row in enumerate(records):
        name = row['evidence_path'].removeprefix(replay.guest_base)
        replay.expect('session_within_round', name.startswith('measurements/'), row['name'])
        replay.equal('order_identity', [row[k] for k in
                     ('comparison_workload', 'threads', 'repeat', 'comparison_arm')], order[i], name)
        replay.equal('plan_binding', {k: row.get(k) for k in plan[i]}, plan[i], name)
        replay.equal('saved_session_binding', row, replay.jread(name+'/session.json'), name)
        replay.equal('state_session_binding', state['sessions'][i],
                     dict(name=row['name'], status=row['execution_status'],
                          drained=row['drained'], path=row['evidence_path']), name)
        replay.equal('original_settings', {k: row.get(k) for k in binding},
                     {k: by_name[row['name']].get(k) for k in binding}, name)
        replay.expect('session_verdict', row['execution_status'] == 'OK' and row['drained']
                      and not row.get('cleanup_error'), name)
        replay.expect('kernel_log_clean', not helper.FAULT.search(
                      replay.contents[name+'/kernel.log'].decode(errors='replace')), name)
        m = row['measurement']
        replay.expect('measurement_binding',
                      all(m.get(k) == v for k, v in replay.jread(name+'/measure.json').items()), name)
        replay.equal('worker_cpu_prefix', [w['cpu'] for w in m['workers']], row['cpus'], name)
        replay.equal('worker_sum', sum(w['completed'] for w in m['workers']), m['completed'], name)
        replay.expect('worker_progress', all(w['completed'] > 0 and w['error'] == 0
                      and w['observed_cpu'] == w['cpu'] for w in m['workers']), name)
        synthetic = row['comparison_workload'] in ('c08', 'rcuht')
        replay.expect('business_oracle', m['complete'] and m['data_ok'] if synthetic else m['ok'], name)
        if synthetic:
            delta = [b-a for a, b in zip(m['before'], m['after'])]
            if row['comparison_workload'] == 'rcuht':
                replay.expect('hash_oracle', m['hash_integrity_ok'] and delta[0] == m['completed']
                              and m['before'][0] == sum(m['before'][1:4])
                              and m['after'][0] == sum(m['after'][1:4])
                              and not any(m['before'][4:]+m['after'][4:]), name)
            else:
                replay.equal('cacheline_oracle', delta, [m['completed']]*8+[0]*8, name)
        whole = m['completed']*1e9/m['wall_ns']
        replay.peak(dict(row, whole_throughput_ops_s=whole), name)
        evidence = 'NOT_APPLICABLE'
        if row['arm'] == 'kdlock':
            entries = row['jit_bodies']
            replay.expect('entry_bounds', 0 <= entries <= m['completed'], name)
            if synthetic:
                evidence = 'WITNESSED_JIT' if entries else 'NO_JIT'
            else:
                returns = row['jit_completions']
                replay.expect('return_bounds', 0 <= returns <= entries, name)
                evidence = 'RETURNED_JIT' if returns else 'PARTIAL_JIT' if entries else 'NO_JIT'
            replay.equal('exact_retirement', row['retired'], dict(state=2, modules=0, writers=0, frames=0), name)
            replay.equal('stable_publication', row['published_before'], row['published_after'], name)
            for filename, digest in row['published_before']['images'].items():
                replay.expect('retained_published_image', any(
                    p.startswith(name+'/workspace/') and Path(p).name == filename and h == digest
                    for p, h in replay.files.items()), [name, filename])
        classes[evidence] += 1
        grouped[(row['comparison_workload'], row['threads'], row['comparison_arm'], evidence)].append(row)
    replay.equal('health_classes', dict(classes), health['execution_classes'])
    replay.equal('health_retirements', health['exact_retirements'],
                 [dict(name=r['name'], retired=r['retired']) for r in records if r['arm'] == 'kdlock'])
    analysis = replay.jread('analysis-final/comparisons.json')
    replay.equal('analysis_script_binding', analysis['script_sha256'],
                 replay.files['analysis-final/compare-observed.py'])
    for point in analysis['points']:
        groups = point['runs']['mutex-public-20261020-observed-1']['groups']
        for group in groups:
            key = group['workload'], group['threads'], group['arm'], group['execution_class']
            selected = grouped[key]
            rates = [r['measurement']['completed']*1e9/r['measurement']['wall_ns'] for r in selected]
            expected = dict(planned=len(selected), accepted=len(selected), whole_min=min(rates),
                whole_median=median(rates), whole_max=max(rates),
                whole_spread_pct=100*(max(rates)-min(rates))/median(rates),
                comparable_three_repeats=sorted(r['repeat'] for r in selected) == [0, 1, 2])
            replay.equal('independent_summary_arithmetic', {k: group[k] for k in expected}, expected, key)
        for score in point['runs']['mutex-public-20261020-observed-1']['outer_comparisons']:
            public = next(g for g in groups if g['arm'] == 'public-kd' and
                          g['execution_class'] == score['public_execution_class'])
            controls = [g for g in groups if g['arm'] == 'baseline-kd'
                        and g['execution_class'] == public['execution_class']]
            complete = public['comparable_three_repeats'] and len(controls) == 1 and controls[0]['comparable_three_repeats']
            replay.equal('independent_comparison_ratio', score['whole_median_ratio'],
                         public['whole_median']/controls[0]['whole_median'] if complete else None)
            replay.equal('independent_range_screen', score['loss_exceeds_observed_range'],
                         public['whole_max'] < .95*controls[0]['whole_min'] if complete else None)
            replay.equal('latency_remains_unmeasured', score['p95_latency_gate'], 'UNMEASURED')
            replay.equal('acceptance_remains_open', score['overall_acceptance'], 'OPEN')
    def csv_member(name):
        with tarfile.open(replay.raw/replay.members[name]['archive']) as archive:
            data = archive.extractfile(replay.prefix+name).read()
        replay.equal('csv_member_rechecked', helper.sha(data), replay.files[name], name)
        return list(csv.DictReader(io.StringIO(data.decode())))

    csv_rows = csv_member('analysis-final/per-repeat.csv')
    replay.equal('per_repeat_count', len(csv_rows), 360)
    for name, item in analysis['inputs'].items():
        local = args.repo/item['path']
        replay.equal('comparison_input_hash', helper.hashfile(local), item['sha256'], name)
        indexed = {r['name']: r for r in json.loads(local.read_text())}
        selected_csv = [r for r in csv_rows if r['run'] == name]
        replay.equal('csv_run_count', len(selected_csv), 120, name)
        for r in selected_csv:
            source = indexed[r['name']]
            replay.equal('per_repeat_arithmetic', float(r['whole_ops_s']),
                         source['measurement']['completed']*1e9/source['measurement']['wall_ns'], r['name'])
    observation = replay.jread('analysis-final/host-observation-summary.json')
    replay.equal('observer_analysis_binding', observation['source_sha256'],
                 replay.files['analysis-final/observe-analysis.py'])
    for name, digest in observation['input_sha256'].items():
        member = name if name in ('records.json', 'session-clocks.jsonl') else 'host-observation/'+name
        replay.equal('observation_input_binding', replay.files[member], digest, member)
    for name in ('host_observer.py', 'clock_calibration.py'):
        replay.equal('observation_source_git', replay.files['host-observation/'+name],
                     helper.sha(replay.git_bytes('bc72912', 'bench/mutex_api_compare/'+name)))
    replay.equal('observer_source_hash', observation['header']['source_sha256'],
                 replay.files['host-observation/host_observer.py'])
    replay.expect('observer_finished_naturally', observation['complete'] and
                  not observation['final']['stopped_by_signal'] and
                  observation['final']['failures'] == 0 and not observation['issues'])
    for name in ('comparisons.json', 'per-repeat.csv', 'host-observation-summary.json'):
        replay.equal('compact_report_binding', helper.hashfile(args.report/name),
                     replay.files['analysis-final/'+name], name)
    # The first CSV used the csv module's default CRLF. Preserve it in its
    # original archive and prove that LF normalization changed no data rows.
    first_csv = csv_member('analysis/per-repeat.csv')
    replay.equal('csv_format_only_revision', csv_rows, first_csv)
    result = dict(consistent=not any(a.issues for a in audits.values()),
        checks=sum(sum(a.counts.values()) for a in audits.values()),
        check_counts={k: dict(a.counts) for k, a in audits.items()},
        issues={k: a.issues for k, a in audits.items()}, archives=archive_details,
        sessions=120, execution_classes=dict(classes), reconstructed_windows=len(replay.windows),
        source_host=socket.gethostname(), script_sha256=helper.hashfile(Path(__file__)),
        limits='Strict post-run QEMU thread-set mismatch remains an issue; it is not waived. '
               'Observer sampling and clock uncertainties are separately retained. No live test.')
    output.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k not in
                     ('check_counts', 'archives', 'issues')}, indent=2))
    print(json.dumps({k: [dict(check=i['check'], detail=i.get('detail'))
                         for i in a.issues if i['check'] != 'qemu_thread_placement']
                      for k, a in audits.items()}))
    return int(not result['consistent'])


if __name__ == '__main__':
    raise SystemExit(main())
