#!/usr/bin/env python3
"""Compare the isolated provider run while keeping every collection separate."""
import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

REGRESSIONS = {('c08', 3), ('c08', 4), ('c08', 5), ('pipebytes', 3),
               ('pipebytes', 5), ('pipecap', 5), ('rcuht', 2)}
BINDING = ('comparison_workload', 'threads', 'repeat', 'comparison_arm', 'arm',
    'source_identity', 'caller_shell', 'cookie_storage', 'cpus', 'cpu_nodes',
    'collector_cpu', 'collector_shared', 'duration_ms', 'peak_window_ms',
    'peak_settle_ms', 'sample_ms', 'warmup_iterations_per_worker', 'warmup',
    'warmup_ms', 'warmup_policy', 'warmup_pause_seconds', 'entries', 'value_size',
    'file_descriptions', 'syscalls_per_op', 'post_work_rounds', 'numa_policy',
    'spin_entry_ratio_limit', 'spin_prefetch', 'delegation_batch_limit',
    'kd_provider_ubsan', 'diagnostic', 'pmu', 'perf_record')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    helper = args.repo/'bench/mutex_api_compare/report.py'
    assert sha(helper) == 'ae4a9272ac7fae6130fd8bc5f99e98f20ffd1e115ed29322b0bf962ff8b6b39c'
    spec = importlib.util.spec_from_file_location('maintained_report', helper)
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    paths = {
        'mutex-public-20261020-r2': args.raw/'mutex-public-20261020-replay-2/extracted/analysis/original-selected-records.json',
        'mutex-public-20261020-replay-2': args.raw/'mutex-public-20261020-replay-2/extracted/records.json',
        'mutex-public-20261020-observed-1': args.raw/'mutex-public-20261020-observed-1/records.json',
        'mutex-public-20261020-inline-1': args.raw/'mutex-public-20261020-inline-1/records.json'}
    candidate_path = args.raw/'mutex-public-20261020-inline-inputs-1/candidate.json'
    assert sha(candidate_path) == 'd8b5b56daa3110cf3e276ca8c2198c2b05eda1bd79630210142163f57bc8f9ac'
    candidate = json.loads(candidate_path.read_text())
    assert sha(next(iter(paths.values()))) == '99e1c0127eaeb4e0de650a00034627134d99c9fffa6f3f6c72bf065e4832422b'
    records = {name: json.loads(path.read_text()) for name, path in paths.items()}
    original = {r['name']: r for r in next(iter(records.values()))}
    summaries, comparisons, samples = {}, {}, []
    for run, rows in records.items():
        assert len(rows) == len({r['name'] for r in rows}) == 120
        assert {r['name'] for r in rows} == set(original)
        for row in rows:
            derived = run.endswith('inline-1') and row['comparison_arm'] == 'public-kd'
            assert all(row.get(k) == original[row['name']].get(k)
                       for k in BINDING if not (derived and k == 'source_identity')), row['name']
            if derived:
                key = 'candidate-public/'+row['comparison_workload']
                assert row['source_identity'] == candidate['bundles'][key]['source_identity']
                assert row['provider_candidate'] == sha(candidate_path)
                assert row['provider_sha256'] == candidate['provider_sha256']
            assert row['execution_status'] in ('OK', 'NO_JIT') and row['drained']
            samples.append(dict(run=run, name=row['name'],
                instrumentation='host observer and outside-session clocks' if run.endswith('observed-1') else 'plain',
                workload=row['comparison_workload'], workers=row['threads'], repeat=row['repeat'],
                arm=row['comparison_arm'], execution_class=report.execution_class(row),
                score_eligible=report.accepted(row), source_identity=row['source_identity'],
                whole_ops_s=row['measurement']['completed']*1e9/row['measurement']['wall_ns'],
                jit_bodies=row.get('jit_bodies'), jit_completions=row.get('jit_completions'),
                evidence_path=row['evidence_path']))
        summaries[run] = report.summarize(rows)
        comparisons[run] = report.comparisons(summaries[run])
    points = []
    for workload, workers in sorted({(r['comparison_workload'], r['threads']) for r in original.values()}):
        point = dict(workload=workload, workers=workers,
            original_issue='separated_loss' if (workload, workers) in REGRESSIONS else 'class_gap',
            disposition='OPEN; report the isolated candidate separately; original-public '
                        'before/after changes are observational, not a simultaneous causal estimate',
            runs={})
        for run in records:
            group = [s for s in summaries[run] if (s['workload'], s['threads']) == (workload, workers)]
            outer = [s for s in comparisons[run] if (s['workload'], s['threads'], s['comparator']) ==
                     (workload, workers, 'baseline-kd')]
            point['runs'][run] = dict(groups=group, outer_comparisons=outer)
        points.append(point)
    args.output.mkdir(parents=True, exist_ok=True)
    save(args.output/'comparisons.json', dict(script_sha256=sha(Path(__file__)),
        helper_sha256=sha(helper), inputs={r: dict(path=str(p), sha256=sha(p)) for r, p in paths.items()},
        original_collection='d21a1e3', observed_scheduler='bc72912',
        candidate_scheduler='d1a976a', candidate_manifest_sha256=sha(candidate_path),
        candidate_provider_revision='d21 plus selected 003d71c entry patch',
        points=points,
        overall_acceptance='OPEN', p95_latency='UNMEASURED',
        limits='Three repeats per collection; do not pool runs, sources, execution classes or '
               'instrumentation. Observed ranges are not confidence intervals. The 5% screen '
               'is provisional and is not a user acceptance threshold.'))
    with (args.output/'per-repeat.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(samples[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(samples)
    for point in points:
        scores = point['runs']['mutex-public-20261020-inline-1']['outer_comparisons']
        print(point['workload'], point['workers'],
              [(r['whole_median_ratio'], r['loss_exceeds_observed_range']) for r in scores])


if __name__ == '__main__':
    main()
