#!/usr/bin/env python3
"""Read fresh three-backend mutex evidence; keep entry, returned and local classes separate."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
from statistics import median

COLLECTIONS = ('c01', 'c08', 'rcuht', 'seek-set', 'seek-end', 'pipebytes', 'pipecap')
SYNTHETIC = ('c01', 'c08', 'rcuht')
BACKENDS = ('native', 'tclock', 'kdlock')
WORKERS = (1, 2, 4, 8, 16, 32, 36, 48, 60)
FAULT = re.compile(r'BUG:|\bWARNING:|kernel panic|double fault|soft lockup|hard LOCKUP|'
                   r'unable to handle|general protection fault|Oops:|\[ERROR\]|'
                   r'\[KD_JIT\]\[ERROR\]|invariant_failures=[1-9]|runtime error:|KASAN:|UBSAN:', re.I)
IDENTITY = ('arm', 'lock_kind', 'caller_abi', 'caller_shell', 'cookie_storage', 'api_mode',
    'scenario', 'measurement_mode', 'cpus', 'cpu_nodes', 'collector_cpu', 'collector_shared',
    'duration_ms', 'peak_window_ms', 'peak_settle_ms', 'sample_ms', 'warmup_iterations_per_worker',
    'warmup', 'warmup_ms', 'entries', 'value_size', 'syscalls_per_op', 'file_descriptions',
    'hotlock_mode', 'cpu_heat_policy', 'numa_policy', 'delegation_batch_limit', 'kd_provider_ubsan',
    'jit_completion_probe', 'jit_evidence_version', 'entry_abi', 'mutex_implementation', 'mutex_lock_offset')


def read(path):
    return json.loads(path.read_text())


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def unsigned(value):
    return type(value) is int and value >= 0


def same(a, b):
    return (type(a) in (int, float) and type(b) in (int, float) and
            math.isfinite(a) and math.isfinite(b) and math.isclose(a, b, rel_tol=1e-12))


def stats(values):
    return dict(n=len(values), min=min(values) if values else None,
                median=median(values) if values else None, max=max(values) if values else None)


def production(manifest):
    suffixes = ('.c', '.h', '.inc', '.S', '.def', '.py', '.json', '.patch')
    return {k: v for k, v in manifest.items() if k.startswith(('include/', 'kernel_module/'))
            and not k.endswith('.mod.c') and (Path(k).suffix in suffixes or Path(k).name == 'Makefile')}


def diagnostics(path, kd):
    if not path.is_file():
        return dict(present=False, fault_count=0, issues=['missing kernel log'],
                    mutex_stats=None, mutex_tasks=None, bodies_per_combiner=None)
    lines = path.read_text(errors='replace').splitlines()
    faults = [line for line in lines if FAULT.search(line)]
    result = dict(present=True, sha256=digest(path), fault_count=len(faults), fault_examples=faults[:5], issues=[])
    for name, marker in (('mutex_stats', 'kd_mutex stats:'), ('mutex_tasks', 'kd_mutex tasks:')):
        matches = [line for line in lines if marker in line]
        result[name] = dict((k, int(v)) for k, v in re.findall(r'(\w+)=(-?\d+)', matches[0])) if len(matches) == 1 else None
        if kd and len(matches) != 1:
            result['issues'].append(name + ': missing or ambiguous final row')
        if not kd and matches:
            result['issues'].append('KD provider diagnostics in non-KD control')
    if any('kd_mutex aux:' in line for line in lines):
        result['issues'].append('obsolete auxiliary diagnostics remain')
    physical = result['mutex_stats'] or {}
    success, count = physical.get('jit_success'), physical.get('combiner')
    result['bodies_per_combiner'] = success / count if count and unsigned(success) else None
    return result


def retained_no_jit(row):
    m = row.get('measurement', {})
    return (row.get('arm') == 'kdlock' and row.get('execution_status') == 'NO_JIT'
        and row.get('jit_acceptance') == 'NO_JIT' and row.get('jit_bodies') == 0
        and row.get('drained') is True and not row.get('cleanup_error')
        and m.get('complete') is True and m.get('data_ok') is True)


def saved_matches(saved, record, synthetic):
    if not synthetic:
        return saved == record
    derived = {'whole_amortized_ns_op', 'throughput_ops_s', 'whole_throughput_ops_s', 'score_eligible', 'amortized_ns_op'}
    if set(record) - set(saved) != derived or any(record.get(k) != v for k, v in saved.items()):
        return False
    m, peak = saved.get('measurement', {}), saved.get('measurement', {}).get('peak', {})
    good = (saved.get('execution_status') == 'OK' and saved.get('drained') is True
            and m.get('complete') is True and m.get('data_ok') is True)
    if record.get('score_eligible') is not good:
        return False
    numeric = derived - {'score_eligible'}
    if not good:
        return all(record.get(k) is None for k in numeric) and retained_no_jit(saved)
    if not all(unsigned(v) and v > 0 for v in (m.get('completed'), m.get('wall_ns'), peak.get('completed'), peak.get('elapsed_ns'))):
        return False
    expected = dict(whole_throughput_ops_s=m['completed'] * 1e9 / m['wall_ns'],
        whole_amortized_ns_op=m['wall_ns'] / m['completed'],
        throughput_ops_s=peak['completed'] * 1e9 / peak['elapsed_ns'],
        amortized_ns_op=peak['elapsed_ns'] / peak['completed'])
    return all(same(record.get(k), v) for k, v in expected.items())


def session_summary(base, folder, row, collection, commit, source_id, inherited):
    name, backend = row['name'], row['arm']
    if Path(name).name != name or name in ('.', '..'):
        raise ValueError('unsafe session name')
    path = folder / name
    synthetic, kd, tc = collection in SYNTHETIC, backend == 'kdlock', backend == 'tclock'
    rejected = synthetic and retained_no_jit(row)
    issues = list(inherited)
    check = lambda ok, message: issues.append(message) if not ok else None
    saved = path / 'session.json'
    check(saved.is_file() and saved_matches(read(saved), row, synthetic), 'saved session/derived aggregate fields differ')
    check(row.get('execution_status') == 'OK' or rejected, 'execution failed')
    check(row.get('drained') is True and not row.get('cleanup_error'), 'final drain failed')
    check(not row.get('error') or rejected, 'unaccepted execution error')
    check(backend in BACKENDS and row.get('lock_kind') == 'mutex', 'backend/lock kind differs')
    check(row.get('cpus') == list(range(row['threads'])) and row.get('collector_cpu') == 63, 'CPU placement differs')
    check(tuple(row.get(k) for k in ('duration_ms', 'peak_window_ms', 'peak_settle_ms', 'sample_ms')) ==
          (2000, 300, 300, 10), 'measurement policy differs')
    check(not any(row.get(k) for k in ('diagnostic', 'pmu', 'perf_record')) and row.get('mutex_lock_offset') is None,
          'instrumentation/placement diagnostic in ordinary cohort')
    m = row.get('measurement', {})
    count, wall = m.get('completed'), m.get('wall_ns')
    measurable = unsigned(count) and count > 0 and unsigned(wall) and wall > 0
    rate = count * 1000 / wall if measurable else None
    check(measurable, 'missing positive operation/time counts')
    if not rejected:
        check(same(row.get('whole_throughput_ops_s'), rate * 1e6 if rate else None), 'whole rate arithmetic differs')
    peak = m.get('peak', {})
    peak_count, peak_elapsed = peak.get('completed'), peak.get('elapsed_ns')
    peak_measurable = unsigned(peak_count) and peak_count > 0 and unsigned(peak_elapsed) and peak_elapsed > 0
    peak_rate = peak_count * 1000 / peak_elapsed if peak_measurable else None
    check(peak_measurable and same(peak.get('throughput_ops_s'), peak_rate * 1e6 if peak_rate else None)
          and same(peak.get('amortized_ns_op'), peak_elapsed / peak_count if peak_measurable else None),
          'peak rate arithmetic differs')
    reported_peak = row.get('throughput_ops_s' if synthetic else 'peak_throughput_ops_s')
    check(reported_peak is None if rejected else same(reported_peak, peak_rate * 1e6 if peak_rate else None),
          'reported peak rate differs from measured window or rejected-score policy')
    workers = m.get('workers', [])
    check(len(workers) == row['threads'] and all(unsigned(w.get('completed')) and w['completed'] > 0
          and w.get('error') == 0 and w.get('observed_cpu') == w.get('cpu') for w in workers)
          and sum(w.get('completed', 0) for w in workers) == count
          and [w.get('cpu') for w in workers] == row.get('cpus'), 'worker oracle/progress differs')
    check(m.get('collector_error') == 0 and m.get('collector_observed_cpu') == 63
          and m.get('duration_ns') == 2000000000 and wall == m.get('finished_ns', 0) - m.get('started_ns', 0),
          'collector/measurement interval differs')
    entries, returned = row.get('jit_bodies'), None if synthetic else row.get('jit_completions')
    check(unsigned(entries) and measurable and entries <= count, 'invalid JIT entries')
    jit_class = 'NOT_APPLICABLE' if not kd else (('WITNESSED_JIT' if entries else 'NO_JIT') if synthetic
                else ('RETURNED_JIT' if returned else 'PARTIAL_JIT' if entries else 'NO_JIT'))
    if not kd:
        check(entries == 0 and (synthetic or returned == 0), 'non-KD control reports JIT')
    if synthetic:
        check(m.get('complete') is True and m.get('data_ok') is True, 'synthetic oracle failed')
        check(row.get('warmup_iterations_per_worker') == 48000, 'synthetic warmup differs')
        geometry = row.get('layout', {})
        if kd or backend == 'native':
            check(geometry.get('lock_bytes') == 32 and unsigned(geometry.get('lock_addr'))
                  and geometry['lock_addr'] > 0 and geometry['lock_addr'] % 8 == 0, '32-byte/native-aligned geometry differs')
            check('lock_align' not in geometry or geometry['lock_align'] == 8, 'reported type alignment differs')
        if kd:
            check(row.get('parameters', {}).get('bench_complete_probe') in ('N', '0'), 'synthetic returned probe unexpectedly enabled')
            check(unsigned(row.get('jit_before')) and unsigned(row.get('jit_after'))
                  and row['jit_after'] - row['jit_before'] == entries, 'synthetic JIT delta differs')
        if collection == 'rcuht':
            check(tuple(geometry.get(k) for k in ('workload', 'buckets', 'entries', 'key_range', 'resched')) ==
                  ('rcuht', 1024, 4096, 8192, 0), 'RCUHT geometry differs')
    else:
        check(m.get('ok') is True and m.get('phase') == 'measure', 'API oracle failed')
        check(row.get('redirected_calls') == count == row.get('jit_eligible_operations'), 'API operation accounting differs')
        check(unsigned(returned) and unsigned(entries) and returned <= entries, 'invalid returned JIT count')
        check(row.get('warmup') == 48000 and row.get('warmup_ms') == 1000, 'API warmup differs')
        expected_jit = ('PASS' if returned else 'PARTIAL_JIT' if entries else 'NO_JIT') if kd else 'NOT_APPLICABLE'
        check(row.get('jit_status') == expected_jit and row.get('require_jit') is False, 'API JIT verdict/policy differs')
        if kd:
            check(row.get('jit_completion_probe') is True and row.get('jit_evidence_version') == 2 and
                  row.get('entry_abi') == 2, 'API completion instrumentation differs')
        check(row.get('source_identity') == source_id, 'API source identity differs')
        for label in ('check-before', 'check-after'):
            oracle = path / (label + '.json')
            check(oracle.is_file() and read(oracle).get('check') is True, 'missing/failed ' + label)
    d = diagnostics(path / 'kernel.log', kd)
    issues.extend(d['issues'])
    check(d['present'] and d['fault_count'] == 0, 'missing kernel log or fault')
    if kd:
        check(row.get('retired') == dict(state=2, modules=0, frames=0, writers=0), 'KD source retirement differs')
        check(row.get('caller_abi') == 'clobber', 'KD wrapper ABI differs')
        physical, tasks = d['mutex_stats'] or {}, d['mutex_tasks'] or {}
        check(all(physical.get(k) == 0 for k in ('active_waiters', 'reserved_nodes', 'frame_failure')) and
              tasks.get('active_tasks') == 0, 'KD physical/task drain counters differ')
        check(unsigned(physical.get('origin_acquires')) and physical.get('origin_acquires') == physical.get('origin_releases'),
              'KD physical acquire/release imbalance')
    else:
        check('retired' not in row, 'KD retirement record in non-KD control')
    delegated = row.get('delegated_bodies') if synthetic else row.get('tclock_delegation')
    if tc:
        check(unsigned(delegated) and measurable and delegated <= count, 'invalid measured TCLock delegation count')
        if synthetic:
            before, after, drained = (row.get(k, {}) for k in ('tclock_before', 'tclock_after', 'tclock_drained'))
            check(all(p.get('quiescent') == 1 for p in (before, after, drained)), 'TCLock queue/stack not quiescent')
            check(unsigned(before.get('delegated')) and unsigned(after.get('delegated')) and
                  after['delegated'] - before['delegated'] == delegated, 'TCLock measured delegation delta differs')
    return dict(source_commit=commit, source_identity=source_id, collection=collection, workload=collection,
        backend=backend, threads=row['threads'], repeat=row['repeat'], name=name,
        session_path=str(path.relative_to(base)), valid=not issues, issues=issues,
        score_eligible=not issues and not rejected, retained_no_jit_rejection=rejected,
        execution_status=row.get('execution_status'), original_jit_verdict=row.get('jit_acceptance') if synthetic else row.get('jit_status'),
        drained=row.get('drained'), jit_class=jit_class, completed=count, wall_ns=wall,
        jit_bodies=entries, jit_completions=returned, tclock_delegated=delegated if tc else None,
        measured_body_entry_share=entries / count if kd and measurable and unsigned(entries) else None,
        measured_returned_jit_share=returned / count if kd and measurable and unsigned(returned) else None,
        measured_tclock_delegation_share=delegated / count if tc and measurable and unsigned(delegated) else None,
        observed_whole_mops=rate, measured_peak_mops=peak_rate, whole_session_diagnostics=d,
        identity={k: row.get(k) for k in IDENTITY}, layout=row.get('layout'),
        session_sha256=digest(saved) if saved.is_file() else None)


def aggregate(rows):
    first = rows[0]
    usable = [r for r in rows if r['score_eligible']]
    identities = {json.dumps(r['identity'], sort_keys=True) for r in rows}
    if len(identities) != 1:
        usable = []
    total = sum(r['completed'] for r in usable)
    def share(key):
        return sum(r[key] for r in usable) / total if total and all(unsigned(r[key]) for r in usable) else None
    return dict(**{k: first[k] for k in ('source_commit', 'source_identity', 'collection', 'workload', 'backend', 'threads', 'jit_class')},
        status='COMPLETE' if len(usable) == 3 else 'REJECTED_NO_JIT' if all(r['retained_no_jit_rejection'] for r in rows)
               else 'MIXED_IDENTITY' if len(identities) != 1 else 'INCOMPLETE_CLASS',
        planned=3, collected=len(rows), valid=len(usable), repeats=[r['repeat'] for r in usable],
        whole_mops=stats([r['observed_whole_mops'] for r in usable]),
        peak_mops=stats([r['measured_peak_mops'] for r in usable]),
        measured_body_entry_share=share('jit_bodies') if first['backend'] == 'kdlock' else None,
        measured_returned_jit_share=share('jit_completions') if first['backend'] == 'kdlock' else None,
        measured_tclock_delegation_share=share('tclock_delegated'),
        whole_session_bodies_per_combiner=stats([r['whole_session_diagnostics']['bodies_per_combiner'] for r in usable
            if r['whole_session_diagnostics']['bodies_per_combiner'] is not None]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if os.uname().release != '6.1.159-kdclobber2':
        raise RuntimeError('run only in the recovery VM')
    base, out = args.base.resolve(), (args.output or args.base).resolve()
    matrix = read(base / 'current/matrix.json')
    commit = matrix.get('source_commit')
    issues, collections, sessions, productions = [], [], [], []
    if not matrix.get('passed') or not matrix.get('final_idle') or matrix.get('plain_sessions') != 567:
        issues.append('matrix incomplete or scope differs')
    for name in COLLECTIONS:
        folder = base / 'current' / name
        records = read(folder / 'records.json')
        source = read(folder / 'source-sha256.json')
        source_id = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
        command = read(base / 'current' / (name + '-command.json'))
        local = []
        expected = {(b, n, r) for b in BACKENDS for n in WORKERS for r in range(3)}
        if len(records) != 81 or {(r['arm'], r['threads'], r['repeat']) for r in records} != expected:
            local.append('missing/duplicate/unexpected planned sessions')
        plan = read(folder / 'plan.json')
        planned = {r['name']: r for r in plan}
        if len(planned) != 81 or len(plan) != 81 or any(r['name'] not in planned or
                any(r.get(k) != v for k, v in planned[r['name']].items()) for r in records):
            local.append('record differs from frozen plan')
        if command.get('source_commit') != commit or command.get('collection') != name or not command.get('idle_after'):
            local.append('command/source/drain receipt differs')
        rejected = [r['name'] for r in records if retained_no_jit(r)] if name in SYNTHETIC else []
        if command.get('non_jit_rejections') != rejected:
            local.append('retained NO_JIT inventory differs')
        if rejected:
            failure = read(folder / 'failure.json')
            if command.get('exit_code') != 1 or failure.get('status') != 'NO_JIT' or failure.get('sessions') != rejected:
                local.append('NO_JIT original failure receipt differs')
        elif command.get('exit_code') != 0:
            local.append('collection command failed')
        for relative, sha in source.items():
            p = Path(relative)
            if p.is_absolute() or '..' in p.parts or not (folder / 'source' / p).is_file() or digest(folder / 'source' / p) != sha:
                local.append('frozen source differs: ' + relative)
        prod = production(source)
        if not prod or not any(k.endswith('.inc') for k in prod) or 'include/kd_mutex_state.h' not in prod:
            local.append('current compact production/private inputs missing')
        if any(k in prod for k in ('include/kd_mutex_aux.h', 'kernel_module/kd_mutex_aux.c')):
            local.append('obsolete auxiliary source remains')
        productions.append(prod)
        collections.append(dict(collection=name, source_commit=commit, source_identity=source_id, sessions=len(records),
            issues=local, source_manifest_sha256=digest(folder / 'source-sha256.json'),
            records_sha256=digest(folder / 'records.json'), production_files=len(prod),
            command_sha256=digest(base / 'current' / (name + '-command.json'))))
        sessions.extend(session_summary(base, folder, r, name, commit, source_id, local) for r in records)
    if any(p != productions[0] for p in productions):
        issues.append('production source differs between collections')
    grouped = defaultdict(list)
    for row in sessions:
        grouped[row['workload'], row['backend'], row['threads'], row['jit_class']].append(row)
    groups = [aggregate(rows) for _, rows in sorted(grouped.items())]
    complete = not issues and len(sessions) == 567 and all(r['valid'] for r in sessions) and all(not c['issues'] for c in collections)
    result = dict(schema=1, created_utc=datetime.now(timezone.utc).isoformat(), complete=complete,
        source_commit=commit, backends=list(BACKENDS), workers=list(WORKERS), collections=collections,
        sessions=sessions, groups=groups, issues=issues,
        execution_status_counts=dict(Counter(r['execution_status'] for r in sessions)),
        execution_class_counts=dict(Counter(r['jit_class'] for r in sessions)),
        score_eligible_sessions=sum(r['score_eligible'] for r in sessions),
        retained_no_jit_rejections=sum(r['retained_no_jit_rejection'] for r in sessions),
        analysis_helper=dict(file=Path(__file__).name, sha256=digest(Path(__file__))),
        notes=['Whole Mops/s is completed operations / actual wall interval; ranges are observed repetitions, not confidence intervals.',
               'Peak Mops/s uses each session\'s validated observed full-cohort window; its statistics remain separate from whole-run throughput and whole-run delegation shares.',
               'Separate execution-class groups never pool PASS/NO_JIT/PARTIAL_JIT. COMPLETE requires three matching eligible repeats.',
               'Synthetic entries do not prove returns. API explicit completions and TCLock delegated counts remain separate.',
               'Drained rejected synthetic NO_JIT is retained but excluded from timing scores; its raw observed rate remains in sessions.',
               'Whole-session provider ratios include warmup and checks, never a measured-phase batch distribution.',
               'Seven sequential workload blocks; backend order varies within repeats. No prior-source measurements are pooled.'])
    out.mkdir(parents=True, exist_ok=True)
    (out / 'comparison.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    lines = ['| Workload | Backend | Workers | Class | Eligible repeats | Whole Mops/s median [min, max] | Status |',
             '| --- | --- | ---: | --- | ---: | ---: | --- |']
    for row in groups:
        v = row['whole_mops']
        value = '—' if not v['n'] else f"{v['median']:.3f} [{v['min']:.3f}, {v['max']:.3f}]"
        lines.append(f"| {row['workload']} | {row['backend']} | {row['threads']} | {row['jit_class']} | {v['n']} | {value} | {row['status']} |")
    (out / 'comparison-table.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps(dict(complete=complete, sessions=len(sessions), groups=len(groups),
        invalid=sum(not r['valid'] for r in sessions), rejected_no_jit=result['retained_no_jit_rejections'], issues=issues)))
    return 0 if complete else 1


if __name__ == '__main__':
    raise SystemExit(main())
