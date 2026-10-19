#!/usr/bin/env python3
"""VM-only compact report of explicit mutex source arms; never run workloads.

Read ARM/pipe for the fresh embedded32 and old256 source blocks. Raw measurements and source
manifests remain in their original collections; this report retains compact
session evidence, separate timing classes, and whole-session diagnostics.
"""
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


FAULT = re.compile(r'BUG:|\bWARNING:|kernel panic|double fault|soft lockup|hard LOCKUP|'
                   r'unable to handle|general protection fault|Oops:|\[ERROR\]|'
                   r'\[KD_JIT\]\[ERROR\]|invariant_failures=[1-9]|runtime error:|KASAN:|UBSAN:', re.I)
GROUPS = ('pipe',)
IDENTITY = ('arm', 'lock_kind', 'caller_abi', 'caller_shell', 'cookie_storage',
            'api_mode', 'scenario', 'measurement_mode', 'cpus', 'cpu_nodes',
            'collector_cpu', 'collector_shared', 'duration_ms', 'peak_window_ms',
            'peak_settle_ms', 'sample_ms', 'warmup_iterations_per_worker',
            'warmup', 'warmup_ms', 'entries', 'value_size', 'syscalls_per_op',
            'file_descriptions', 'hotlock_mode', 'cpu_heat_policy', 'numa_policy',
            'delegation_batch_limit', 'kd_provider_ubsan', 'jit_completion_probe',
            'jit_evidence_version', 'entry_abi', 'mutex_implementation')


def read(path):
    return json.loads(path.read_text())


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def unsigned(value):
    return type(value) is int and value >= 0


def same(a, b):
    return (type(a) in (int, float) and type(b) in (int, float) and
            math.isfinite(a) and math.isfinite(b) and math.isclose(a, b, rel_tol=1e-12))


def stats(values):
    return dict(n=len(values), min=min(values) if values else None,
                median=median(values) if values else None, max=max(values) if values else None)


def case(record, group):
    return '%s-%s-n%d' % (record['kind'], record['query'], record['entries'])


def expected(group):
    return {('pipebytes-query-n16', workers, repeat) for workers in (8, 60) for repeat in range(3)}


def diagnostics(path):
    if not path.is_file():
        return dict(present=False, fault_count=0, fault_examples=[], mutex_stats=None,
                    mutex_tasks=None, mutex_aux=None, issues=['missing kernel.log'])
    lines = path.read_text(errors='replace').splitlines()
    faults = [line for line in lines if FAULT.search(line)]
    result = dict(present=True, sha256=digest(path), fault_count=len(faults),
                  fault_examples=faults[:5], issues=[])
    for name, marker in (('mutex_stats', 'kd_mutex stats:'), ('mutex_tasks', 'kd_mutex tasks:'),
                         ('mutex_aux', 'kd_mutex aux:')):
        matches = [line for line in lines if marker in line]
        result[name] = dict((k, int(v)) for k, v in re.findall(r'(\w+)=(-?\d+)', matches[0])) if len(matches) == 1 else None
        if len(matches) != 1 and (name != 'mutex_aux' or matches):
            result['issues'].append(name + ': missing or ambiguous final row')
    physical = result['mutex_stats'] or {}
    success, combiners = physical.get('jit_success'), physical.get('combiner')
    result['bodies_per_combiner'] = success / combiners if combiners and unsigned(success) else None
    return result



def session_summary(base, folder, record, arm, group, commit, source_id, collection_issues):
    name = record['name']
    if Path(name).name != name or name in ('.', '..'):
        raise ValueError('unsafe session name: ' + name)
    path = folder / name
    issues = list(collection_issues)
    check = lambda ok, message: issues.append(message) if not ok else None
    saved_path = path / 'session.json'
    check(saved_path.is_file() and read(saved_path) == record,
          'saved session and aggregate record differ')
    d = diagnostics(path / 'kernel.log')
    issues.extend(d['issues'])
    check(d['present'] and not d['fault_count'], 'kernel log missing or fault marker present')
    check(record.get('execution_status') == 'OK' and record.get('drained') is True, 'execution/drain failed')
    check(not record.get('error') and not record.get('cleanup_error'), 'recorded execution/cleanup error')
    check(record.get('retired') == dict(state=2, modules=0, frames=0, writers=0), 'source retirement differs')
    check(record.get('arm') == 'kdlock' and record.get('lock_kind') == 'mutex' and
          record.get('caller_abi') == 'clobber', 'backend/protocol/ABI differs')
    check(record.get('cpus') == list(range(record['threads'])) and record.get('collector_cpu') == 63,
          'worker/collector placement differs')
    check(tuple(record.get(k) for k in ('duration_ms', 'peak_window_ms', 'peak_settle_ms', 'sample_ms')) ==
          (2000, 300, 300, 10), 'measurement policy differs')
    m = record.get('measurement', {})
    count, wall = m.get('completed'), m.get('wall_ns')
    measurable = unsigned(count) and count > 0 and unsigned(wall) and wall > 0
    rate = count * 1000 / wall if measurable else None
    check(measurable and same(record.get('whole_throughput_ops_s'), rate * 1e6 if rate else None),
          'whole rate differs from positive counts/time')
    workers = m.get('workers', [])
    check(len(workers) == record['threads'] and all(unsigned(w.get('completed')) and w['completed'] > 0 and
          w.get('error') == 0 and w.get('observed_cpu') == w.get('cpu') for w in workers) and
          sum(w.get('completed', 0) for w in workers) == count and
          [w.get('cpu') for w in workers] == record.get('cpus'), 'worker oracle/progress differs')
    check(m.get('collector_error') == 0 and m.get('collector_observed_cpu') == 63 and
          m.get('duration_ns') == 2000000000 and wall == m.get('finished_ns', 0) - m.get('started_ns', 0),
          'collector/measurement interval differs')
    bodies = record.get('jit_bodies')
    check(unsigned(bodies) and measurable and bodies <= count, 'invalid JIT entry counter')
    completions = record.get('jit_completions')
    jit_class = 'RETURNED_JIT' if completions else 'PARTIAL_JIT' if bodies else 'NO_JIT'
    check(m.get('ok') is True and m.get('phase') == 'measure', 'API oracle failed')
    check(record.get('kind') == 'pipebytes' and record.get('query') == 'query' and
          record.get('entries') == 16 and record.get('value_size') == 64, 'pipe workload differs')
    check(record.get('redirected_calls') == count == record.get('jit_eligible_operations'), 'API redirected count differs')
    check(unsigned(completions) and unsigned(bodies) and completions <= bodies, 'invalid returned JIT count')
    check(record.get('jit_completion_probe') is True and record.get('jit_evidence_version') == 2 and
          record.get('entry_abi') == 2 and record.get('warmup') == 48000 and record.get('warmup_ms') == 1000,
          'API warmup/completion instrumentation differs')
    check(record.get('jit_status') == ('PASS' if completions else 'PARTIAL_JIT' if bodies else 'NO_JIT'),
          'API execution classification differs')
    check(record.get('learning_waves') == [], 'unexpected helper learning waves')
    check(record.get('source_identity') == source_id, 'API source identity differs')
    for endpoint in ('check-before', 'check-after'):
        oracle = path / (endpoint + '.json')
        check(oracle.is_file() and read(oracle).get('check') is True, 'missing/failed ' + endpoint)
    physical, tasks = d['mutex_stats'] or {}, d['mutex_tasks'] or {}
    check(d['mutex_aux'] is None, 'unexpected indexed auxiliary state diagnostic')
    check(all(physical.get(k) == 0 for k in ('active_waiters', 'reserved_nodes', 'frame_failure')) and
          tasks.get('active_tasks') == 0, 'nonzero/missing final physical/task drain counters')
    check(unsigned(physical.get('origin_acquires')) and physical.get('origin_acquires') == physical.get('origin_releases'),
          'physical acquisition/release imbalance')
    check(not any(record.get(k, False) for k in ('diagnostic', 'perf_record', 'pmu')), 'plain timing contains profiling')
    return dict(arm=arm, source_commit=commit, source_identity=source_id, collection=group,
                workload=case(record, group), threads=record['threads'], repeat=record['repeat'], name=name,
                session_path=str(path.relative_to(base)), valid=not issues, issues=issues,
                score_eligible=not issues and record.get('score_eligible') is not False,
                execution_status=record.get('execution_status'), drained=record.get('drained'), jit_class=jit_class,
                completed=count, wall_ns=wall, jit_bodies=bodies, jit_completions=completions,
                measured_body_entry_share=bodies / count if measurable and unsigned(bodies) else None,
                measured_returned_jit_share=completions / count if measurable and unsigned(completions) else None,
                observed_whole_mops=rate, whole_session_diagnostics=d,
                identity={key: record.get(key) for key in IDENTITY},
                session_sha256=digest(saved_path) if saved_path.is_file() else None)


def aggregate(rows):
    valid = [row for row in rows if row['score_eligible']]
    classes = {row['jit_class'] for row in valid}
    identities = {json.dumps(row['identity'], sort_keys=True) for row in rows}
    usable = valid if len(classes) == 1 and len(identities) == 1 else []
    total = sum(row['completed'] for row in usable)
    returned = sum(row['jit_completions'] for row in usable) if usable and usable[0]['jit_completions'] is not None else None
    first = rows[0]
    return dict(**{key: first[key] for key in ('arm', 'source_commit', 'source_identity', 'collection', 'workload', 'threads')},
                status='COMPLETE' if len(usable) == 3 else 'MIXED_IDENTITY_OR_CLASSES' if len(classes) > 1 or len(identities) > 1 else 'INCOMPLETE',
                jit_class=next(iter(classes)) if len(classes) == 1 else 'MIXED', planned=3,
                valid=len(valid), repeats=[row['repeat'] for row in usable],
                whole_mops=stats([row['observed_whole_mops'] for row in usable]),
                measured_returned_jit_share=returned / total if total and returned is not None else None,
                measured_body_entry_share=sum(row['jit_bodies'] for row in usable) / total if total else None,
                whole_session_bodies_per_combiner=stats([row['whole_session_diagnostics']['bodies_per_combiner']
                    for row in usable if row['whole_session_diagnostics']['bodies_per_combiner'] is not None]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--arms', nargs='+', required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--allow-partial', action='store_true', help='write an explicitly incomplete progress report without failing')
    args = parser.parse_args()
    if os.uname().release != '6.1.159-kdclobber2':
        raise RuntimeError('run only in the recovery VM')
    base, out = args.base.resolve(), (args.output or args.base).resolve()
    out.mkdir(parents=True, exist_ok=True)
    sessions, collections, issues, arms = [], [], [], []
    if len(set(args.arms)) != len(args.arms) or not set(args.arms) <= {'embedded32', 'old256'}:
        raise ValueError('select distinct embedded32/old256 arms')
    for arm in args.arms:
        if not re.fullmatch(r'[a-z0-9][a-z0-9._-]*', arm):
            raise ValueError('unsafe arm name')
        matrix_path = base / arm / 'matrix.json'
        matrix = read(matrix_path) if matrix_path.is_file() else {}
        arms.append(dict(arm=arm, source_commit=matrix.get('source_commit'), passed=matrix.get('passed'),
                         final_idle=matrix.get('final_idle'), matrix_sha256=digest(matrix_path) if matrix else None))
        if matrix.get('passed') is not True or matrix.get('final_idle') is not True:
            issues.append(arm + ': matrix not complete/idle')
        for group in GROUPS:
            folder = base / arm / group
            records_path = folder / 'records.json'
            if not records_path.is_file():
                issues.append(arm + '/' + group + ': missing records')
                continue
            records = read(records_path)
            source_path = folder / 'source-sha256.json'
            command_path = base / arm / (group + '-command.json')
            source, command = read(source_path), read(command_path)
            source_id = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
            commit = command.get('source_commit')
            local = []
            if command.get('exit_code') != 0 or command.get('version') != arm or not commit or commit != matrix.get('source_commit'):
                local.append('collection command/source receipt differs or incomplete')
            keys = [(case(row, group), row['threads'], row['repeat']) for row in records]
            if len(set(keys)) != len(keys) or set(keys) != expected(group):
                local.append('missing/duplicate/unexpected planned sessions')
            plan = read(folder / 'plan.json')
            planned = {row['name']: row for row in plan}
            if len(planned) != len(plan) or len(records) != len(plan) or any(
                    row['name'] not in planned or any(row.get(key) != value for key, value in planned[row['name']].items())
                    for row in records):
                local.append('record differs from frozen plan')
            production = {name: sha for name, sha in source.items() if name.startswith(('include/', 'kernel_module/'))}
            if 'include/kd_mutex_aux.h' in production or 'kernel_module/kd_mutex_aux.c' in production:
                local.append('obsolete indexed auxiliary production source remains')
            if ('include/kd_mutex_state.h' in production) != (arm == 'embedded32'):
                local.append('embedded-state source identity differs from selected arm')
            if not production or not any(name.endswith('.inc') for name in production):
                local.append('empty production manifest or missing private implementation fragments')
            for name, sha in production.items():
                relative = Path(name)
                if relative.is_absolute() or '..' in relative.parts or not (folder / 'source' / relative).is_file() or digest(folder / 'source' / relative) != sha:
                    local.append('frozen production source differs: ' + name)
            collections.append(dict(arm=arm, collection=group, source_commit=commit, source_identity=source_id,
                sessions=len(records), issues=local, verified_production_files=len(production),
                production_identity=hashlib.sha256(json.dumps(production, sort_keys=True).encode()).hexdigest(),
                records_sha256=digest(records_path), source_manifest_sha256=digest(source_path), command_sha256=digest(command_path)))
            sessions.extend(session_summary(base, folder, row, arm, group, commit, source_id, local) for row in records)
    grouped = defaultdict(list)
    for row in sessions:
        grouped[row['arm'], row['workload'], row['threads']].append(row)
    groups = [aggregate(values) for _, values in sorted(grouped.items())]
    # A complete cohort inside each arm does not establish comparability across
    # arms. Only the declared implementation label may differ here.
    cross_arm = []
    for workers in (8, 60):
        cohort = [row for row in sessions if row['threads'] == workers]
        identities = {json.dumps({key: value for key, value in row['identity'].items()
                                  if key != 'mutex_implementation'}, sort_keys=True) for row in cohort}
        comparable = len(identities) == 1 and {row['arm'] for row in cohort} == set(args.arms)
        cross_arm.append(dict(threads=workers, comparable=comparable,
                              allowed_identity_differences=['mutex_implementation']))
        if not comparable:
            issues.append(f'pipe/{workers}: cross-arm workload/placement/instrumentation identity differs or is missing')
    complete = (not issues and len(collections) == len(args.arms) and len(sessions) == 6 * len(args.arms) and
                len(groups) == 2 * len(args.arms) and all(not row['issues'] for row in collections) and
                all(row['valid'] for row in sessions) and all(row['status'] == 'COMPLETE' for row in groups))
    result = dict(schema=1, created_utc=datetime.now(timezone.utc).isoformat(), complete=complete,
                  arms=args.arms, arm_status=arms, collections=collections, sessions=sessions, groups=groups,
                  cross_arm_identity=cross_arm, issues=issues,
                  notes=['Whole-run Mops/s uses measured operations/time; min/max ranges are three sequential repetitions, not confidence intervals.',
                         'Only plain pipe sessions are collected; JIT entries and matching returns remain separate counters.',
                         'Whole-session diagnostic counters include warmup; they are never used as measured-phase fallback fractions or lifetime authorities.',
                         'The ordinary local live probe separately checks public size/alignment; pipe timing records do not contain object geometry.',
                         'Mixed source, workload, identity or execution classes are not pooled. Full archive, binary and snapshot audits are separate.'])
    (out / 'comparison.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    lines = ['| Arm | Workload | Workers | Whole Mops/s median [min, max] | Execution | Status |',
             '| --- | --- | ---: | ---: | --- | --- |']
    for row in groups:
        value = row['whole_mops']
        text = '—' if not value['n'] else f"{value['median']:.3f} [{value['min']:.3f}, {value['max']:.3f}]"
        lines.append(f"| {row['arm']} | {row['workload']} | {row['threads']} | {text} | {row['jit_class']} | {row['status']} |")
    (out / 'comparison-table.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps(dict(complete=complete, sessions=len(sessions), plain=len(sessions),
                          groups=len(groups), invalid=sum(not row['valid'] for row in sessions), issues=issues, output=str(out))))
    return 0 if complete or args.allow_partial else 1


if __name__ == '__main__':
    raise SystemExit(main())
