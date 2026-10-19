#!/usr/bin/env python3
"""Summarize finished real_api records; run only in the recovery VM.

Inputs are read-only. This standalone standard-library report does not import or
execute runner code. It retains failed sessions and keeps distinct measured KD
execution groups separate, including valid single-worker NO_JIT observations.
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
CASES = (('pipes', 'pipebytes', 'query'), ('pipes', 'pipecap', 'query'),
         ('seek', 'seek', 'set'), ('seek', 'seek', 'end'))
REPEATS = 3
COMMON = ('source_identity', 'kernel_identity', 'topology_identity',
          'cpus', 'collector_cpu', 'duration_ms', 'peak_window_ms',
          'peak_settle_ms', 'sample_ms', 'warmup', 'warmup_ms',
          'helper_waves', 'helper_cpus', 'file_descriptions', 'lock_kind',
          'syscalls_per_op', 'entries', 'value_size')
PROTOCOL = ('jit_evidence_version', 'jit_completion_probe', 'entry_abi',
            'caller_abi', 'mutex_implementation')
OPTIONAL_IDENTITY = ('cpu_nodes', 'mutex_wait_mode', 'mutex_spin_limit',
                     'owned_mutex_reuse_spins', 'owned_mutex_adaptive',
                     'owned_mutex_object_bytes', 'owned_mutex_origin_spin',
                     'owned_mutex_numa')
FLAGS = ('diagnostic', 'pmu', 'perf_record')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def unsigned(value):
    return type(value) is int and value >= 0


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def same_number(actual, expected):
    return (type(actual) in (int, float) and math.isfinite(actual)
            and math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-15))


def stats(values):
    if not values:
        return dict(min=None, median=None, max=None, spread_pct=None)
    mid = median(values)
    return dict(min=min(values), median=mid, max=max(values),
                spread_pct=100 * (max(values) - min(values)) / mid
                if len(values) > 1 and mid else None)


def identity(records, fields, label, *, optional=False):
    result = {}
    for field in fields:
        require(optional or all(field in r for r in records),
                f'{label}: missing identity {field}')
        values = [r.get(field, 'unrecorded') for r in records]
        require(len({json.dumps(v, sort_keys=True) for v in values}) == 1,
                f'{label}: mixed identity {field}')
        result[field] = values[0]
    return result


def worker_distribution(counts):
    if not counts or not all(unsigned(value) for value in counts):
        return None
    total = sum(counts)
    return dict(min=min(counts), max=max(counts), total=total,
                zero_workers=sum(value == 0 for value in counts),
                min_share=min(counts) / total if total else None,
                max_share=max(counts) / total if total else None,
                max_min_ratio=max(counts) / min(counts) if min(counts) else None)


def verify_peak(m, r):
    """Independently check the recorded earliest-endpoint peak against samples."""
    label = r['name']
    for field, spec in (('duration_ns', 'duration_ms'),
                        ('peak_window_ns', 'peak_window_ms'),
                        ('peak_settle_ns', 'peak_settle_ms'),
                        ('sample_period_ns', 'sample_ms')):
        require(m[field] == r[spec] * 1000000, f'{label}: timing differs: {field}')
    require(m['deadline_ns'] == m['started_ns'] + m['duration_ns']
            and m['wall_ns'] == m['finished_ns'] - m['started_ns'] > 0
            and 0 < m['sample_period_ns'] <= m['peak_window_ns']
            and m['peak_settle_ns'] + m['peak_window_ns'] < m['duration_ns'],
            f'{label}: invalid timing bounds')
    workers = m['workers']
    require(m['progress_batch'] == 256 and m['collector_error'] == 0
            and m['collector_cpu'] == m['collector_observed_cpu'] == r['collector_cpu']
            and r['collector_cpu'] not in r['cpus'], f'{label}: collector differs')
    for w in workers:
        require(m['started_ns'] <= w['active_started_ns'] < m['deadline_ns']
                <= w['kernel_finished_ns'] <= w['finished_ns'] <= m['finished_ns'],
                f'{label}: worker does not span measurement')
    earliest = max(w['active_started_ns'] for w in workers) + m['peak_settle_ns']
    latest = min(m['deadline_ns'], *(w['kernel_finished_ns'] for w in workers))
    previous_time, previous_counts = m['started_ns'], [0] * len(workers)
    samples, eligible = m['samples'], []
    require(len(samples) >= 2, f'{label}: missing progress samples')
    for index, sample in enumerate(samples):
        begin, end, counts = sample['started_ns'], sample['finished_ns'], sample['completed']
        require(previous_time <= begin <= end and len(counts) == len(workers)
                and all(unsigned(v) and old <= v <= w['completed']
                        for v, old, w in zip(counts, previous_counts, workers)),
                f'{label}: invalid progress sample')
        require(all((end >= w['active_started_ns'] or v == 0)
                    and (begin < w['kernel_finished_ns'] or v == w['completed'])
                    for v, w in zip(counts, workers)), f'{label}: progress outside worker life')
        if begin >= earliest and end <= latest:
            eligible.append(index)
        previous_time, previous_counts = end, counts
    best = None
    for offset, start in enumerate(eligible):
        for end in eligible[offset + 1:]:
            elapsed = samples[end]['finished_ns'] - samples[start]['started_ns']
            if elapsed < m['peak_window_ns']:
                continue
            counts = [b - a for a, b in zip(samples[start]['completed'], samples[end]['completed'])]
            total = sum(counts)
            if min(counts) > 0 and (best is None or total * best[3] > best[2] * elapsed):
                best = (start, end, total, elapsed, counts)
            break
    require(best is not None, f'{label}: no full-cohort peak')
    p = m['peak']
    require((p['start_sample_index'], p['end_sample_index'], p['completed'],
             p['elapsed_ns'], p['worker_completed']) == best
            and p['policy'] == 'observed_full_cohort_earliest_endpoint'
            and same_number(p['throughput_ops_s'], best[2] * 1e9 / best[3]),
            f'{label}: recorded peak differs from independent selection')


def execution_group(r):
    if r['arm'] != 'kdlock':
        return 'NOT_APPLICABLE'
    entries, completed = r.get('jit_bodies'), r.get('jit_completions')
    if entries is None or completed is None:
        return 'UNMEASURED'
    if not (unsigned(entries) and unsigned(completed) and completed <= entries):
        return 'INVALID_EVIDENCE'
    return 'PASS' if completed else 'PARTIAL_JIT' if entries else 'NO_JIT'


def summarize_session(r, folder, nodes):
    label, m = r['name'], r.get('measurement', {})
    accepted = (r['execution_status'] == 'OK' and r.get('drained') is True
                and not any(r.get(field, False) for field in FLAGS))
    count, wall = m.get('completed'), m.get('wall_ns')
    p, workers = m.get('peak') or {}, m.get('workers', [])
    whole = count * 1000 / wall if unsigned(count) and count and unsigned(wall) and wall else None
    peak = p['completed'] * 1000 / p['elapsed_ns'] if p.get('completed') and p.get('elapsed_ns') else None
    entries, completions = r.get('jit_bodies'), r.get('jit_completions')
    tc = r.get('tclock_delegation')
    group = execution_group(r)
    checks = {}
    for name in ('check-before', 'check-after', 'warmup'):
        path = folder / label / (name + '.json')
        checks[name] = read(path) if path.is_file() else None
    if accepted:
        require(m.get('ok') is True and m.get('phase') == 'measure'
                and whole is not None and peak is not None and count > 0
                and len(workers) == r['threads']
                and [w['cpu'] for w in workers] == r['cpus']
                and sum(w['completed'] for w in workers) == count
                and all(w['error'] == 0 and w['cpu'] == w['observed_cpu']
                        and unsigned(w['completed']) and w['completed'] > 0
                        and unsigned(w['cpu_ns']) for w in workers),
                f'{label}: invalid successful measurement/worker oracle')
        require(r['redirected_calls'] == count, f'{label}: redirected syscall count differs')
        require(same_number(r['whole_throughput_ops_s'], whole * 1e6)
                and same_number(r['peak_throughput_ops_s'], peak * 1e6),
                f'{label}: stored throughput differs')
        verify_peak(m, r)
        require(all(checks[name] and checks[name].get('check') is True
                    for name in ('check-before', 'check-after')), f'{label}: missing/failed endpoint oracle')
        warm = checks['warmup']
        require(warm and warm.get('ok') is True and len(warm['workers']) == r['threads']
                and [w['cpu'] for w in warm['workers']] == r['cpus']
                and all(w['completed'] >= r['warmup'] and w['error'] == 0
                        and w['observed_cpu'] == w['cpu']
                        and w['finished_ns'] >= warm['started_ns'] + r['warmup_ms'] * 1000000
                        for w in warm['workers']), f'{label}: warmup oracle differs')
        require(unsigned(entries) and unsigned(completions) and 0 <= completions <= entries <= count
                and r['jit_eligible_operations'] == count
                and same_number(r['jit_share'], entries / count)
                and same_number(r['jit_complete_share'], completions / count),
                f'{label}: invalid measured JIT entry/completion accounting')
        require(r['jit_status'] == group, f'{label}: JIT execution status differs')
        require(not r.get('require_jit') or completions > 0, f'{label}: required returned JIT absent')
        if r['arm'] == 'kdlock':
            before, after = r['published_before'], r['published_after']
            require(before['entry'] == after['entry'] and before['images'] == after['images']
                    and all(x['source']['writers'] == x['source']['frames'] == 0
                            and x['source']['state'] == 0 and x['entry']['status'] == 0
                            and x['entry']['entry_abi'] == 2 and x['entry']['lock_kind'] == 2
                            for x in (before, after)), f'{label}: publication changed or not drained')
            require(r['probe_parameters']['bench_complete_probe'] in ('Y', '1')
                    and int(r['probe_parameters']['bench_lock_addr'], 0) == r['gate_addr'],
                    f'{label}: completion probe differs')
            require(r.get('retired') == dict(state=2, modules=0, frames=0, writers=0),
                    f'{label}: exact KD retirement missing')
        else:
            require(entries == completions == 0, f'{label}: control executed JIT')
        if r['arm'] == 'tclock':
            require(unsigned(tc) and tc <= count, f'{label}: invalid TCLock delegation count')
        # Only source kinds exposing a quiescent module parameter record this
        # field. Mutex cleanup instead checks provider drain and control unbind.
        require('source_quiescent' not in r or r['source_quiescent'] is True,
                f'{label}: recorded source quiescence failed')
    return dict(name=label, input_directory=folder.name, kind=r['kind'], query=r['query'],
                entries=r['entries'], value_size=r['value_size'], threads=r['threads'],
                repeat=r['repeat'], arm=r['arm'], execution_status=r['execution_status'],
                execution_group=group, score_eligible=accepted, drained=r.get('drained', False),
                source_quiescent=r.get('source_quiescent', 'unrecorded'),
                diagnostic=r.get('diagnostic', False), pmu=r.get('pmu', False),
                perf_record=r.get('perf_record', False), require_jit=r.get('require_jit'),
                error=r.get('error'), cleanup_error=r.get('cleanup_error'),
                measurement_ok=m.get('ok'), completed=count, wall_ns=wall,
                redirected_calls=r.get('redirected_calls'),
                whole_mops=whole if accepted else None, peak_mops=peak if accepted else None,
                observed_whole_mops_unscored_if_ineligible=whole,
                observed_peak_mops_unscored_if_ineligible=peak,
                jit_entries=entries, jit_completions=completions,
                measured_jit_entry_share=entries / count if unsigned(entries) and count else None,
                measured_jit_completion_share=completions / count if unsigned(completions) and count else None,
                measured_jit_completion_fraction=completions / entries
                    if unsigned(completions) and unsigned(entries) and entries else None,
                tclock_delegation=tc, measured_tclock_delegation_share=tc / count
                    if unsigned(tc) and count else None,
                address_guard_exits=r.get('address_guard_exits'),
                cpu_nodes_recorded=r.get('cpu_nodes', 'unrecorded'),
                cpu_nodes_from_topology=[nodes[cpu] for cpu in r['cpus']],
                worker_progress=worker_distribution([w.get('completed') for w in workers]),
                peak_worker_progress=worker_distribution(p.get('worker_completed', [])),
                cpu_ns_per_op=sum(w.get('cpu_ns', 0) for w in workers) / count if count else None,
                endpoint_checks={name: checks[name].get('check') if checks[name] else None
                                 for name in ('check-before', 'check-after')},
                warmup_ok=checks['warmup'].get('ok') if checks['warmup'] else None,
                published_image_hashes=(r.get('published_after') or {}).get('images'),
                peak_window=p or None)


def aggregate(sessions):
    operations = sum(s['completed'] for s in sessions)
    entries = sum(s['jit_entries'] for s in sessions)
    completions = sum(s['jit_completions'] for s in sessions)
    tc = [s['tclock_delegation'] for s in sessions]
    delegated = sum(tc) if sessions and all(unsigned(v) for v in tc) else None
    best = max(sessions, key=lambda s: s['peak_mops']) if sessions else None
    progress = [s['worker_progress'] for s in sessions]
    peak_progress = [s['peak_worker_progress'] for s in sessions]
    return dict(valid=len(sessions), whole_mops=stats([s['whole_mops'] for s in sessions]),
                peak_mops=stats([s['peak_mops'] for s in sessions]),
                best_peak_session=best['name'] if best else None,
                best_peak_window=best['peak_window'] if best else None,
                eligible_measured_operations=operations, eligible_jit_entries=entries,
                eligible_jit_completions=completions,
                measured_jit_entry_share=entries / operations if operations else None,
                measured_jit_completion_share=completions / operations if operations else None,
                measured_jit_completion_fraction=completions / entries if entries else None,
                actual_jit_sessions=sum(s['jit_entries'] > 0 for s in sessions),
                actual_jit_completion_sessions=sum(s['jit_completions'] > 0 for s in sessions),
                tclock_delegated_bodies=delegated,
                measured_tclock_delegation_share=delegated / operations
                    if delegated is not None and operations else None,
                worker_min_share=min((p['min_share'] for p in progress), default=None),
                worker_max_share=max((p['max_share'] for p in progress), default=None),
                worker_max_min_ratio=max((p['max_min_ratio'] for p in progress), default=None),
                peak_worker_min_share=min((p['min_share'] for p in peak_progress), default=None),
                peak_worker_max_share=max((p['max_share'] for p in peak_progress), default=None),
                peak_worker_max_min_ratio=max((p['max_min_ratio'] for p in peak_progress), default=None),
                cpu_ns_per_op=stats([s['cpu_ns_per_op'] for s in sessions]))


def backend(raw, sessions, label):
    good = [s for s in sessions if s['score_eligible']]
    groups = {name: aggregate([s for s in good if s['execution_group'] == name])
              for name in sorted({s['execution_group'] for s in good})}
    mixed = len(groups) > 1
    metrics = aggregate([] if mixed else good)
    if mixed:
        # Bookkeeping totals remain exact even when the performance statistics
        # and weighted fractions must stay within each execution group.
        metrics.update(eligible_measured_operations=sum(s['completed'] for s in good),
                       eligible_jit_entries=sum(s['jit_entries'] for s in good),
                       eligible_jit_completions=sum(s['jit_completions'] for s in good),
                       actual_jit_sessions=sum(s['jit_entries'] > 0 for s in good),
                       actual_jit_completion_sessions=sum(s['jit_completions'] > 0 for s in good))
    # A mixed entry/completion class must never become one throughput curve.
    return dict(metrics, arm=raw[0]['arm'], valid=len(good), planned=REPEATS,
                valid_n_of_3=f'{len(good)}/{REPEATS}',
                status='MIXED_EXECUTION_GROUPS' if mixed else
                       'COMPLETE' if len(good) == REPEATS else 'PARTIAL' if good else 'NO_VALID',
                execution_group='MIXED' if mixed else next(iter(groups), 'UNSCORED'),
                execution_statuses=dict(sorted(Counter(s['execution_status'] for s in sessions).items())),
                jit_execution_statuses=dict(sorted(Counter(s['execution_group'] for s in sessions).items())),
                identity={**identity(raw, PROTOCOL, label),
                          **identity(raw, OPTIONAL_IDENTITY, label, optional=True),
                          **identity([{k: r.get(k, False) for k in FLAGS} for r in raw], FLAGS, label)},
                execution_groups=groups, sessions=sessions)


def input_collection(folder):
    records = read(folder / 'records.json')
    require(isinstance(records, list) and len(records) == 72,
            f'{folder}: expected 72 planned records, retaining failures/unrun cases')
    source = read(folder / 'source-sha256.json')
    source_identity = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
    files = ('records.json', 'plan.json', 'source-sha256.json', 'kernel-identity.json',
             'topology.txt', 'environment.json', 'binaries.json', 'build-configuration.json')
    hashes = {name: digest(folder / name) for name in files}
    require(all(r['source_identity'] == source_identity
                and r['kernel_identity'] == hashes['kernel-identity.json']
                and r['topology_identity'] == hashes['topology.txt'] for r in records),
            f'{folder}: record source/kernel/topology identity differs from retained inputs')
    for relative, expected in source.items():
        require(digest(folder / 'source' / relative) == expected, f'{folder}: changed source {relative}')
    binaries = read(folder / 'binaries.json')
    for relative, item in binaries.items():
        # Resolve through this evidence collection, not a historical absolute path.
        require(digest(folder / 'build' / relative) == item['sha256'],
                f'{folder}: changed binary {relative}')
    nodes = {}
    for line in (folder / 'topology.txt').read_text().splitlines():
        fields = line.split()
        if fields and fields[0].isdigit():
            require(len(fields) >= 5 and fields[4] == 'yes', f'{folder}: offline or malformed CPU')
            nodes[int(fields[0])] = int(fields[1])
    require(nodes, f'{folder}: missing topology')
    plan = read(folder / 'plan.json')
    require(len(plan) == len(records), f'{folder}: plan/record count differs')
    planned = {r['name']: r for r in plan}
    require(len(planned) == len(plan), f'{folder}: duplicate planned name')
    for r in records:
        require(r['name'] in planned and all(r.get(k) == v for k, v in planned[r['name']].items()),
                f'{folder}/{r["name"]}: record changed planned identity')
    return records, nodes, dict(directory=str(folder), file_sha256=hashes,
                                source_identity=source_identity, verified_source_files=len(source),
                                binaries=binaries, verified_binary_files=len(binaries),
                                kernel=read(folder / 'kernel-identity.json'),
                                topology=(folder / 'topology.txt').read_text(),
                                environment=read(folder / 'environment.json'),
                                build_configuration=read(folder / 'build-configuration.json'))


def write_csv(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows({k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v
                          for k, v in row.items()} for row in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True,
                        help='Finished evidence root containing pipes/ and seek/')
    parser.add_argument('--output', type=Path, required=True, help='Report output directory')
    parser.add_argument('--host-receipt', type=Path, action='append', default=[])
    args = parser.parse_args()
    indexed, provenance, all_raw, topology = {}, [], [], {}
    for directory in ('pipes', 'seek'):
        raw, nodes, evidence = input_collection(args.base / directory)
        provenance.append(evidence)
        topology[directory] = nodes
        all_raw.extend(raw)
        for r in raw:
            key = (directory, r['kind'], r['query'], r['entries'], r['threads'], r['arm'], r['repeat'])
            require(key not in indexed and r['lock_kind'] == 'mutex' and r['value_size'] == 64,
                    f'{directory}: unexpected/duplicate session {key}')
            require(r['jit_evidence_version'] == 2
                    and r['jit_completion_probe'] == (r['arm'] == 'kdlock')
                    and r['entry_abi'] == (2 if r['arm'] == 'kdlock' else 0)
                    and r['caller_abi'] == ('clobber' if r['arm'] == 'kdlock' else 'c')
                    and r['mutex_implementation'] == ('kd-only-legacy' if r['arm'] == 'kdlock' else 'not_applicable'),
                    f'{r["name"]}: unexpected protocol or completion instrumentation')
            indexed[key] = r
    shared_identity = identity(all_raw, ('source_identity', 'kernel_identity', 'topology_identity'), 'screen')
    for arm in ARMS:
        identity([r for r in all_raw if r['arm'] == arm], PROTOCOL, arm + '/all cohorts')
        identity([r for r in all_raw if r['arm'] == arm], OPTIONAL_IDENTITY[1:],
                 arm + '/all cohorts', optional=True)
    rows, wide, flat, session_rows = [], [], [], []
    for directory, kind, query in CASES:
        for threads in THREADS:
            label = f'{kind}-{query}'
            common = dict(case=label, kind=kind, query=query, entries=16, value_size=64, threads=threads)
            row, flattened, matched = dict(common, backends={}), dict(common), []
            for arm in ARMS:
                raw = [indexed.pop((directory, kind, query, 16, threads, arm, repeat))
                       for repeat in range(REPEATS)]
                matched.extend(raw)
                sessions = [summarize_session(r, args.base / directory, topology[directory]) for r in raw]
                session_rows.extend(sessions)
                b = backend(raw, sessions, f'{label}/{threads}/{arm}')
                row['backends'][arm] = b
                exported = dict(common, arm=arm)
                for key in ('valid', 'planned', 'valid_n_of_3', 'status', 'execution_group',
                            'execution_statuses', 'jit_execution_statuses', 'eligible_measured_operations',
                            'eligible_jit_entries', 'eligible_jit_completions', 'measured_jit_entry_share',
                            'measured_jit_completion_share', 'measured_jit_completion_fraction',
                            'actual_jit_sessions', 'actual_jit_completion_sessions', 'tclock_delegated_bodies',
                            'measured_tclock_delegation_share', 'worker_min_share', 'worker_max_share',
                            'worker_max_min_ratio', 'peak_worker_min_share', 'peak_worker_max_share',
                            'peak_worker_max_min_ratio', 'best_peak_session'):
                    exported[key] = b[key]
                for metric in ('whole_mops', 'peak_mops', 'cpu_ns_per_op'):
                    for statistic, value in b[metric].items():
                        exported[f'{metric}_{statistic}'] = value
                exported['peak_mops_best'] = b['peak_mops']['max']
                flat.append(exported)
                flattened.update({arm + '_' + k: v for k, v in exported.items()
                                  if k not in (*common, 'arm')})
            row['identity'] = identity(matched, COMMON, f'{label}/{threads}/controls')
            identity(matched, ('cpu_nodes',), f'{label}/{threads}/controls', optional=True)
            row['cpu_nodes_from_topology'] = [topology[directory][cpu] for cpu in row['identity']['cpus']]
            row['ratios'] = {}
            for control in ('native', 'tclock'):
                for metric, statistic, suffix in (('whole_mops', 'median', 'whole_median'),
                                                   ('peak_mops', 'median', 'peak_median'),
                                                   ('peak_mops', 'max', 'peak_best')):
                    kd, other = row['backends']['kdlock'][metric][statistic], row['backends'][control][metric][statistic]
                    row['ratios'][f'kd_over_{control}_{suffix}'] = kd / other if kd is not None and other else None
            row['status'] = 'COMPLETE' if all(b['status'] == 'COMPLETE' for b in row['backends'].values()) else 'INCOMPLETE'
            flattened.update(row['ratios'], row_status=row['status'])
            rows.append(row)
            wide.append(flattened)
    require(not indexed, f'unexpected sessions: {list(indexed)}')
    receipts = []
    for path in args.host_receipt:
        content = path.read_text()
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            pass
        receipts.append(dict(path=str(path), sha256=digest(path), content=content))
    result = dict(schema=1, generated_utc=datetime.now(timezone.utc).isoformat(),
                  source_base=str(args.base), script_sha256=digest(Path(__file__)),
                  comparison_rows=len(rows), backend_groups=len(flat), planned_sessions=len(session_rows),
                  eligible_sessions=sum(s['score_eligible'] for s in session_rows),
                  unscored_sessions=[s for s in session_rows if not s['score_eligible']],
                  shared_identity=shared_identity, provenance=provenance, host_receipts=receipts,
                  primary_metric='median whole-interval million completed syscall operations/second',
                  eligibility='Maintained real_api report: execution_status OK, drained true, no diagnostic/PMU/perf flags. Accepted records additionally pass independent exact measurement, peak, endpoint, source/binary and returned-body accounting checks.',
                  execution_group_policy='PASS/PARTIAL_JIT/NO_JIT remain separate. Mixed eligible KD classes have no pooled throughput or ratio; execution_groups retains each class. Failed and unrun sessions remain visible.',
                  jit_definitions={'entries': 'jit_bodies counts entry witnesses, not completed bodies',
                                   'completion_share': 'sum returned jit_completions / sum measured operations',
                                   'completion_fraction': 'sum returned jit_completions / sum jit_bodies entries; null when no entries',
                                   'no_jit': 'An accepted NO_JIT run at any worker count is performance data, not delegation evidence'},
                  tclock_definition='Measured tclock_delegation counts native delegated bodies; weighted share divides by measured operations. This runner records no park counter.',
                  spread_definition='100 * (maximum - minimum) / median across eligible same-execution-group repeats; null for n<2',
                  ratios_definition='Within workload/cohort: KD median/median or best-peak/best-peak, as named; no cross-workload pooling',
                  limits=['Three short repeats are a screen, not confidence intervals or long-run fairness evidence.',
                          'Peak windows and whole-interval rates are distinct; worker progress summaries do not measure lock acquisition latency.',
                          'Native/TCLock C shells and KD clobber shells differ; all include syscalls, validation and benchmark observation.',
                          'Pipe queries use private per-worker descriptions; seek updates a shared description and retains file-reference traffic.',
                          'No paired 256-byte KD baseline is included; these controls do not isolate compact-layout overhead.',
                          'Retain each collection binary identity and actual host placement receipts; binding policy does not prove page placement.'],
                  rows=rows)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'comparison.json').write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    write_csv(args.output / 'comparison.csv', wide)
    write_csv(args.output / 'backend-groups.csv', flat)
    write_csv(args.output / 'sessions.csv', [{k: v for k, v in s.items() if k != 'peak_window'} for s in session_rows])
    print(json.dumps(dict(output=str(args.output), rows=len(rows), backend_groups=len(flat),
                          sessions=len(session_rows), eligible=result['eligible_sessions'])))


if __name__ == '__main__':
    main()
