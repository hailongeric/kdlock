#!/usr/bin/env python3
"""Offline audit of frozen c01 mutex protocol experiments."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import re
import statistics
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT / 'bench/tclock_compare'))
import mutex_study as study
from bench_runtime import digest, require, FAULT

# Historical experiment identity must survive removal of rejected runner flags.
POLICY_FIELDS = ('mutex_entry_ratio_limit', 'mutex_routing', 'mutex_acceptance',
                 'mutex_frame_reuse', 'mutex_native_epoch_ms', 'mutex_native_probe_ms',
                 'mutex_lazy_save', 'mutex_node_locality', 'mutex_preflight',
                 'mutex_native_epoch_cache', 'mutex_native_epoch_cross_node')


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def write_csv(path, rows):
    with path.open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def audit(path, post_work_rounds):
    rows = study.load_run(path, post_work_rounds)
    for row in rows:
        log = (path / row['name'] / 'kernel.log').read_text()
        require(not FAULT.search(log), 'kernel fault: ' + str(path))
        if row['arm'] != 'kdlock':
            continue
        lines = [line for line in log.splitlines() if 'kd_mutex stats:' in line]
        require(len(lines) == 1, 'missing mutex drain counters')
        counts = {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', lines[0])}
        require(counts['active_waiters'] == counts['reserved_nodes'] == counts['frame_failure'] == 0,
                'outstanding mutex resources or frame failure')
        require(counts['origin_acquires'] == counts['origin_releases'], 'native owner imbalance')
        params = row['parameters']
        for key, default in (('mutex_frame_reuse', False), ('mutex_native_epoch_cache', False),
                             ('mutex_native_epoch_cross_node', False),
                             ('mutex_native_epoch_ms', 0),
                             ('mutex_native_probe_ms', 1)):
            expected = row.get(key, default)
            actual = params.get(key, 'N' if default is False else str(default))
            require(actual == ('Y' if expected else 'N') if default is False else
                    int(actual) == expected, 'policy identity mismatch: ' + key)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--series', nargs='+', required=True)
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--post-work-rounds', type=int, default=64)
    args = parser.parse_args()
    args.raw = args.raw.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    runs = {name: audit(args.raw / name, args.post_work_rounds) for name in args.series}
    require('baseline' in runs, 'baseline required')
    stats, samples, coverage, decisions = [], [], {}, {}
    for name, rows in runs.items():
        grouped = defaultdict(list)
        for row in rows:
            grouped[row['threads'], row['arm']].append(row)
            measurement = row['measurement']
            shares = [worker['completed'] / measurement['completed'] for worker in measurement['workers']]
            samples.append(dict(series=name, post_work_rounds=args.post_work_rounds,
                sample=row['name'], threads=row['threads'],
                arm=row['arm'], repeat=row['repeat'],
                execution_class=row.get('execution_class', row.get('jit_status')),
                whole_mops=measurement['completed'] * 1000 / measurement['wall_ns'],
                peak_mops=measurement['peak']['throughput_ops_s'] / 1e6,
                worker_cpu_ns_per_op=measurement['worker_cpu_ns'] / measurement['completed'],
                min_worker_share=min(shares), max_worker_share=max(shares),
                returned_jit=row.get('jit_bodies', 0), delegation_share=row.get('delegation_share'),
                result_parks=row.get('mutex_wait_delta', {}).get('result_schedule_calls'),
                gate_waits=row.get('mutex_wait_delta', {}).get('gate_wait_calls'),
                native_epochs=(row.get('mutex_epoch_delta') or [None, None, None])[0],
                remote_vetoes=(row.get('mutex_epoch_delta') or [None, None, None])[2],
                drained=row['drained']))
        for (threads, arm), cohort in sorted(grouped.items()):
            metric = study.metrics(cohort)
            stats.append(dict(series=name, post_work_rounds=args.post_work_rounds,
                threads=threads, arm=arm,
                whole_min_mops=min(metric['whole_rates']) / 1e6,
                whole_median_mops=metric['median_whole'] / 1e6,
                whole_max_mops=max(metric['whole_rates']) / 1e6,
                best_peak_mops=metric['best_peak'] / 1e6,
                whole_spread_pct=metric['whole_spread_pct'],
                peak_spread_pct=metric['peak_spread_pct'],
                worker_share_min=metric['worker_share_min'],
                worker_share_max=metric['worker_share_max'],
                median_worker_cpu_ns_per_op=statistics.median(metric['worker_cpu_ns_per_op']),
                returned_jit=sum(metric['jit_bodies']),
                median_jit_share=statistics.median(metric['jit_shares'])))
        if name != 'baseline':
            decisions[name] = study.evaluate(runs['baseline'], rows)
        sources = json.loads((args.raw / name / 'source-sha256.json').read_text())
        coverage[name] = dict(post_work_rounds=args.post_work_rounds,
            samples=len(rows), counts=sorted({r['threads'] for r in rows}),
            source_manifest_sha256=digest(args.raw / name / 'source-sha256.json'),
            binary_manifest_sha256=digest(args.raw / name / 'binary-sha256.json'),
            policy={key: sorted({str(r.get(key)) for r in rows if r['arm'] == 'kdlock'})
                    for key in POLICY_FIELDS},
            provider_files={key: value for key, value in sources.items()
                            if key.startswith(('include/', 'kernel_module/'))})
    write_csv(args.out / 'statistics.csv', stats)
    write_csv(args.out / 'samples.csv', samples)
    write_json(args.out / 'coverage.json', coverage)
    write_json(args.out / 'acceptance.json', decisions)
    write_json(args.out / 'artifacts.json', {str(p.relative_to(ROOT)): dict(
        sha256=digest(p), bytes=p.stat().st_size) for p in sorted(args.raw.glob('*.tar.gz'))})
    print(json.dumps(dict(samples=len(samples), acceptance=decisions), indent=2))


if __name__ == '__main__':
    main()
