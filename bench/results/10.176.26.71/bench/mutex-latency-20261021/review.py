#!/usr/bin/env python3
"""Inert archive, original-input and sample arithmetic review on 380G10."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import posixpath
import socket
from statistics import median, mean, stdev
import sys
import tarfile
from types import SimpleNamespace

HELPER = 'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/offline-review.py'
HELPER_SHA = '05b87daa59dd00c658b042f8e6bf30ee60d5c811956a5a132053d9708ae4ebf6'
ORIGINAL_SHA = '7b7dad099d06b2c8964d9e1831b9e02e7f0bba0e209420982a5904972330c3c4'
POINTS = {('c08', 3), ('c08', 4), ('c08', 5), ('rcuht', 2),
          ('pipebytes', 3), ('pipebytes', 5), ('pipecap', 5)}
MODES = ('plain', 'disabled', 'sampled')
MASK = (1 << 64)-1


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def stats(values):
    if not values:
        return None
    return dict(n=len(values), minimum=min(values), median=median(values), maximum=max(values),
                spread_pct=100*(max(values)-min(values))/median(values),
                cv_pct=100*stdev(values)/mean(values) if len(values) > 1 else None)


def quantile(values):
    return sorted(values)[math.ceil(.95*len(values))-1] if values else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run', default='run-2')
    parser.add_argument('--inputs', default='inputs-4')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[5]
    assert socket.gethostname() == '380G10' and not args.output.exists()
    args.output.mkdir()
    sys.dont_write_bytecode = True
    helper_path = repo/HELPER
    assert hashlib.sha256(helper_path.read_bytes()).hexdigest() == HELPER_SHA
    spec = importlib.util.spec_from_file_location('latency_inert_archive_helper', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    original_raw = args.raw.parent/'mutex-public-20261020-r2'
    assert helper.hashfile(original_raw/'archives.json') == ORIGINAL_SHA
    original_manifest = json.loads((original_raw/'archives.json').read_text())
    original_inventory = json.loads((original_raw/'input-inventory.json').read_text())
    assert helper.hashfile(original_raw/'input-inventory.json') == original_manifest['input_inventory_sha256']

    class Audit(helper.Audit):
        def target_retained(self, target):
            roots = {self.guest_base.rstrip('/'): self.inventory,
                     original_manifest['guest_base'].rstrip('/'): original_inventory}
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
                for length in range(1, len(parts)+1):
                    name = '/'.join(parts[:length])
                    item = roots[root].get(name)
                    if item is None:
                        return False
                    if item.get('link') is not None:
                        link = item['link']
                        target = link if link.startswith('/') else posixpath.join(root, posixpath.dirname(name), link)
                        if length < len(parts):
                            target = posixpath.join(target, *parts[length:])
                        break
                else:
                    return True
            return False

        def check(self, value, label, detail=None):
            if label == 'symlink_target_retained':
                value = self.target_retained(detail['target'])
            return super().check(value, label, detail)

    original = Audit(SimpleNamespace(repo=repo, raw=original_raw, report=args.output))
    audit = Audit(SimpleNamespace(repo=repo, raw=args.raw, report=args.output))
    archives = {}
    for name, item in (('original', original), ('latency', audit)):
        groups, links = item.load_archives()
        archives[name] = dict(groups=groups, links=len(links), files=len(item.files),
                              manifest_sha256=helper.hashfile(item.raw/'archives.json'))
    check, equal = audit.check, audit.equal
    j = audit.jread
    base, inp = args.run+'/', args.inputs+'/'
    inputs = j(inp+'inputs.json')
    check(inputs['complete'] and j(inp+'state.json')['complete'], 'prepared_complete')
    equal('input_manifest_identity', j(base+'status.json')['inputs_sha256'], audit.files[inp+'inputs.json'])
    equal('run_manifest_copy', audit.files[base+'inputs.json'], audit.files[inp+'inputs.json'])
    for p, h in inputs['immutable_files'].items():
        equal('immutable_input_hash', audit.files.get(inp+p), h, p)
    for filename in ('latency.py', 'latency_inputs.py', 'latency_overlay.py', 'latency_run.py'):
        equal('tool_git_binding', audit.files[inp+'tools/'+filename],
              helper.sha(audit.git_bytes(inputs['source_commit'], 'bench/mutex_api_compare/'+filename)), filename)
    for name in ('operation_latency.h', 'kernel.inc', 'client.inc'):
        equal('payload_git_binding', audit.files[inp+'tools/'+name],
              helper.sha(audit.git_bytes(inputs['source_commit'], 'workload_modules/latency/'+name)), name)
    for name in ('baseline', 'current', 'tclock'):
        crc = j(inp+'exports-'+name+'.crc.json')
        check(crc['equal'] and crc['original'] and crc['original'] == crc['rebuilt'], 'export_crc_receipt', name)
    bodies = j(inp+'body-audits.json')
    equal('eight_compiled_bodies', len(bodies), 8)
    for key, body in bodies.items():
        check(body['equal'] and body['before'] == body['after'], 'compiled_body_receipt', key)
    for key, item in inputs['bundles'].items():
        prefix = inp+'bundles/'+key+'/'
        source, old = j(prefix+'source-sha256.json'), original.jread(key+'/source-sha256.json')
        equal('source_additions', set(source)-set(old), set(item['source_additions']), key)
        equal('one_allowed_source_change', {p for p in old if source.get(p) != old[p]},
              {item['changed_source']}, key)
        for p, h in source.items():
            equal('prepared_source_hash', audit.files[prefix+'source/'+p], h, [key, p])
            if p in old and p != item['changed_source']:
                equal('original_source_retained', h, original.files[key+'/source/'+p], [key, p])
        for p, name in item['source_additions'].items():
            equal('payload_copy', source[p], audit.files[inp+'tools/'+name], [key, p])
        for p, identity in item['binaries'].items():
            equal('original_binary_binding', identity['original_sha256'], original.files[key+'/'+p], [key, p])
            equal('prepared_binary_binding', identity['sha256'], audit.files[prefix+p], [key, p])
            if p not in item['changed_binaries']:
                equal('original_binary_unchanged', identity['sha256'], identity['original_sha256'], [key, p])
        equal('original_plan', audit.files[prefix+'plan.json'], original.files[key+'/plan.json'], key)
    for name in ('checks-1', 'checks-2', 'checks-3', 'checks-4'):
        receipt = j(name+'/result.json')
        check(receipt['passed'] and receipt['final_idle'], 'focused_checks', name)
        for p, h in receipt['source_files'].items():
            equal('check_source_git', h, helper.sha(audit.git_bytes(receipt['source_commit'], p)), [name, p])

    original_host = original.jread('matrix/host-state.json')
    host_failures = []
    for name in ('before', 'after'):
        host = j(base+'host-'+name+'.json')
        for key in ('cpufreq', 'numa', 'recovery_snapshot'):
            equal('host_configuration', host[key], original_host[key], [name, key])
        for key in ('pid', 'args'):
            equal('qemu_identity', host['qemu'][0][key], original_host['qemu'][0][key], [name, key])
        same_tasks = sorted(host['qemu'][0]['tasks'], key=lambda t: t['tid']) == sorted(
            original_host['qemu'][0]['tasks'], key=lambda t: t['tid'])
        if not same_tasks:
            host_failures.append(dict(endpoint=name, captured_utc=host['captured_utc'],
                expected=67, actual=len(host['qemu'][0]['tasks']), issue='strict QEMU thread set differs'))
        if name == 'before':
            check(same_tasks and host['pins_verified'] and host['snapshot_listed'], 'strict_preflight')
    for key in ('boot_id', 'cmdline', 'preemption', 'packages', 'python', 'snapshot_tag', 'collector_topology'):
        equal('guest_environment', j(base+'environment.json')[key],
              original.jread('matrix/environment.json')[key], key)
    equal('guest_topology', j(base+'topology.json'), original.jread('matrix/topology.json'))
    old_order = [r for r in original.jread('matrix/execution-order.json') if tuple(r[:2]) in POINTS]
    expected_order = []
    for i in range(0, len(old_order), 4):
        group = old_order[i:i+4]
        repeat = group[0][2]
        for mode in MODES[repeat:]+MODES[:repeat]:
            expected_order.extend([*r, mode] for r in group)
    equal('fixed_plan', j(base+'execution-order.json'), expected_order)
    records, state = j(base+'records.json'), j(base+'status.json')
    equal('completed_plan', [state['state'], state['complete'], state['planned'], state['completed'],
          ['COMPLETE', True, 252, 252])
    equal('record_count', len(records), 252)
    equal('unique_sessions', len({r['name'] for r in records}), 252)
    audit.windows = []
    old_records = {r['name']: r for r in original.jread('matrix/records.json')}
    binding = ('comparison_workload', 'threads', 'repeat', 'comparison_arm', 'arm',
        'caller_shell', 'cookie_storage', 'cpus', 'cpu_nodes', 'collector_cpu', 'collector_shared',
        'duration_ms', 'peak_window_ms', 'peak_settle_ms', 'sample_ms', 'warmup_iterations_per_worker',
        'warmup', 'warmup_ms', 'warmup_policy', 'warmup_pause_seconds', 'entries', 'value_size',
        'file_descriptions', 'syscalls_per_op', 'post_work_rounds', 'numa_policy',
        'spin_entry_ratio_limit', 'spin_prefetch', 'delegation_batch_limit', 'kd_provider_ubsan',
        'pmu', 'perf_record')
    grouped, rows, execution = defaultdict(list), [], Counter()
    sample_total = 0
    for index, record in enumerate(records):
        name = record['evidence_path'].removeprefix(audit.guest_base)
        mode = record['latency_mode']
        old_name = record['name'].removesuffix('-'+mode)
        old = old_records[old_name]
        equal('order', [record[k] for k in ('comparison_workload', 'threads', 'repeat',
              'comparison_arm', 'latency_mode')], expected_order[index], name)
        equal('session_record', record, j(name+'/session.json'), name)
        equal('state_record', state['sessions'][index], dict(name=record['name'],
              path=record['evidence_path'], status=record['execution_status'], drained=True), name)
        equal('original_settings', {k: record.get(k) for k in binding}, {k: old.get(k) for k in binding}, name)
        check(record['execution_status'] == 'OK' and record['drained'] and
              not record.get('cleanup_error'), 'strict_session', name)
        check(not helper.FAULT.search(audit.contents[name+'/kernel.log'].decode(errors='replace')),
              'kernel_log', name)
        group = record['comparison_workload']
        key = ('baseline' if record['comparison_arm'] == 'baseline-kd' else 'current')+'/'+group
        identity = original.jread('frozen-inputs.json')[key]['source_identity'] if mode == 'plain' else inputs['bundles'][key]['source_identity']
        equal('source_identity', record['source_identity'], identity, name)
        measured = record['measurement']
        raw_measure = j(name+'/measure.json')
        check(all(measured.get(k) == v for k, v in raw_measure.items()), 'measurement_binding', name)
        synthetic = group in ('c08', 'rcuht')
        check(measured['complete'] and measured['data_ok'] if synthetic else measured['ok'], 'business_oracle', name)
        if synthetic:
            delta = [b-a for a, b in zip(measured['before'], measured['after'])]
            if group == 'c08':
                equal('protected_cacheline_effect', delta, [measured['completed']]*8+[0]*8, name)
            else:
                check(measured['hash_integrity_ok'] and delta[0] == measured['completed'] and
                      all(v[0] == sum(v[1:4]) and not any(v[4:]) for v in
                          (measured['before'], measured['after'])), 'protected_hash_effect', name)
        rate = measured['completed']*1e9/measured['wall_ns']
        audit.peak(dict(record, whole_throughput_ops_s=rate), name)
        cls = 'NOT_APPLICABLE'
        if record['arm'] == 'kdlock':
            entries = record['jit_bodies']
            check(0 <= entries <= measured['completed'], 'jit_bounds', name)
            cls = 'WITNESSED_JIT' if entries else 'NO_JIT'
            if not synthetic:
                returns = record['jit_completions']
                check(0 <= returns <= entries, 'jit_return_bounds', name)
                cls = 'RETURNED_JIT' if returns else 'PARTIAL_JIT' if entries else 'NO_JIT'
            equal('exact_retirement', record['retired'], dict(state=2, modules=0, writers=0, frames=0), name)
            for key in ('entry', 'images'):
                equal('stable_publication', record['published_before'][key], record['published_after'][key], [name, key])
            for filename, digest in record['published_before']['images'].items():
                check(any(p.startswith(name+'/workspace/') and Path(p).name == filename and h == digest
                          for p, h in audit.files.items()), 'publication_artifact', [name, filename])
        execution[mode+'/'+cls] += 1
        p95, sufficient, sample_count = None, False, 0
        if mode != 'plain':
            observation = j(name+'/latency.json')
            equal('latency_summary', observation['summary'], record['operation_latency'], name)
            observed = observation['rows']
            equal('latency_workers', len(observed), len(measured['workers']), name)
            values, per_worker = [], []
            for worker, (item, progress) in enumerate(zip(observed, measured['workers'])):
                sequence = []
                random = ((worker+1)*0x9e3779b97f4a7c15) & MASK
                if mode == 'sampled':
                    for first in range(0, progress['completed'], 256):
                        random ^= random >> 12
                        random ^= (random << 25) & MASK
                        random ^= random >> 27
                        ordinal = first+((random*0x2545f4914f6cdd1d) & 255)
                        if ordinal < progress['completed']:
                            sequence.append(ordinal)
                equal('latency_worker_identity', {k: item[k] for k in
                      ('worker', 'completed', 'selected', 'dropped', 'enabled')},
                      dict(worker=worker, completed=progress['completed'], selected=len(sequence),
                           dropped=0, enabled=mode == 'sampled'), [name, worker])
                equal('exact_sampling_schedule', [s[0] for s in item['samples']], sequence, [name, worker])
                check(len(sequence) <= 131072, 'no_sample_overflow', [name, worker])
                last = progress['active_started_ns']
                durations = []
                for ordinal, start, finish in item['samples']:
                    check(all(type(v) is int for v in (ordinal, start, finish)) and
                          last <= start < finish <= progress['kernel_finished_ns'],
                          'sample_clock_extent', [name, worker, ordinal])
                    last = finish
                    durations.append(finish-start)
                values.extend(durations)
                per_worker.append(dict(worker=worker, cpu=progress['cpu'], samples=len(durations),
                    median_ns=median(durations) if durations else None,
                    p95_ns=quantile(durations), max_ns=max(durations) if durations else None))
            summary = observation['summary']
            p95, sample_count = quantile(values), len(values)
            sufficient = mode == 'sampled' and all(w['samples'] >= 1000 for w in per_worker)
            expected = dict(version=1, enabled=mode == 'sampled', stride=256,
                percentile_method='nearest_rank', samples=sample_count, minimum_samples_per_worker=1000,
                sufficient=sufficient, median_ns=median(values) if values else None, p95_ns=p95,
                max_ns=max(values) if values else None, workers=per_worker, calibration_subtracted=False)
            equal('independent_latency_arithmetic', {k: summary[k] for k in expected}, expected, name)
            if not synthetic:
                equal('client_observation_binding', raw_measure['operation_latency']['rows'], observed, name)
            sample_total += sample_count
        row = dict(name=record['name'], workload=group, threads=record['threads'],
            repeat=record['repeat'], arm=record['comparison_arm'], mode=mode, execution_class=cls,
            whole_mops=rate/1e6, peak_mops=measured['peak']['throughput_ops_s']/1e6,
            jit_entries=record.get('jit_bodies'), jit_returns=record.get('jit_completions'),
            latency_samples=sample_count, p95_ns=p95, sufficient=sufficient)
        rows.append(row)
        grouped[group, record['threads'], record['comparison_arm'], mode, cls].append(row)
    groups = []
    for key, members in sorted(grouped.items()):
        g, n, arm, mode, cls = key
        groups.append(dict(workload=g, threads=n, arm=arm, mode=mode, execution_class=cls,
            repeats=sorted(r['repeat'] for r in members), complete=sorted(r['repeat'] for r in members) == [0, 1, 2],
            whole_mops=stats([r['whole_mops'] for r in members]),
            p95_ns=stats([r['p95_ns'] for r in members if r['p95_ns'] is not None]),
            all_latency_sufficient=all(r['sufficient'] for r in members)))
    comparisons = []
    for g, n in sorted(POINTS):
        for mode in MODES:
            public = [r for r in groups if (r['workload'], r['threads'], r['mode'], r['arm']) == (g, n, mode, 'public-kd')]
            for p in public:
                controls = [r for r in groups if (r['workload'], r['threads'], r['mode'], r['arm'], r['execution_class'])
                            == (g, n, mode, 'baseline-kd', p['execution_class'])]
                comparable = p['complete'] and len(controls) == 1 and controls[0]['complete']
                control = controls[0] if comparable else None
                latency_ok = comparable and mode == 'sampled' and p['all_latency_sufficient'] and control['all_latency_sufficient']
                comparisons.append(dict(workload=g, threads=n, mode=mode, execution_class=p['execution_class'],
                    same_class_three_repeats=comparable,
                    public_outer_whole_ratio=p['whole_mops']['median']/control['whole_mops']['median'] if comparable else None,
                    sufficient_sampled_latency=latency_ok,
                    public_outer_p95_ratio=p['p95_ns']['median']/control['p95_ns']['median'] if latency_ok else None,
                    accepted=False))
    overhead = []
    for g, n in sorted(POINTS):
        for arm in ('baseline-kd', 'public-kd', 'native', 'tclock'):
            for before, after in (('plain', 'disabled'), ('disabled', 'sampled')):
                left = [r for r in groups if (r['workload'], r['threads'], r['arm'], r['mode']) == (g, n, arm, before)]
                right = [r for r in groups if (r['workload'], r['threads'], r['arm'], r['mode']) == (g, n, arm, after)]
                same = len(left) == len(right) == 1 and left[0]['complete'] and right[0]['complete'] and left[0]['execution_class'] == right[0]['execution_class']
                overhead.append(dict(workload=g, threads=n, arm=arm, before=before, after=after,
                    comparable=same, before_classes=[r['execution_class'] for r in left],
                    after_classes=[r['execution_class'] for r in right],
                    whole_ratio=right[0]['whole_mops']['median']/left[0]['whole_mops']['median'] if same else None))
    with (args.output/'per-repeat.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    save(args.output/'groups.json', groups)
    save(args.output/'comparisons.json', comparisons)
    save(args.output/'overhead.json', overhead)
    result = dict(evidence_consistent=not audit.issues and not original.issues,
        checks=sum(audit.counts.values())+sum(original.counts.values()),
        check_counts=dict(audit.counts), issues=audit.issues, original_issues=original.issues,
        host_failures=host_failures, archives=archives, sessions=len(records), samples=sample_total,
        execution_classes=dict(execution), insufficient_sampled_sessions=[r['name'] for r in rows
            if r['mode'] == 'sampled' and not r['sufficient']], accepted=False,
        source_host=socket.gethostname(), script_sha256=helper.hashfile(Path(__file__)),
        limits='Observation receipt/body equality is not an independent ELF reconstruction. '
               'Synthetic JIT evidence is entry-only. No causal fix or whole-kernel acceptance.')
    save(args.output/'review.json', result)
    print(json.dumps({k: result[k] for k in ('evidence_consistent', 'checks', 'sessions', 'samples',
                                            'host_failures', 'insufficient_sampled_sessions')}, indent=2))
    if audit.issues or original.issues:
        print(json.dumps(dict(issues=audit.issues[:20], original=original.issues[:20]), indent=2))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
