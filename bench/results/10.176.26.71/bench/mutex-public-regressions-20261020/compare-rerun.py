#!/usr/bin/env python3
"""Recompute separate original/replay summaries from inert retained JSON."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import median

REGRESSIONS = {('c08', 3), ('c08', 4), ('c08', 5), ('pipebytes', 3),
               ('pipebytes', 5), ('pipecap', 5), ('rcuht', 2)}
CLASS_GAPS = {('c08', 2), ('pipebytes', 4), ('pipecap', 4)}
ARMS = ('baseline-kd', 'public-kd', 'native', 'tclock')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--records', type=Path, required=True)
    args = parser.parse_args()
    helper = args.repo/'bench/mutex_api_compare/report.py'
    assert digest(helper) == 'ae4a9272ac7fae6130fd8bc5f99e98f20ffd1e115ed29322b0bf962ff8b6b39c'
    spec = importlib.util.spec_from_file_location('maintained_comparison', helper)
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    original_path = args.report/'original-selected-records.json'
    selection = json.loads((args.report/'selection.json').read_text())
    assert digest(original_path) == selection['selection_sha256']
    original = json.loads(original_path.read_text())
    replay = json.loads(args.records.read_text())
    assert len(original) == len(replay) == 120
    original_by_name = {r['name']: r for r in original}
    assert len(original_by_name) == 120 and {r['name'] for r in replay} == set(original_by_name)
    assert len({r['name'] for r in replay}) == 120
    binding = ('comparison_workload', 'threads', 'repeat', 'comparison_arm', 'arm',
               'source_identity', 'caller_shell', 'cookie_storage', 'cpus', 'cpu_nodes',
               'collector_cpu', 'collector_shared', 'duration_ms', 'peak_window_ms',
               'peak_settle_ms', 'sample_ms', 'warmup_iterations_per_worker', 'warmup',
               'warmup_ms', 'warmup_policy', 'warmup_pause_seconds', 'entries', 'value_size',
               'file_descriptions', 'syscalls_per_op', 'post_work_rounds', 'numa_policy',
               'spin_entry_ratio_limit', 'spin_prefetch', 'delegation_batch_limit',
               'kd_provider_ubsan', 'diagnostic', 'pmu', 'perf_record')
    for row in replay:
        old = original_by_name[row['name']]
        assert all(row.get(key) == old.get(key) for key in binding), row['name']
    summaries = {}
    comparisons = {}
    for collection, records in (('original', original), ('replay', replay)):
        summaries[collection] = report.summarize(records)
        comparisons[collection] = report.comparisons(summaries[collection])
        save(args.report/(collection+'-summary.json'), summaries[collection])
        save(args.report/(collection+'-comparisons.json'), comparisons[collection])
    points = []
    for workload, threads in sorted(REGRESSIONS | CLASS_GAPS):
        point = dict(workload=workload, threads=threads,
                     original_issue='separated_loss' if (workload, threads) in REGRESSIONS
                                    else 'incomparable_execution_classes',
                     collections={}, disposition='UNRESOLVED; no causal fix or latency validation')
        for collection, records in (('original', original), ('replay', replay)):
            chosen = [r for r in records
                      if (r['comparison_workload'], r['threads']) == (workload, threads)]
            assert len(chosen) == 12
            samples = {}
            for arm in ARMS:
                rows = sorted((r for r in chosen if r['comparison_arm'] == arm),
                              key=lambda r: r['repeat'])
                assert [r['repeat'] for r in rows] == [0, 1, 2]
                samples[arm] = [dict(name=r['name'], repeat=r['repeat'],
                    execution_status=r['execution_status'], accepted=report.accepted(r),
                    drained=r.get('drained'), execution_class=report.execution_class(r),
                    jit_bodies=r.get('jit_bodies'), jit_completions=r.get('jit_completions'),
                    whole_ops_s=(r['measurement']['completed']*1e9/r['measurement']['wall_ns']
                                 if report.accepted(r) else None),
                    evidence_path=r.get('evidence_path')) for r in rows]
            paired = []
            for public, outer in zip(samples['public-kd'], samples['baseline-kd']):
                comparable = (public['accepted'] and outer['accepted'] and
                              public['execution_class'] == outer['execution_class'])
                paired.append(dict(repeat=public['repeat'], comparable=comparable,
                    public_class=public['execution_class'], outer_class=outer['execution_class'],
                    ratio=public['whole_ops_s']/outer['whole_ops_s'] if comparable else None))
            score = [r for r in comparisons[collection]
                     if (r['workload'], r['threads'], r['comparator']) ==
                        (workload, threads, 'baseline-kd')]
            groups = [r for r in summaries[collection]
                      if (r['workload'], r['threads']) == (workload, threads)]
            complete = len(score) == 1 and score[0]['whole_median_ratio'] is not None
            matched_ratios = [p['ratio'] for p in paired] if complete else []
            point['collections'][collection] = dict(samples=samples, groups=groups,
                outer_comparisons=score, paired_ratios=paired,
                paired_ratio_range=([min(matched_ratios), median(matched_ratios), max(matched_ratios)]
                                    if matched_ratios else None),
                complete_same_class_comparison=complete)
        current = point['collections']['replay']
        if not current['complete_same_class_comparison']:
            finding = 'INCOMPARABLE_CLASSES_OR_INVALID_REPETITION'
        else:
            score = current['outer_comparisons'][0]
            finding = ('SEPARATED_LOSS_REPRODUCED' if score['loss_exceeds_observed_range'] else
                       'MEDIAN_LOSS_WITH_OVERLAPPING_RANGES' if score['whole_median_ratio'] < .95 else
                       'ORIGINAL_LOSS_NOT_REPRODUCED_AT_PROVISIONAL_SCREEN')
        point['replay_finding'] = finding
        points.append(point)
    result = dict(original_run='mutex-public-20261020-r2',
        replay_run='mutex-public-20261020-replay-2',
        measured_collection='d21a1e3', records_sha256=digest(args.records),
        original_selection_sha256=digest(original_path), helper_sha256=digest(helper),
        script_sha256=digest(Path(__file__)), points=points,
        statuses=dict(Counter(r['execution_status'] for r in replay)),
        accepted=sum(report.accepted(r) for r in replay),
        drained=sum(bool(r.get('drained')) for r in replay),
        seven_regression_findings=dict(Counter(p['replay_finding'] for p in points
                                             if p['original_issue'] == 'separated_loss')),
        p95_latency='UNMEASURED', overall_acceptance='OPEN',
        limits='Separate three-repeat collections; observed ranges are not confidence intervals. '
               'No pooling across execution classes; no performance claim for later source revisions.')
    save(args.report/'investigation.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'points'}, indent=2))


if __name__ == '__main__':
    main()
