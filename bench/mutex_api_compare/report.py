#!/usr/bin/env python3
"""Keep source, caller and JIT classes separate in public-mutex comparisons."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
from statistics import median


def execution_class(row):
    if row['arm'] != 'kdlock':
        return 'NOT_APPLICABLE'
    if 'jit_bodies' not in row:
        return 'UNMEASURED'
    entries = row['jit_bodies']
    if row['comparison_workload'] in ('c01', 'c08', 'rcuht'):
        return 'WITNESSED_JIT' if entries else 'NO_JIT'
    completed = row.get('jit_completions')
    if completed is None:
        return 'UNMEASURED'
    if not 0 <= completed <= entries:
        raise ValueError('invalid entry/completion counters')
    return 'RETURNED_JIT' if completed else 'PARTIAL_JIT' if entries else 'NO_JIT'


def accepted(row):
    if (row.get('execution_status') != 'OK' or not row.get('drained')
            or row.get('cleanup_error')
            or any(row.get(k) for k in ('diagnostic', 'pmu', 'perf_record'))):
        return False
    m = row.get('measurement', {})
    workers = m.get('workers', [])
    synthetic = row['comparison_workload'] in ('c01', 'c08', 'rcuht')
    correct = (m.get('complete') and m.get('data_ok')) if synthetic else m.get('ok')
    return (bool(correct) and m.get('completed', 0) > 0 and m.get('wall_ns', 0) > 0
            and len(workers) == row['threads']
            and [w.get('cpu') for w in workers] == row['cpus']
            and sum(w.get('completed', 0) for w in workers) == m['completed']
            and all(w.get('completed', 0) > 0 and w.get('error') == 0
                    and w.get('observed_cpu') == w['cpu'] for w in workers))


def summarize(records):
    grouped = defaultdict(list)
    identities = {}
    geometries = {}
    for row in records:
        key = (row['comparison_workload'], row['threads'], row['comparison_arm'])
        geometry = tuple(json.dumps(row.get(k), sort_keys=True) for k in (
            'cpus', 'cpu_nodes', 'collector_cpu', 'collector_shared',
            'duration_ms', 'peak_window_ms', 'peak_settle_ms', 'sample_ms',
            'warmup_iterations_per_worker', 'warmup', 'warmup_ms',
            'entries', 'value_size', 'file_descriptions', 'syscalls_per_op',
            'kernel_identity', 'topology_identity'))
        if key[:2] in geometries and geometry != geometries[key[:2]]:
            raise ValueError('worker/timing/workload geometry differs across arms')
        geometries[key[:2]] = geometry
        identity = tuple(json.dumps(row.get(k), sort_keys=True) for k in (
            'source_identity', 'caller_shell', 'cookie_storage', 'cpus', 'cpu_nodes',
            'collector_cpu', 'collector_shared', 'duration_ms', 'peak_window_ms',
            'peak_settle_ms', 'sample_ms', 'kernel_identity', 'topology_identity'))
        if key in identities and identity != identities[key]:
            raise ValueError('source/caller/placement changed between repetitions')
        identities[key] = identity
        grouped[key + (execution_class(row),)].append(row)
    summary = []
    for key, rows in sorted(grouped.items()):
        good = [row for row in rows if accepted(row)]
        repeats = [row['repeat'] for row in good]
        if len(set(repeats)) != len(repeats):
            raise ValueError('duplicate accepted repetition')
        whole = [r['measurement']['completed'] * 1e9 / r['measurement']['wall_ns']
                 for r in good]
        peak = [r['measurement']['peak']['throughput_ops_s'] for r in good]
        summary.append(dict(workload=key[0], threads=key[1], arm=key[2],
            execution_class=key[3], planned=len(rows), accepted=len(good),
            comparable_three_repeats=sorted(repeats) == [0, 1, 2],
            whole_min=min(whole) if whole else None,
            whole_median=median(whole) if whole else None,
            whole_max=max(whole) if whole else None,
            whole_spread_pct=100 * (max(whole)-min(whole))/median(whole) if whole else None,
            peak_max=max(peak) if peak else None, p95_latency_ns=None,
            latency_status='UNMEASURED; inverse throughput is not latency',
            source_identity=rows[0]['source_identity'],
            caller_shell=rows[0]['caller_shell'], cookie_storage=rows[0]['cookie_storage']))
    return summary


def comparisons(summary):
    by_point = defaultdict(list)
    for row in summary:
        by_point[row['workload'], row['threads']].append(row)
    result = []
    for (workload, threads), rows in sorted(by_point.items()):
        public = [r for r in rows if r['arm'] == 'public-kd']
        for candidate in public:
            for arm in ('baseline-kd', 'native', 'tclock'):
                controls = [r for r in rows if r['arm'] == arm
                            and (arm != 'baseline-kd' or
                                 r['execution_class'] == candidate['execution_class'])]
                complete = (candidate['comparable_three_repeats'] and len(controls) == 1
                            and controls[0]['comparable_three_repeats'])
                control = controls[0] if len(controls) == 1 else None
                ratio = (candidate['whole_median'] / control['whole_median']
                         if complete else None)
                # Three repeats do not establish statistical significance.
                # Expose observed ranges alongside the provisional 5% rule.
                separated = (candidate['whole_max'] < 0.95 * control['whole_min']
                             if complete else None)
                result.append(dict(workload=workload, threads=threads,
                    public_execution_class=candidate['execution_class'], comparator=arm,
                    whole_median_ratio=ratio, loss_exceeds_observed_range=separated,
                    throughput_gate=('INCOMPLETE' if not complete else
                        'MEETS_PROVISIONAL_5_PERCENT' if ratio >= .95 else
                        'LOSS_BEYOND_OBSERVED_RANGE' if separated else
                        'LOSS_NOT_SEPARATED_AT_5_PERCENT_MARGIN'),
                    p95_latency_gate='UNMEASURED',
                    overall_acceptance='OPEN',
                    gate_origin='provisional coordinator-proposed 5% throughput / 10% p95; '
                                'not an established project-wide acceptance rule'))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('matrix', type=Path)
    args = parser.parse_args()
    records = json.loads((args.matrix/'records.json').read_text())
    rows = summarize(records)
    for name, values in (('summary', rows), ('comparisons', comparisons(rows))):
        (args.matrix/(name+'.json')).write_text(json.dumps(values, indent=2)+'\n')
        if values:
            with (args.matrix/(name+'.csv')).open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(values[0]), lineterminator='\n')
                writer.writeheader()
                writer.writerows(values)
    print(json.dumps(dict(sessions=len(records), accepted=sum(accepted(r) for r in records),
                          comparison_rows=len(comparisons(rows)),
                          overall_acceptance='OPEN; p95 latency is unmeasured')))


if __name__ == '__main__':
    main()
