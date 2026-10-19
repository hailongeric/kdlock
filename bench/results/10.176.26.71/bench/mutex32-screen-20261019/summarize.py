#!/usr/bin/env python3
"""Summarize finished mutex32 maintained-runner records; never run workloads.

Run in the VM after both collections finish. Inputs are read-only. Failed and
unscored sessions remain visible, but only maintained score-eligible sessions
enter rates, ratios, returned-JIT shares and hash outcome aggregates.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from statistics import median


ARMS = ('native', 'tclock', 'kdlock')
THREADS = (1, 8, 32, 60)
CASES = (('cacheline', 1, 'c01'), ('cacheline', 8, 'c08'), ('rcuht', 0, 'rcuht'))
REPEATS = 3
COMMON_IDENTITY = (
    'lock_kind', 'scenario', 'api_mode', 'iterations', 'cpus', 'cpu_nodes',
    'duration_ms', 'peak_window_ms', 'peak_settle_ms', 'sample_ms',
    'collector_cpu', 'collector_shared', 'warmup_policy',
    'warmup_iterations_per_worker', 'warmup_pause_seconds', 'measurement_mode',
)
BACKEND_IDENTITY = (
    'caller_abi', 'caller_shell', 'cookie_storage', 'hotlock_mode',
    'cpu_heat_policy', 'spin_contention_pct', 'spin_entry_ratio_limit',
    'spin_delegate', 'numa_policy', 'delegation_batch_limit', 'spin_prefetch',
    'kd_provider_ubsan', 'diagnostic', 'pmu', 'perf_record',
)
LAYOUT_IDENTITY = ('version', 'line_bytes', 'slots', 'lock_bytes', 'lock_kind',
                   'workload', 'buckets', 'entries', 'key_range', 'resched')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def stats(values):
    if not values:
        return dict(min=None, median=None, max=None, spread_pct=None)
    mid = median(values)
    return dict(min=min(values), median=mid, max=max(values),
                spread_pct=100 * (max(values) - min(values)) / mid
                if len(values) > 1 and mid else None)


def identity(records, keys, label):
    result = {}
    for key in keys:
        present = [r[key] for r in records if key in r]
        values = {json.dumps(value, sort_keys=True) for value in present}
        require(len(values) <= 1, f'{label}: mixed identity field {key}')
        result[key] = present[0] if present else None
    return result


def hash_mix(record, strict):
    if record.get('workload') != 'rcuht':
        return None
    m = record.get('measurement', {})
    before, after = m.get('before'), m.get('after')
    if not (isinstance(before, list) and isinstance(after, list)
            and len(before) == len(after) == 16):
        require(not strict, f'{record["name"]}: missing hash outcome counters')
        return None
    delta = [a - b for a, b in zip(after, before)]
    valid = (m.get('hash_integrity_ok') is True and min(delta) >= 0
             and delta[0] == sum(delta[1:4]) == m.get('completed')
             and before[0] == sum(before[1:4]) and after[0] == sum(after[1:4])
             and not any(before[4:] + after[4:]))
    require(not strict or valid, f'{record["name"]}: invalid hash outcome mix')
    return dict(valid=valid, operations=delta[0], moves=delta[1],
                conflicts=delta[2], misses=delta[3])


def measured_parks(record, strict):
    before = record.get('tclock_before', {})
    after = record.get('tclock_after', {})
    # Current mutex provider calls successful parking CAS transitions "parks".
    # Keep the key explicit; these transitions are not context-switch counts.
    keys = [key for key in ('parks', 'park_success') if key in before or key in after]
    if not keys:
        return None, None
    require(len(keys) == 1, f'{record["name"]}: ambiguous park counter')
    key = keys[0]
    valid = (type(before.get(key)) is int and type(after.get(key)) is int
             and 0 <= before[key] <= after[key])
    require(not strict or valid, f'{record["name"]}: invalid measured park counter')
    return key, after[key] - before[key] if valid else None


def session(record, source):
    m = record.get('measurement', {})
    # Same eligibility as tclock_compare/run.py::report and summarize.valid.
    valid = (record.get('execution_status') == 'OK' and record.get('drained') is True
             and m.get('data_ok') is True and m.get('complete') is True)
    eligible = valid and not any(record.get(k, False)
                                for k in ('diagnostic', 'pmu', 'perf_record'))
    require(type(record.get('score_eligible')) is bool,
            f'{record["name"]}: expected finished maintained records.json')
    require(record['score_eligible'] == eligible,
            f'{record["name"]}: maintained eligibility disagrees')
    completed, wall = m.get('completed'), m.get('wall_ns')
    observed_whole = completed * 1000 / wall if completed and wall and wall > 0 else None
    peak = (m.get('peak') or {}).get('throughput_ops_s')
    observed_peak = peak / 1e6 if peak is not None else None
    bodies = record.get('jit_bodies')
    observed_share = bodies / completed if bodies is not None and completed else None
    delegated = record.get('delegated_bodies')
    delegation_share = delegated / completed if delegated is not None and completed else None
    park_counter_key, parks = measured_parks(record, eligible)
    if eligible:
        require(observed_whole is not None and observed_whole > 0,
                f'{record["name"]}: valid session has no whole rate')
        require(math.isclose(record['whole_throughput_ops_s'] / 1e6,
                             observed_whole, rel_tol=1e-12),
                f'{record["name"]}: stored whole rate differs')
        require(not record.get('duration_ms') or observed_peak and observed_peak > 0,
                f'{record["name"]}: timed eligible session has no accepted peak')
        require(type(bodies) is int and 0 <= bodies <= completed,
                f'{record["name"]}: invalid measured returned-body count')
        require(type(delegated) is int and 0 <= delegated <= completed,
                f'{record["name"]}: invalid measured delegated-body count')
        if record['arm'] == 'tclock':
            before, after = record.get('tclock_before', {}), record.get('tclock_after', {})
            require(type(before.get('delegated')) is int
                    and type(after.get('delegated')) is int
                    and after['delegated'] - before['delegated'] == delegated,
                    f'{record["name"]}: TCLock delegated-body delta differs')
            require(record['threads'] == 1 or record.get('delegation_status') == 'PASS'
                    and delegated > 0,
                    f'{record["name"]}: contended eligible TCLock lacks delegation')
        else:
            require(delegated == bodies,
                    f'{record["name"]}: native/KD delegation count differs from returned JIT')
        if record['arm'] == 'kdlock' and record['threads'] > 1:
            require(record.get('jit_acceptance') == 'PASS' and bodies > 0,
                    f'{record["name"]}: contended eligible KD lacks returned JIT')
    return dict(name=record['name'], input_directory=source, arm=record['arm'],
                workload=record['workload'], cachelines=record['cachelines'],
                threads=record['threads'], repeat=record['repeat'],
                execution_status=record.get('execution_status', 'NOT_RUN'),
                score_eligible=eligible, drained=record.get('drained', False),
                data_ok=m.get('data_ok'), complete=m.get('complete'),
                diagnostic=record.get('diagnostic', False),
                pmu=record.get('pmu', False), perf_record=record.get('perf_record', False),
                error=record.get('error'), cleanup_error=record.get('cleanup_error'),
                jit_acceptance=record.get('jit_acceptance'), jit_status=record.get('jit_status'),
                completed=completed, wall_ns=wall, jit_bodies=bodies,
                measured_returned_jit_share=observed_share,
                delegated_bodies=delegated, delegation_status=record.get('delegation_status'),
                measured_delegation_share=delegation_share,
                park_counter_key=park_counter_key, measured_park_successes=parks,
                observed_whole_mops_unscored_if_ineligible=observed_whole,
                observed_peak_mops_unscored_if_ineligible=observed_peak,
                whole_mops=observed_whole if eligible else None,
                peak_mops=observed_peak if eligible else None,
                peak_window=m.get('peak'), hash_outcomes=hash_mix(record, eligible))


def backend_group(raw, sessions, label):
    good = [s for s in sessions if s['score_eligible']]
    whole = stats([s['whole_mops'] for s in good])
    peaks = [s for s in good if s['peak_mops'] is not None]
    peak = stats([s['peak_mops'] for s in peaks])
    best = max(peaks, key=lambda s: s['peak_mops']) if peaks else None
    completed = sum(s['completed'] for s in good)
    returned = sum(s['jit_bodies'] for s in good)
    delegated = sum(s['delegated_bodies'] for s in good)
    park_sessions = [s for s in good if s['measured_park_successes'] is not None]
    parks = sum(s['measured_park_successes'] for s in park_sessions)
    park_operations = sum(s['completed'] for s in park_sessions)
    outcomes = [s['hash_outcomes'] for s in good if s['hash_outcomes'] is not None]
    mix = None
    if outcomes:
        mix = {k: sum(row[k] for row in outcomes)
               for k in ('operations', 'moves', 'conflicts', 'misses')}
        mix.update({key + '_share': mix[key] / mix['operations']
                    for key in ('moves', 'conflicts', 'misses')})
    return dict(arm=raw[0]['arm'], valid=len(good), planned=REPEATS,
                valid_n_of_3=f'{len(good)}/{REPEATS}',
                status='COMPLETE' if len(good) == REPEATS else 'PARTIAL' if good else 'NO_VALID',
                execution_statuses=dict(sorted(Counter(s['execution_status'] for s in sessions).items())),
                jit_acceptance_statuses=dict(sorted(Counter(str(s['jit_acceptance']) for s in sessions).items())),
                delegation_statuses=dict(sorted(Counter(str(s['delegation_status']) for s in sessions).items())),
                identity=identity(raw, BACKEND_IDENTITY, label),
                layout=identity([r.get('layout', {}) for r in raw], LAYOUT_IDENTITY, label),
                whole_mops=whole, peak_mops=peak,
                best_peak_session=best['name'] if best else None,
                best_peak_window=best['peak_window'] if best else None,
                eligible_measured_operations=completed, eligible_returned_jit_bodies=returned,
                measured_returned_jit_share=returned / completed if completed else None,
                session_returned_jit_share=stats([s['measured_returned_jit_share'] for s in good]),
                actual_jit_sessions=sum(s['jit_bodies'] > 0 for s in good),
                eligible_delegated_bodies=delegated,
                measured_delegation_share=delegated / completed if completed else None,
                session_delegation_share=stats([s['measured_delegation_share'] for s in good]),
                actual_delegation_sessions=sum(s['delegated_bodies'] > 0 for s in good),
                park_counter_keys=sorted({s['park_counter_key'] for s in park_sessions}),
                park_measured_sessions=len(park_sessions),
                eligible_measured_park_successes=parks if park_sessions else None,
                measured_park_successes_per_operation=parks / park_operations if park_operations else None,
                hash_outcomes=mix, sessions=sessions)


def ratio(numerator, denominator):
    return numerator / denominator if numerator is not None and denominator else None


def write_csv(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, sort_keys=True)
                             if isinstance(value, (dict, list)) else value
                             for key, value in row.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=Path(
        '/root/kdlock-evidence/10.176.26.71/bench/mutex32-screen-20261019'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--host-receipt', type=Path, action='append', default=[])
    args = parser.parse_args()
    out = args.output or args.base
    records, provenance = {}, []
    for directory, expected in (('cacheline', 72), ('rcuht', 36)):
        folder = args.base / directory
        path = folder / 'records.json'
        data = load(path)
        require(isinstance(data, list) and len(data) == expected,
                f'{path}: expected {expected} planned records including failed/not-run entries')
        for record in data:
            key = (record['workload'], record['cachelines'], record['threads'], record['arm'], record['repeat'])
            require(record.get('lock_kind') == 'mutex' and key not in records,
                    f'{path}: unexpected lock kind or duplicate session {key}')
            records[key] = (record, directory)
        files = [path] + [folder / name for name in
                         ('plan.json', 'source-sha256.json', 'binary-sha256.json', 'environment.json')
                         if (folder / name).is_file()]
        provenance.append(dict(directory=str(folder), files={str(p): digest(p) for p in files}))
    rows, flat_rows, groups, all_sessions = [], [], [], []
    for workload, lines, case in CASES:
        for threads in THREADS:
            raw_all, backends = [], {}
            flat = dict(case=case, workload=workload, cachelines=lines, threads=threads)
            for arm in ARMS:
                raw, summaries = [], []
                for repeat in range(REPEATS):
                    record, source = records.pop((workload, lines, threads, arm, repeat))
                    raw.append(record)
                    summaries.append(session(record, source))
                label = f'{case}/{threads}/{arm}'
                identity(raw, COMMON_IDENTITY, label)
                group = backend_group(raw, summaries, label)
                backends[arm] = group
                raw_all.extend(raw)
                all_sessions.extend(summaries)
                group_flat = dict(case=case, workload=workload, cachelines=lines, threads=threads)
                for key in ('arm', 'valid', 'planned', 'valid_n_of_3', 'status', 'execution_statuses',
                            'jit_acceptance_statuses', 'delegation_statuses', 'eligible_measured_operations',
                            'eligible_returned_jit_bodies', 'measured_returned_jit_share',
                            'actual_jit_sessions', 'eligible_delegated_bodies',
                            'measured_delegation_share', 'actual_delegation_sessions',
                            'park_counter_keys', 'park_measured_sessions',
                            'eligible_measured_park_successes', 'measured_park_successes_per_operation',
                            'best_peak_session', 'hash_outcomes'):
                    group_flat[key] = group[key]
                for metric in ('whole_mops', 'peak_mops'):
                    for statistic, value in group[metric].items():
                        group_flat[f'{metric}_{statistic}'] = value
                group_flat['peak_mops_best'] = group['peak_mops']['max']
                groups.append(group_flat)
                flat.update({f'{arm}_{k}': v for k, v in group_flat.items()
                             if k not in ('case', 'workload', 'cachelines', 'threads', 'arm')})
            common = identity(raw_all, COMMON_IDENTITY, f'{case}/{threads}/controls')
            ratios = {}
            for control in ('native', 'tclock'):
                for metric, statistic, suffix in (
                        ('whole_mops', 'median', 'whole_median'),
                        ('peak_mops', 'median', 'peak_median'),
                        ('peak_mops', 'max', 'peak_best')):
                    key = f'kd_over_{control}_{suffix}'
                    ratios[key] = ratio(backends['kdlock'][metric][statistic],
                                        backends[control][metric][statistic])
            flat.update(ratios)
            row_status = 'COMPLETE' if all(b['valid'] == REPEATS for b in backends.values()) else 'INCOMPLETE'
            flat['row_status'] = row_status
            rows.append(dict(case=case, workload=workload, cachelines=lines, threads=threads,
                             status=row_status, identity=common, backends=backends, ratios=ratios))
            flat_rows.append(flat)
    require(not records, f'unexpected remaining sessions: {list(records)}')
    host_receipts = []
    for path in args.host_receipt:
        content = path.read_text()
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            pass
        host_receipts.append(dict(path=str(path), sha256=digest(path), content=content))
    result = dict(schema=1, generated_utc=datetime.now(timezone.utc).isoformat(),
                  source_base=str(args.base), script_sha256=digest(Path(__file__)),
                  comparison_rows=len(rows), backend_groups=len(groups), planned_sessions=len(all_sessions),
                  eligible_sessions=sum(s['score_eligible'] for s in all_sessions),
                  unscored_sessions=[s for s in all_sessions if not s['score_eligible']],
                  primary_metric='median whole-run throughput in million completed operations/second',
                  spread_definition='100 * (maximum - minimum) / median over eligible repeats; null for n<2',
                  ratios_definition='KD eligible median/median or best-peak/best-peak, as named; not paired-repeat ratios',
                  jit_share_definition='sum of measured returned JIT bodies / sum of measured operations across eligible repeats; not a peak-window share',
                  delegation_share_definition='sum of measured delegated bodies / sum of measured operations across eligible repeats; TCLock mutex counts native delegated bodies, KD counts returned JIT bodies, native counts zero',
                  parks_definition='TCLock measured after-minus-before parks counter counts successful waiter parking CAS transitions; it is neither sleep duration nor context-switch count. Null means unavailable. Aggregates include only eligible sessions with measured counters.',
                  eligibility='maintained score_eligible checked against OK, drained, complete, data_ok and no diagnostic/PMU/perf flags; failed and unscored sessions retained',
                  single_worker_note='KD one-worker NO_JIT remains eligible only when maintained execution_status is OK; it is not evidence of delegation',
                  host_placement_note='Host preflight reported imperfect actual memory placement despite NUMA binding (about 7.94% off node for bind:0 and 3.42% for bind:1); consult retained pre/post host receipts. CPU placement and binding policy alone do not prove page placement.',
                  provenance=provenance, host_receipts=host_receipts, rows=rows)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'comparison.json').write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    write_csv(out / 'comparison.csv', flat_rows)
    write_csv(out / 'backend-groups.csv', groups)
    write_csv(out / 'sessions.csv', [{k: v for k, v in s.items() if k != 'peak_window'} for s in all_sessions])
    print(json.dumps(dict(output=str(out), rows=len(rows), backend_groups=len(groups),
                          sessions=len(all_sessions), eligible=result['eligible_sessions'])))


if __name__ == '__main__':
    main()
