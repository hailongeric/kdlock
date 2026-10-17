#!/usr/bin/env python3
"""Read-only replay of the 2026-10-11 real-API campaign, including failed pilots.

Run after measurement; print a JSON receipt. Never load a module or change a run.
The argument is the directory containing real-sync-*-v* run directories.
"""
import ast
from collections import Counter
import datetime
import hashlib
import json
from pathlib import Path
import re
import runpy
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def require(ok, message):
    if not ok:
        raise ValueError(message)


def manifest(run, name, root, binary=False):
    path = run / name
    if not path.exists():
        return None
    items = read(path)
    for relative, expected in items.items():
        if binary:
            expected = expected['sha256']
        require(sha(run / root / relative) == expected, f'{run.name}: hash mismatch: {relative}')
    return dict(sha256=sha(path), checked_files=len(items))


def audit(run):
    receipt = dict(source=manifest(run, 'source-sha256.json', 'source'),
                   kernel=manifest(run, 'kernel-inputs-sha256.json', 'kernel-inputs'),
                   binary=manifest(run, 'binaries.json', 'build', True),
                   environment=read(run / 'environment.json'))
    require('nopvspin' in receipt['environment']['cmdline'].split(), 'wrong boot policy')
    audit_context = runpy.run_path(str(run / 'source/bench/tclock_compare/context_audit.py'))['audit']
    context_audits = []
    for audit_path in sorted(run.glob('tclock-*-context-audit.json')):
        family = audit_path.name.split('-')[1]
        replay = audit_context((run / f'tclock-{family}-assembly.txt').read_text(), family)
        require(read(audit_path) == replay, 'TCLock emitted-context audit differs')
        context_audits.append(family)
    receipt['emitted_context_audits_recomputed'] = context_audits
    for imports in run.glob('imports-*.txt'):
        require('__ubsan_' not in imports.read_text(), 'timed module imports UBSAN')
    if not (run / 'records.json').exists():
        require('screen' in run.name, f'{run}: missing final records')
        receipt['status'] = 'BUILD_OR_CAPTURE_FAILED_BEFORE_SESSION_PLAN'
        return receipt
    records = read(run / 'records.json')
    plan = read(run / 'plan.json')
    require([r['name'] for r in records] == [s['name'] for s in plan], 'plan/record mismatch')
    peak = runpy.run_path(str(run / 'source/bench/spin_cacheline/peak.py'))['analyze_peak']
    runtime = ast.parse((run / 'source/bench/spin_cacheline/bench_runtime.py').read_text())
    fault_node = next(n for n in runtime.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'FAULT' for t in n.targets))
    faults = re.compile(ast.literal_eval(fault_node.value.args[0]), re.I)
    accepted = []
    for r in records:
        folder = run / r['name']
        if r['execution_status'] != 'NOT_RUN':
            require(read(folder / 'session.json') == r, 'records/session mismatch')
        if r['execution_status'] != 'OK' or not r.get('drained'):
            continue
        accepted.append(r)
        require(not faults.search((folder / 'kernel.log').read_text()), 'accepted kernel fault')
        for when in ('before', 'after'):
            require(read(folder / f'check-{when}.json')['check'] is True, 'oracle failed')
        warm = read(folder / 'warmup.json')
        require(warm['ok'] and len(warm['workers']) == r['threads'], 'warmup failed')
        require(all(w['completed'] >= r['warmup'] and w['error'] == 0
                    and w['cpu'] == w['observed_cpu']
                    and w['finished_ns'] >= warm['started_ns'] + r['warmup_ms'] * 1000000
                    for w in warm['workers']), 'warmup bounds/affinity failed')
        raw = read(folder / 'measure.json')
        m = r['measurement']
        require({k: v for k, v in m.items() if k != 'peak'} == raw, 'raw measurement changed')
        require(m['ok'] and m['completed'] == sum(w['completed'] for w in m['workers']), 'bad total')
        require(m['wall_ns'] == max(w['finished_ns'] for w in m['workers']) - m['started_ns'], 'bad wall time')
        require(all(w['completed'] > 0 and w['error'] == 0 and w['cpu'] == w['observed_cpu']
                    for w in m['workers']), 'bad worker progress/affinity')
        require(r['whole_throughput_ops_s'] == m['completed'] * 1e9 / m['wall_ns'], 'bad whole rate')
        expected_peak = peak(raw, r)
        require(m['peak'] == expected_peak and r['peak_throughput_ops_s'] == expected_peak['throughput_ops_s'],
                'bad peak')
        eligible = m['writes'] if r['kind'] == 'utsname' else m['completed']
        if r['kind'] == 'utsname':
            require(m['reads'] + m['writes'] == m['completed'], 'bad rw accounting')
        # The earliest pipe pilot predates stored derived share fields.
        # Derive them from raw totals there; final runs must include both.
        require(0 <= r['jit_bodies'] <= eligible and r.get('jit_eligible_operations', eligible) == eligible
                and r.get('jit_share', r['jit_bodies'] / eligible) == r['jit_bodies'] / eligible,
                'bad JIT accounting')
        if '-final-' in run.name:
            require('jit_eligible_operations' in r and 'jit_share' in r, 'missing final JIT accounting')
        require(r['redirected_calls'] == (0 if r['arm'] == 'stock' else m['completed']), 'bad hook count')
        if 'source_quiescent' in r:
            require(r['source_quiescent'] is True, 'RW source not idle')
        if r['arm'] == 'kdlock':
            require(r['retired'] == dict(state=2, modules=0, frames=0, writers=0), 'retirement not exact')
            require(r['jit_status'] == ('PASS' if r['jit_bodies'] else 'NO_JIT'), 'bad JIT classification')
            pub = r['publication']
            entry = pub['entry']
            expected_abi = r.get('entry_abi', {'spin': 1, 'mutex': 2, 'rwlock': 3}[r['lock_kind']])
            require(entry['status'] == 0 and entry['code'] != 0 and entry['pid'] == 0
                    and entry['entry_abi'] == expected_abi, 'bad publication')
            require(r['entry_range'][0] <= entry['entry'] < r['entry_range'][1], 'wrong root')
            require(len(r['registry_after']) == 1 and all(
                r['registry_after'][0][key] == entry[key]
                for key in ('entry', 'code', 'entry_abi', 'lock_kind', 'status')),
                'published entry changed during measurement')
            asm = folder / 'workspace/daemon' / hex(entry['entry']) / str(entry['tgid']) / 'asm'
            for filename, expected in pub['images'].items():
                require(sha(asm / filename) == expected, 'JIT inspection image changed')
        if r['arm'] == 'tclock' and r['lock_kind'] == 'mutex':
            require(type(r['tclock_delegation']) is int and 0 <= r['tclock_delegation'] <= m['completed'],
                    'bad TCLock delegation count')
        for suffix in ('source', 'tc', 'kd'):
            command = folder / f'unload-{suffix}.log.command.json'
            if command.exists():
                # command() records the invocation and raises on nonzero exit;
                # an OK/drained session is the successful-return observation.
                require(read(command)['argv'][0] == 'rmmod', 'wrong unload command')
    final = '-final-' in run.name
    if final:
        require(len(accepted) == len(records), 'incomplete final run')
        require(receipt['source'] and receipt['kernel'] and receipt['binary'], 'missing final manifest')
        require(all(r['warmup'] == 48000 and r['warmup_ms'] == 1000 and r['duration_ms'] == 2000
                    for r in records), 'different final timing')
        groups = Counter(tuple(r[k] for k in ('kind', 'query', 'entries', 'value_size', 'threads', 'arm'))
                         for r in records)
        require(set(groups.values()) == {3}, 'final point has other than three rounds')
        if any(r['kind'] == 'utsname' for r in records):
            require(all(r.get('source_quiescent') is True for r in records if r['arm'] != 'stock'),
                    'missing final RW drain observation')
        summary_path = run / 'report/summary.json'
        if summary_path.exists():
            summarize = runpy.run_path(str(run / 'source/bench/real_api/report.py'))['summarize']
            require(read(summary_path) == summarize(records), 'report changed from raw data')
            receipt['report_recomputed'] = True
    kd = [r for r in accepted if r['arm'] == 'kdlock']
    tc = [r for r in accepted if r['arm'] == 'tclock' and r['lock_kind'] == 'mutex']
    receipt.update(status='AUDITED', final=final, records_sha256=sha(run / 'records.json'),
                   planned=len(records), accepted=len(accepted),
                   statuses=dict(Counter(r['execution_status'] for r in records)),
                   excluded=[{k: r.get(k) for k in ('name', 'execution_status', 'drained', 'error', 'cleanup_error')}
                             for r in records if r['execution_status'] not in ('OK', 'NOT_RUN')],
                   timed_operations=sum(r['measurement']['completed'] for r in accepted),
                   kd_sessions=len(kd), kd_jit_positive=sum(r['jit_bodies'] > 0 for r in kd),
                   kd_jit_bodies=sum(r['jit_bodies'] for r in kd),
        kd_eligible_operations=sum(r['measurement']['writes'] if r['kind'] == 'utsname'
                                   else r['measurement']['completed'] for r in kd),
                   tclock_mutex_delegated=sum(r['tclock_delegation'] for r in tc),
                   raw_measurements_peaks_oracles_and_drain_recomputed=True)
    return receipt


if __name__ == '__main__':
    run = Path(sys.argv[1])
    print(json.dumps(dict(checked_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                         verifier_sha256=sha(Path(__file__)), audit=audit(run)), indent=2, sort_keys=True))
