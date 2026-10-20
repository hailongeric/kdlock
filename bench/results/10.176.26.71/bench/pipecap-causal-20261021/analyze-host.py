#!/usr/bin/env python3
"""Read completed host samples and guest receipts without executing their code."""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from statistics import median


def read(path):
    return json.loads(path.read_text())


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def interval_stats(values):
    return dict(min=min(values), median=median(values), max=max(values))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--number', type=int, choices=(1,2), required=True)
    args = parser.parse_args()
    raw = args.raw
    before, after = (read(raw/f'clock-{side}-{args.number}.json') for side in ('before','after'))
    assert before['complete'] and after['complete']
    assert before['source_boot_id'] == after['source_boot_id']
    assert before['source_host'] == after['source_host'] == '380G10'
    bounds, boot, rtts = {}, {}, {}
    for target in ('guest', 'host'):
        selected = [r for capture in (before, after)
                    for r in capture['samples'] if r['target'] == target]
        assert len(selected) == 6
        offsets = []
        for row in selected:
            clock = row['target_clock']
            assert clock['affinity'] == [62]
            assert row['source_before_ns'] <= row['source_after_ns']
            pair = [row['source_before_ns']-clock['monotonic_ns'],
                    row['source_after_ns']-clock['monotonic_ns']]
            assert pair == row['source_minus_target_bounds_ns']
            offsets.append(pair)
        bounds[target] = [min(b[0] for b in offsets), max(b[1] for b in offsets)]
        identities = {r['target_clock']['boot_id'] for r in selected}
        assert len(identities) == 1
        boot[target] = identities.pop()
        rtts[target] = [b[1]-b[0] for b in offsets]
    # Retain the envelope of every RTT, including the slowest observation.
    # This projects endpoints only under the explicit between-capture condition
    # below; finite endpoint samples cannot prove the clocks' intervening rate.
    delta = [bounds['guest'][0]-bounds['host'][1],
             bounds['guest'][1]-bounds['host'][0]]
    records = read(raw/f'run-{args.number}-records.json')
    original_ids = {r['tid'] for r in read(raw/'host-original.json')['qemu'][0]['tasks']}
    assert len(original_ids) == 67
    rows = []
    for record in records:
        if record['execution_status'] not in ('OK','NO_JIT'):
            continue
        m, name = record['measurement'], record['name']
        start, finish = m['started_ns'], m['finished_ns']
        assert start < finish
        assert record['collector_cpu'] == 63 and record['threads'] <= 5
        rows.append(dict(name=name, arm=record['comparison_arm'],
            workload=record['comparison_workload'], threads=record['threads'],
            guest_measurement_ns=[start, finish],
            possible_host_window_ns=[start+delta[0], finish+delta[1]],
            common_host_interior_ns=[start+delta[1], finish+delta[0]],
            observed_samples=0, task_count_range=[1 << 30, 0],
            additional_task_ids=set(), disappeared_during_sample=set(),
            runtime_in_overlapping_intervals_ns=Counter(),
            runtime_in_fully_contained_intervals_ns=Counter(),
            max_sample_gap_ns=0))
    assert len(rows) == (6 if args.number == 1 else 48)
    previous, header, final = None, None, None
    durations, gaps, counts, issues = [], [], [], []
    task_lifetimes = {}
    runtime_total = Counter()
    samples = 0

    def category(task):
        key = (task['tid'], task['start_ticks'])
        if task['comm'] == 'CPU 63/KVM':
            return 'collector_vcpu_63'
        if task['comm'].startswith('CPU ') and task['comm'].endswith('/KVM'):
            return 'worker_vcpus_0_4' if int(task['comm'][4:-4]) < 5 else 'other_vcpus'
        return 'original_service' if task['tid'] in original_ids else 'additional_service'

    with gzip.open(raw/f'host-observation-{args.number}.jsonl.gz', 'rt') as stream:
        for line in stream:
            sample = json.loads(line)
            kind = sample['kind']
            if kind == 'header':
                assert header is None and previous is None
                header = sample
                assert header['boot_id'] == boot['host']
                assert header['observer_affinity'] == [62]
                continue
            if kind == 'final':
                assert final is None
                final = sample
                continue
            if kind != 'sample':
                issues.append(sample)
                continue
            assert header is not None and final is None
            assert sample['sequence'] == samples
            samples += 1
            a, b = sample['monotonic_begin_ns'], sample['monotonic_end_ns']
            assert a <= b
            durations.append(b-a)
            counts.append(len(sample['tasks']))
            tasks = {(t['tid'], t['start_ticks']): t for t in sample['tasks']}
            assert len(tasks) == len(sample['tasks'])
            assert original_ids <= {t['tid'] for t in tasks.values()}
            if sample['placement_issues']:
                issues.append(dict(sequence=sample['sequence'], issues=sample['placement_issues']))
            for key, task in tasks.items():
                assert task['affinity'] == ([int(task['comm'][4:-4])]
                    if task['comm'].startswith('CPU ') and task['comm'].endswith('/KVM') else [63])
                lifetime = task_lifetimes.setdefault(key, dict(tid=key[0], start_ticks=key[1],
                    comm=task['comm'], category=category(task), first_seen_ns=a,
                    first_runtime_ns=task['runtime_ns'], samples=0))
                lifetime.update(last_seen_ns=b, last_runtime_ns=task['runtime_ns'])
                lifetime['samples'] += 1
            overlapping = [r for r in rows if a <= r['possible_host_window_ns'][1]
                           and b >= r['possible_host_window_ns'][0]]
            for row in overlapping:
                row['observed_samples'] += 1
                row['task_count_range'][0] = min(row['task_count_range'][0], len(tasks))
                row['task_count_range'][1] = max(row['task_count_range'][1], len(tasks))
                row['additional_task_ids'].update(f'{tid}:{start}' for tid, start in tasks if tid not in original_ids)
                row['disappeared_during_sample'].update(sample['disappeared_during_sample'])
            if previous is not None:
                previous_sample, old_tasks = previous
                p = previous_sample['monotonic_begin_ns']
                gap = a-previous_sample['monotonic_end_ns']
                assert gap >= 0
                gaps.append(gap)
                changes = Counter()
                for key in set(old_tasks) & set(tasks):
                    elapsed = tasks[key]['runtime_ns']-old_tasks[key]['runtime_ns']
                    assert elapsed >= 0, key
                    changes[category(tasks[key])] += elapsed
                runtime_total.update(changes)
                for row in rows:
                    low, high = row['possible_host_window_ns']
                    if p <= high and b >= low:
                        row['runtime_in_overlapping_intervals_ns'].update(changes)
                        row['max_sample_gap_ns'] = max(row['max_sample_gap_ns'], gap)
                    low, high = row['common_host_interior_ns']
                    if low <= p <= b <= high:
                        row['runtime_in_fully_contained_intervals_ns'].update(changes)
            previous = (sample, tasks)
    assert header is not None and final is not None
    assert final['samples'] == samples and final['failures'] == len(issues) == 0
    assert final['stopped_by_signal'] is False
    for row in rows:
        assert row['observed_samples'] > 0
        for key in ('additional_task_ids', 'disappeared_during_sample'):
            row[key] = sorted(row[key])
    result = dict(schema=1, complete=True, measured_run=f'pipecap-causal-20261021/run-{args.number}',
        measured_collection='d21a1e3',
        source_sha256=sha(Path(__file__)), input_sha256={p: sha(raw/p) for p in
            (f'clock-before-{args.number}.json', f'clock-after-{args.number}.json',
             f'host-observation-{args.number}.jsonl.gz',f'run-{args.number}-records.json','host-original.json')},
        host_boot=boot['host'], guest_boot=boot['guest'],
        header=header, final=final, issues=issues, samples=samples,
        sample_duration_ns=interval_stats(durations), inter_sample_gap_ns=interval_stats(gaps),
        observed_task_count=interval_stats(counts), runtime_observed_deltas_ns=runtime_total,
        observer_cpu_fraction=final['observer_cpu_ns']/final['elapsed_ns'],
        cross_clock=dict(source_minus_target_envelope_ns=bounds,
            host_minus_guest_envelope_ns=delta, rtt_ns=rtts,
            condition='Projection assumes offsets between endpoint calibrations remain inside '
                      'the envelope of all observed RTT bounds. Intervening drift is unproven.'),
        runqueue_delay=('UNMEASURED: scheduler statistics disabled'
                        if header['scheduler_stats'] == '0' else 'Available in raw samples'),
        limits=['Polling can miss entire short-lived tasks and CPU use after their last sample.',
                'Overlapping-interval totals are observed deltas, not global upper bounds.',
                'Birth-to-first-sample CPU and final-to-exit CPU are excluded from interval deltas.',
                'Only QEMU threads were sampled; other host tasks and all sources of interference '
                'were not measured. Presence, runtime or correlation does not prove causation.',
                'No task-count/placement admission check is waived by this report.',
                'Observer overhead and clock-bracket instrumentation distinguish this collection '
                'from the original matrix and plain replay; do not pool their timings.'],
        tasks=list(task_lifetimes.values()), sessions=rows)
    save(args.output, result)
    print(json.dumps({k: result[k] for k in ('complete', 'samples', 'observed_task_count',
        'inter_sample_gap_ns', 'sample_duration_ns', 'observer_cpu_fraction',
        'runtime_observed_deltas_ns', 'runqueue_delay')}, indent=2))


if __name__ == '__main__':
    main()
