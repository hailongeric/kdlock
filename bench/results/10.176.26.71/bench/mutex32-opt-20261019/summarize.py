#!/usr/bin/env python3
"""VM-only report of three frozen mutex implementations; never run workloads.

Read BASE/{compact-bucket,precompact-256,compact-rcu}/{profile,synthetic,seek,pipe}.
Write comparison.json, comparison.csv and sessions.csv to BASE unless --output
is supplied. Retain failed rows; only valid plain sessions enter timing groups.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
from statistics import median


ARMS = ('compact-bucket', 'precompact-256', 'compact-rcu')
GROUPS = ('profile', 'synthetic', 'seek', 'pipe')
FAULT = re.compile(r'BUG:|\bWARNING:|kernel panic|double fault|soft lockup|'
                   r'hard LOCKUP|unable to handle|general protection fault|'
                   r'Oops:|\[ERROR\]|\[KD_JIT\]\[ERROR\]|invariant_failures=[1-9]|'
                   r'runtime error:|KASAN:|UBSAN:', re.I)
IDENTITY_FIELDS = (
    'arm', 'lock_kind', 'caller_abi', 'caller_shell', 'cookie_storage', 'api_mode',
    'scenario', 'measurement_mode', 'cpus', 'cpu_nodes', 'collector_cpu',
    'collector_shared', 'duration_ms', 'peak_window_ms', 'peak_settle_ms',
    'sample_ms', 'warmup_policy', 'warmup_iterations_per_worker',
    'warmup_pause_seconds', 'warmup', 'warmup_ms', 'helper_waves', 'helper_cpus',
    'file_descriptions', 'entries', 'value_size', 'syscalls_per_op',
    'hotlock_mode', 'cpu_heat_policy', 'spin_entry_ratio_limit', 'spin_delegate',
    'spin_prefetch', 'numa_policy', 'delegation_batch_limit', 'kd_provider_ubsan',
    'jit_evidence_version', 'jit_completion_probe', 'entry_abi',
    'mutex_implementation', 'require_jit', 'diagnostic', 'perf_record', 'pmu',
)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def digest(path):
    with path.open('rb') as stream:
        h = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def unsigned(value):
    return type(value) is int and value >= 0


def same_number(a, b):
    return (type(a) in (int, float) and type(b) in (int, float)
            and math.isfinite(a) and math.isfinite(b)
            and math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-15))


def stats(values):
    mid = median(values) if values else None
    return dict(n=len(values), min=min(values) if values else None, median=mid,
                max=max(values) if values else None,
                spread_pct=100 * (max(values) - min(values)) / mid if mid else None)


def case(record, group):
    if group in ('synthetic', 'profile'):
        require(record.get('workload') == 'cacheline', 'unexpected synthetic workload')
        return f'c{record["cachelines"]:02d}'
    require(record.get('entries') == 16 and record.get('value_size') == 64,
            'unexpected API size')
    return f'{record["kind"]}-{record["query"]}-n16'


def expected(group):
    if group == 'profile':
        return {('c08', t, 0) for t in (8, 60)}
    cases = ('c01', 'c08') if group == 'synthetic' else (
        'seek-set-n16',) if group == 'seek' else ('pipebytes-query-n16',)
    return {(c, t, r) for c in cases for t in ((8,) if group == 'pipe' else (8, 60))
            for r in range(3)}


def collection(base, arm, group):
    folder = base / arm / group
    records = read(folder / 'records.json')
    require(isinstance(records, list), f'{folder}: records must be a list')
    keys = [(case(r, group), r['threads'], r['repeat']) for r in records]
    require(len(keys) == len(set(keys)) and set(keys) == expected(group),
            f'{folder}: missing, duplicate or unexpected planned sessions')
    require(len({r['name'] for r in records}) == len(records), f'{folder}: duplicate name')
    command_path = base / arm / (group + '-command.json')
    command = read(command_path)
    require(command.get('version') == arm and command.get('source_commit'),
            f'{folder}: missing source version receipt')
    source = read(folder / 'source-sha256.json')
    require(isinstance(source, dict) and source, f'{folder}: missing source manifest')
    for relative, sha in source.items():
        name = Path(relative)
        require(not name.is_absolute() and '..' not in name.parts,
                f'{folder}: unsafe snapshot path {relative}')
        require(digest(folder / 'source' / name) == sha,
                f'{folder}: frozen source differs: {relative}')
    source_id = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
    plan = read(folder / 'plan.json')
    require(len(plan) == len(records) and len({r['name'] for r in plan}) == len(plan),
            f'{folder}: invalid plan')
    planned = {r['name']: r for r in plan}
    for record in records:
        require(record['name'] in planned and all(record.get(k) == v
                for k, v in planned[record['name']].items()), f'{folder}: plan changed')
        if group in ('seek', 'pipe'):
            require(record['source_identity'] == source_id
                    and record['kernel_identity'] == digest(folder / 'kernel-identity.json')
                    and record['topology_identity'] == digest(folder / 'topology.txt'),
                    f'{folder}: source/kernel/topology binding differs')
    filenames = ('records.json', 'plan.json', 'source-sha256.json', 'environment.json',
                 'binary-sha256.json', 'binaries.json', 'build-configuration.json',
                 'kernel-identity.json', 'topology.txt', 'failure.json')
    provenance = dict(arm=arm, collection=group, source_commit=command['source_commit'],
                      source_identity=source_id, source_manifest=source,
                      verified_source_files=len(source), command=command,
                      command_sha256=digest(command_path),
                      input_sha256={n: digest(folder / n) for n in filenames if (folder / n).is_file()},
                      environment=read(folder / 'environment.json'))
    return records, folder, provenance


def kernel_diagnostics(path):
    if not path.is_file():
        return dict(present=False, faults=[], mutex_stats=None, mutex_tasks=None)
    lines = path.read_text(errors='replace').splitlines()
    result = dict(present=True, sha256=digest(path), faults=[l for l in lines if FAULT.search(l)])
    for name, marker in (('mutex_stats', 'kd_mutex stats:'), ('mutex_tasks', 'kd_mutex tasks:')):
        rows = [line for line in lines if marker in line]
        result[name + '_lines'] = rows
        result[name] = ({k: int(v) for k, v in re.findall(r'(\w+)=(-?\d+)', rows[-1])}
                        if rows else None)
    return result


def summarize_session(record, folder, provenance):
    arm, group = provenance['arm'], provenance['collection']
    name, m = record['name'], record.get('measurement', {})
    reasons = []

    def check(ok, message):
        if not ok:
            reasons.append(message)

    path = folder / name
    diagnostics = kernel_diagnostics(path / 'kernel.log')
    saved = path / 'session.json'
    check(saved.is_file(), 'missing session.json')
    if saved.is_file():
        check(all(record.get(k) == v for k, v in read(saved).items()), 'record differs from session.json')
    check(record.get('execution_status') == 'OK', 'execution not OK')
    check(record.get('drained') is True, 'drain not established')
    check(not record.get('error') and not record.get('cleanup_error'), 'recorded execution/cleanup error')
    check(diagnostics['present'] and not diagnostics['faults'], 'missing kernel log or runtime fault')
    check(record.get('retired') == dict(state=2, modules=0, frames=0, writers=0), 'source retirement differs')
    check(record.get('arm') == 'kdlock' and record.get('lock_kind') == 'mutex', 'unexpected backend/protocol')
    check(record.get('caller_abi') == 'clobber', 'caller ABI differs')
    check(record.get('cpus') == list(range(record['threads'])) and record.get('collector_cpu') == 63,
          'CPU placement differs')
    check((record.get('duration_ms'), record.get('peak_window_ms'), record.get('peak_settle_ms'),
           record.get('sample_ms')) == (2000, 300, 300, 10), 'measurement policy differs')
    count, wall = m.get('completed'), m.get('wall_ns')
    measurable = unsigned(count) and count > 0 and unsigned(wall) and wall > 0
    whole = count * 1000 / wall if measurable else None
    p = m.get('peak') or {}
    peak_valid = unsigned(p.get('completed')) and p.get('completed', 0) > 0 and unsigned(p.get('elapsed_ns')) and p.get('elapsed_ns', 0) > 0
    peak = p['completed'] * 1000 / p['elapsed_ns'] if peak_valid else None
    check(measurable and peak_valid, 'missing positive whole/peak measurement')
    check(same_number(record.get('whole_throughput_ops_s'), whole * 1e6 if whole else None), 'whole rate differs from counts/time')
    check(same_number(p.get('throughput_ops_s'), peak * 1e6 if peak else None), 'peak rate differs from counts/time')
    workers = m.get('workers', [])
    check(len(workers) == record['threads'] and [w.get('cpu') for w in workers] == record['cpus']
          and all(unsigned(w.get('completed')) and w['completed'] > 0
                  and w.get('error') == 0 and w.get('observed_cpu') == w['cpu'] for w in workers)
          and sum(w.get('completed', 0) for w in workers) == count, 'worker result/progress differs')
    check(m.get('collector_error') == 0 and m.get('collector_observed_cpu') == 63, 'collector failed/moved')
    check(m.get('duration_ns') == 2000000000 and m.get('wall_ns') == m.get('finished_ns', 0) - m.get('started_ns', 0), 'measurement interval differs')
    check(p.get('policy') == 'observed_full_cohort_earliest_endpoint'
          and p.get('requested_window_ns') == 300000000 and p.get('settle_ns') == 300000000
          and len(p.get('worker_completed', [])) == record['threads']
          and all(unsigned(v) and v > 0 for v in p.get('worker_completed', []))
          and sum(p.get('worker_completed', [])) == p.get('completed'), 'invalid full-cohort peak')
    bodies = record.get('jit_bodies')
    check(unsigned(bodies) and measurable and bodies <= count, 'invalid JIT body count')
    synthetic = group in ('synthetic', 'profile')
    completions = None if synthetic else record.get('jit_completions')
    jit_class = ('WITNESSED_JIT' if bodies else 'NO_JIT') if synthetic else (
        'RETURNED_JIT' if completions else 'PARTIAL_JIT' if bodies else 'NO_JIT')
    if synthetic:
        check(m.get('complete') is True and m.get('data_ok') is True, 'synthetic oracle failed')
        check(record.get('jit_acceptance') == 'PASS' and unsigned(bodies) and bodies > 0,
              'synthetic required JIT entry witness absent')
        check(unsigned(record.get('jit_before')) and unsigned(record.get('jit_after'))
              and record['jit_after'] - record['jit_before'] == bodies,
              'synthetic JIT counter delta differs')
        check(record.get('delegated_bodies') == bodies, 'synthetic delegated count differs')
        check(record.get('warmup_iterations_per_worker') == 48000, 'synthetic warmup differs')
        check(record.get('layout', {}).get('lock_bytes') == (256 if arm == 'precompact-256' else 32), 'lock layout differs')
        check(record.get('parameters', {}).get('bench_complete_probe') in ('N', '0'), 'synthetic completion instrumentation differs')
    else:
        check(m.get('ok') is True and m.get('phase') == 'measure', 'API oracle failed')
        check(record.get('redirected_calls') == count and record.get('jit_eligible_operations') == count, 'API call counts differ')
        check(unsigned(completions) and unsigned(bodies) and completions <= bodies, 'invalid API completion count')
        expected_jit = 'PASS' if completions else 'PARTIAL_JIT' if bodies else 'NO_JIT'
        check(record.get('jit_status') == expected_jit, 'API JIT classification differs')
        check(not record.get('require_jit') or bool(completions), 'API required returned JIT absent')
        check(record.get('jit_completion_probe') is True and record.get('jit_evidence_version') == 2
              and record.get('entry_abi') == 2, 'API completion instrumentation differs')
        check(record.get('warmup') == 48000 and record.get('warmup_ms') == 1000, 'API warmup differs')
        for endpoint in ('check-before', 'check-after'):
            oracle = path / (endpoint + '.json')
            check(oracle.is_file() and read(oracle).get('check') is True, 'missing/failed ' + endpoint)
    physical = diagnostics['mutex_stats'] or {}
    tasks = diagnostics['mutex_tasks'] or {}
    check({'active_waiters', 'reserved_nodes', 'frame_failure', 'origin_acquires',
           'origin_releases'} <= physical.keys() and 'active_tasks' in tasks,
          'missing final physical/task drain diagnostics')
    check(all(physical.get(k, 0) == 0 for k in ('active_waiters', 'reserved_nodes', 'frame_failure')),
          'nonzero physical drain/frame diagnostics')
    check(physical.get('origin_acquires') == physical.get('origin_releases'), 'physical acquisition/release imbalance')
    check(tasks.get('active_tasks', 0) == 0, 'active task records remain')
    profile = group == 'profile'
    profile_files = ('perf.data', 'perf-report.txt', 'perf-samples.txt', 'kallsyms', 'modules')
    if profile:
        check(record.get('diagnostic') is True and record.get('perf_record') is True
              and record.get('pmu') is False and record.get('score_eligible') is False, 'profile mode differs')
        check(all((path / filename).is_file() for filename in profile_files), 'incomplete profile evidence')
    else:
        check(not any(record.get(k, False) for k in ('diagnostic', 'perf_record', 'pmu')), 'plain run contains profiling')
        if synthetic:
            check(record.get('score_eligible') is True, 'maintained runner rejected timing')
    identity = {field: record.get(field) for field in IDENTITY_FIELDS}
    return dict(arm=arm, source_commit=provenance['source_commit'], source_identity=provenance['source_identity'],
                collection=group, workload=case(record, group), threads=record['threads'], repeat=record['repeat'],
                name=name, session_path=str(path.relative_to(folder.parents[1])),
                valid=not reasons, score_eligible=not reasons and not profile,
                rejection_reasons=reasons, execution_status=record.get('execution_status'),
                drained=record.get('drained'), jit_class=jit_class,
                jit_acceptance=record.get('jit_acceptance'), jit_status=record.get('jit_status'),
                completed=count, wall_ns=wall, jit_bodies=bodies, jit_completions=completions,
                body_counter_meaning='body_entries', completion_measured=not synthetic,
                measured_body_entry_share=bodies / count if measurable and unsigned(bodies) else None,
                measured_returned_jit_share=completions / count
                    if measurable and unsigned(completions) else None,
                raw_jit_share=record.get('jit_share'),
                observed_whole_mops=whole, observed_peak_mops=peak,
                whole_mops=whole if not reasons and not profile else None,
                peak_mops=peak if not reasons and not profile else None,
                identity=identity, whole_session_diagnostics=diagnostics,
                profile_sha256={n: digest(path / n) for n in profile_files if profile and (path / n).is_file()})


def aggregate(rows):
    valid = [r for r in rows if r['score_eligible']]
    classes = {r['jit_class'] for r in valid}
    # A change of execution class must remain visible, including a mixed pipe group.
    usable = valid if len(classes) <= 1 else []
    count = sum(r['completed'] for r in usable)
    completion_measured = rows[0]['completion_measured']
    returned = sum(r['jit_completions'] for r in usable) if completion_measured and usable else None
    identities = {json.dumps(r['identity'], sort_keys=True) for r in rows}
    require(len(identities) == 1, f'{rows[0]["workload"]}: mixed repeat identity')
    return dict(arm=rows[0]['arm'], source_commit=rows[0]['source_commit'],
                source_identity=rows[0]['source_identity'], collection=rows[0]['collection'],
                workload=rows[0]['workload'], threads=rows[0]['threads'], planned=3,
                valid=len(valid), repeats=[r['repeat'] for r in valid],
                status='MIXED_EXECUTION_CLASSES' if len(classes) > 1 else 'COMPLETE' if len(valid) == 3 else 'INCOMPLETE',
                jit_class=next(iter(classes)) if len(classes) == 1 else 'MIXED' if classes else 'UNSCORED',
                jit_classes=dict(Counter(r['jit_class'] for r in rows)),
                jit_acceptances=dict(Counter(str(r['jit_acceptance']) for r in rows)),
                jit_statuses=dict(Counter(str(r['jit_status']) for r in rows)),
                whole_mops=stats([r['whole_mops'] for r in usable]),
                peak_mops=stats([r['peak_mops'] for r in usable]),
                completed=count, measured_returned_jit_bodies=returned,
                measured_returned_jit_share=returned / count if count and returned is not None else None,
                measured_body_counter_meaning=rows[0]['body_counter_meaning'],
                measured_body_count=sum(r['jit_bodies'] for r in usable),
                measured_body_entry_share=sum(r['jit_bodies'] for r in usable) / count if count else None,
                completion_measured=completion_measured, measured_completion_count=returned,
                identity=rows[0]['identity'], sessions=[r['session_path'] for r in rows],
                whole_session_physical_counts=[r['whole_session_diagnostics']['mutex_stats'] for r in rows])


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows({k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v
                          for k, v in row.items()} for row in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    require(os.uname().release == '6.1.159-kdclobber2', 'run this report only in the recovery VM')
    provenance, sessions = [], []
    for arm in ARMS:
        for group in GROUPS:
            raw, folder, evidence = collection(args.base, arm, group)
            provenance.append(evidence)
            sessions.extend(summarize_session(r, folder, evidence) for r in raw)
        arm_inputs = [p for p in provenance if p['arm'] == arm]
        require(len({p['source_commit'] for p in arm_inputs}) == 1, f'{arm}: source labels mixed')
        common_sources = set.intersection(*(set(p['source_manifest']) for p in arm_inputs))
        require(common_sources and all(len({p['source_manifest'][f] for p in arm_inputs}) == 1
                                      for f in common_sources), f'{arm}: shared frozen sources changed')
    grouped = defaultdict(list)
    for row in sessions:
        if row['collection'] != 'profile':
            grouped[(row['arm'], row['workload'], row['threads'])].append(row)
    comparison = [aggregate(rows) for rows in grouped.values()]
    for workload, threads in {(r['workload'], r['threads']) for r in comparison}:
        matched = [r for r in comparison if (r['workload'], r['threads']) == (workload, threads)]
        require(len(matched) == 3 and len({json.dumps(r['identity'], sort_keys=True) for r in matched}) == 1,
                f'{workload}/{threads}: cross-arm call shell/settings differ')
        classes = {r['arm']: r['jit_class'] for r in matched}
        for row in matched:
            row['cross_arm_execution_classes'] = classes
            row['same_execution_class_across_arms'] = len(set(classes.values())) == 1
    profiles = [r for r in sessions if r['collection'] == 'profile']
    complete = (all(r['valid'] for r in sessions)
                and all(p['command'].get('exit_code') == 0 for p in provenance)
                and all(r['status'] == 'COMPLETE' for r in comparison))
    report = dict(schema=1, created_utc=datetime.now(timezone.utc).isoformat(),
                  complete=complete, arms=list(ARMS), expected_plain_sessions_per_arm=21,
                  expected_profile_sessions_per_arm=2, valid_sessions=sum(r['valid'] for r in sessions),
                  scored_plain_sessions=sum(r['score_eligible'] for r in sessions),
                  primary_metric='median whole-run completed operations per second / 1e6',
                  secondary_metric='median of per-session accepted 300 ms peak Mops/s',
                  notes=[
                      'Source versions ran as sequential blocks, not randomized or interleaved pairs; time/order and frequency drift remain confounders.',
                      'Minimum/maximum show observed repetition ranges, not confidence intervals. Ratios of medians are not paired estimates.',
                      'Profile sessions use cycles:k at 199 Hz and remain unscored; no profile sample enters plain medians.',
                      'NO_JIT API rows measure local physical execution. NORMAL image publication alone does not establish a returned body.',
                      'Synthetic jit_bodies is an entry witness with the completion probe disabled; WITNESSED_JIT preserves runner PASS but does not prove returns. Its returned-body/share metrics are null. API jit_completions counts returns.',
                      'Cross-arm execution-class changes are explicitly marked. In particular, JIT and NO_JIT pipe rates must not be presented as a registry-only speed ratio.',
                      'Final kernel mutex/task counters include preparation and warmup; they are whole-session diagnostics, not measured-window counts.',
                      'Recorded peak arithmetic and full-cohort counts are checked; peak sample-window selection is not independently recomputed here.',
                      'Source snapshots are hash-verified; binary manifests are retained and hashed, not independently rebuilt.',
                  ], provenance=provenance, comparison=comparison, profiles=profiles, sessions=sessions)
    out = args.output or args.base
    out.mkdir(parents=True, exist_ok=True)
    (out / 'comparison.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    csv_rows = []
    for row in comparison:
        flat = {k: v for k, v in row.items() if k not in ('whole_mops', 'peak_mops')}
        for metric in ('whole_mops', 'peak_mops'):
            flat.update({metric + '_' + key: value for key, value in row[metric].items()})
        csv_rows.append(flat)
    write_csv(out / 'comparison.csv', csv_rows)
    write_csv(out / 'sessions.csv', sessions)
    print(json.dumps(dict(complete=complete, valid_sessions=report['valid_sessions'],
                          scored_plain_sessions=report['scored_plain_sessions'],
                          profile_sessions=len(profiles), groups=len(comparison), output=str(out))))
    return 0 if complete else 1


if __name__ == '__main__':
    raise SystemExit(main())
