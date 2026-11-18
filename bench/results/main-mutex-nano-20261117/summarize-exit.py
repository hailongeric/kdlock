#!/usr/bin/env python3
"""Verify and summarize an exit-tuning archive or its extracted evidence directory."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import median
import tarfile

BOOT = 'fc8104fd-5e0c-406f-b93e-e7c6e6cabf6d'
SOURCE = '18dad4a1c372d77a1155db671d56c148918344da'
KERNEL = '7.0.0-38-kdlocalspin6'
RUNNER = 'fb8004b17d979b2b30590ec84e72b703012a0f534c03e46ed2cc6330a9a039d1'
WIDTHS = (1, 16)
WORKERS = (5, 6, 8, 16, 32)
MODES = [('native', 'default'), ('kd', 'exit-1'), ('tclock', 'default'), ('kd', 'exit-2')]
COUNTERS = set('delegated handback offered sessions plain numa_deferred cl_offered cl_done head_sleep parked handoff stop_plain mode_enter mode_exit hb_frontier hb_acquire hb_miss'.split())
TC = {'delegated', 'batches', 'parks'}
PARAMS = dict(kd_deleg_enter_sleep='3', kd_deleg_enter='5', kd_deleg_exit='2', kd_adapt='Y',
              kd_numa='Y', kd_batch='4096', kd_numa_after='32', kd_spin_queue_phase='Y',
              kd_spin_phase_wait='0', kd_xchg='1', kd_vdown='1', kd_cldemote='3',
              kd_handoff_running='1', kd_api='0', kd_mm='N')
MODULES = ['kd_bench', 'tclock_rwsem_backend_km', 'tclock_rwlock_backend_km',
           'tclock_mutex_backend_km', 'tclock_backend_km']

def require(condition, label):
    if not condition:
        raise ValueError(label)

def row_key(r):
    return (r['phase'], r['round'], r['lines'], r['workers'], r['backend'], r['policy'])

def sequence():
    for rnd in range(3):
        for lines in WIDTHS:
            for w in WORKERS:
                k = (rnd + w) % len(MODES)
                for backend, policy in MODES[k:] + MODES[:k]:
                    for phase in ('exit-tuning-warmup', 'exit-tuning'):
                        yield (phase, rnd, lines, w, backend, policy)

def verify(r):
    key = row_key(r)
    w, lines, backend, policy = r['workers'], r['lines'], r['backend'], r['policy']
    ops, writes, elapsed = r['worker_ops'], r['worker_writes'], r['elapsed_ns']
    require(r['ok'] is True and (r['boot_id'], r['kernel'], r['source']) == (BOOT, KERNEL, SOURCE), (key, 'identity'))
    require(len(ops) == len(writes) == w and min(ops) > 0 and ops == writes and
            sum(ops) == r['ops'] == r['writes'] and min(ops) == r['min_worker_ops'] and
            max(ops) == r['max_worker_ops'], (key, 'worker counts'))
    require(r['torn_reads'] == 0 and r['sum_delta'] == r['writes'] * lines and elapsed > 0 and
            math.isclose(r['mops'], 1000 * r['ops'] / elapsed, rel_tol=1e-12), (key, 'data and rate'))
    require(r['post'] == 256 and r['write_pct'] == 100 and r['first_cpu'] == (4 if w == 32 else 0)
            and r['delegation'] == 1, (key, 'workload'))
    expected_exit = '1' if backend == 'kd' and policy == 'exit-1' else '2'
    require(r['parameters'] == {**PARAMS, 'kd_deleg_exit': expected_exit}, (key, 'parameters'))
    kd, tc, recorded = r['kd_delta'], r['tc_delta'], r['execution_counts']
    require(set(recorded) == COUNTERS and all(kd[k] == v for k, v in recorded.items())
            and set(tc) == TC and all(type(x) is int and x >= 0 for x in (*kd.values(), *tc.values())),
            (key, 'counter schema or delta'))
    require(backend == 'tclock' or not any(tc.values()), (key, 'unexpected TCLock activity'))
    require(backend == 'kd' or not any(kd.values()), (key, 'unexpected KD activity in controls'))
    if r['phase'] in ('exit-tuning', 'exit-tuning-warmup'):
        require(r['family'] == 'mutex' and r['ms'] == (250 if r['phase'].endswith('warmup') else 1000), key)
    else:
        require(policy == 'default' and lines == 1, key)
        if r['phase'] == 'learning':
            require((backend, w, r['ms'], r['family']) == ('kd', 32, 600, 'mutex'), key)
        else:
            require(r['family'] in ('mix', 'mutex_cl'), key)
            if r['phase'] == 'functional-control':
                require((backend, w, r['ms'], r['round']) == ('native', 8, 400, 0), key)
            else:
                require(r['phase'] == 'functional-kd' and 0 <= r['round'] < 4 and backend == 'kd'
                        and w == (8 if r['round'] == 0 else 32) and r['ms'] == 750, key)

def summary(rows):
    rates = [r['mops'] for r in rows]
    return {'rates': rates, 'median': median(rates), 'range': [min(rates), max(rates)],
            'ops': sum(r['ops'] for r in rows), 'elapsed_ns': sum(r['elapsed_ns'] for r in rows),
            'min_worker_ops': min(r['min_worker_ops'] for r in rows),
            **{field: {k: sum(r[field][k] for r in rows) for k in rows[0][field]}
               for field in ('kd_delta','tc_delta')}}

def compare(a,b):
    ratios = [100 * (x / y - 1) for x, y in zip(a['rates'], b['rates'])]
    return {'change_between_medians_pct': 100 * (a['median'] / b['median'] - 1),
            'paired_round_pct': ratios, 'paired_median_pct': median(ratios),
            'paired_range_pct': [min(ratios), max(ratios)], 'wins': sum(g > 0 for g in ratios),
            'ties': sum(g == 0 for g in ratios)}

def analyze(read):
    def load(name): return json.loads(read(name))
    identity, cleanup, result = map(load, ('identity.json','cleanup.json','result.json'))
    require((identity['boot_id'], identity['source'], identity['kernel']) == (BOOT, SOURCE, KERNEL)
            and identity['parameters'] == PARAMS and identity['tuning_workers'] == list(WORKERS)
            and identity['exit_thresholds'] == [1, 2] and identity['varied_parameter'] == 'kd_deleg_exit'
            and identity['cpus'] == [38, 39] and identity['post'] == 256, 'campaign identity')
    require(cleanup['boot_id'] == result['boot_id'] == BOOT and cleanup['daemon_rc'] == 0
            and cleanup['initial_params'] == cleanup['final_params'] == PARAMS
            and not cleanup['cleanup_errors'] and cleanup['modules'] == identity['initial_modules']
            and cleanup['taint'] == identity['taint'] and cleanup['unloaded'] == MODULES
            and result['status'] == 'completed' and not result['error'] and not result['cleanup_errors'],
            'runner completion or cleanup')
    require(load('api.json')['failed_checks'] == 0 and load('stats-after.json')['delegation'] == 0
            and load('measurements-complete.json')['exit_tuning_rows'] == 120, 'API checks and final state')
    hashes = load('verified-inputs.json')
    require(RUNNER in hashes.values() and len(hashes) == 141, 'signed artifacts, sources and runner')
    provider=load('mutex-provider.json')
    require(int(provider['target_lock'], 0) == int(provider['kd_bench:t_mutex'], 16)
            and int(provider['batch_size']) == 1024, 'mutex target and batch')
    dmesg = read('dmesg-after.txt')
    require(not re.search(r'BUG:|WARNING:|Oops:|soft lockup|hard LOCKUP|Kernel panic|general protection fault|blocked for more than', dmesg, re.I), 'kernel messages')
    rows = [json.loads(line) for line in read('points.jsonl').splitlines()]
    for r in rows: verify(r)
    grid = [r for r in rows if r['phase'].startswith('exit-tuning')]
    require([row_key(r) for r in grid] == list(sequence()), 'timing coverage, order or duplicates')
    learning = [r for r in rows if r['phase'] == 'learning']
    require(1 <= len(learning) <= 8 and [r['round'] for r in learning] == list(range(len(learning)))
            and load('learning.json')['delegated_by_attempt'] == [r['kd_delta']['delegated'] for r in learning],
            'learning evidence')
    checks = load('checks.json')
    functional = {}
    for family in ('mix','mutex_cl'):
        ctrl = [r for r in rows if r['phase'] == 'functional-control' and r['family'] == family]
        kd = [r for r in rows if r['phase'] == 'functional-kd' and r['family'] == family]
        require(len(ctrl) == 1 and 2 <= len(kd) <= 4 and [r['round'] for r in kd] == list(range(len(kd)))
                and checks[family] == [r['execution_counts'] for r in kd], 'functional evidence '+family)
        functional[family] = summary(kd)['kd_delta']
    cells = []
    for w in WORKERS:
        for width in WIDTHS:
            by_mode = {}
            for backend, policy in MODES:
                subset = [r for r in grid if r['phase'] == 'exit-tuning' and r['workers'] == w
                          and r['lines'] == width and r['backend'] == backend and r['policy'] == policy]
                by_mode[policy if backend == 'kd' else backend] = summary(subset)
            comparisons = {a+'_vs_'+b:compare(by_mode[a],by_mode[b])
                           for a,b in [('exit-1','exit-2'),('exit-1','native'),('exit-1','tclock'),
                                       ('exit-2','native'),('exit-2','tclock')]}
            cells.append({'workers':w,'lines':width,'modes':by_mode,'comparisons':comparisons})
    return {'identity':identity,'timing_grid_validated':True,'phase_counts':dict(Counter(r['phase'] for r in rows)),
            'functional_counts':functional,'cells':cells,'runner_sha256':RUNNER}

def markdown(report):
    lines=['# Mutex exit threshold comparison', '',
           'Each rate is the median of three 1 s runs in Mops/s. Matched rounds use 250 ms warmups, post=256 and enter=3. Native and TCLock ran at exit=2. The change column compares medians. The range and win count use the three paired round changes.', '',
           '| Workers | Lines | Native | TCLock | KD exit 2 | KD exit 1 | Change | Paired range | Wins |',
           '|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for c in report['cells']:
        m=c['modes']; d=c['comparisons']['exit-1_vs_exit-2']; lo,hi=d['paired_range_pct']
        rates=' | '.join(f"{m[k]['median']:.3f}" for k in ('native','tclock','exit-2','exit-1'))
        lines.append(f"| {c['workers']} | {c['lines']} | {rates} | {d['change_between_medians_pct']:+.2f}% | {lo:+.2f}% to {hi:+.2f}% | {d['wins']}/3 |")
    lines += ['', 'Counts sum the three timed rounds for each cell. Each pair of KD rows shares the same three TCLock control runs. To reproduce the tables and export individual rates, all counter deltas and paired comparisons with each control, run `python3 summarize-exit.py raw/main-mutex-exit01.tar.gz --json exit-derived.json` from this directory.', '',
              '| Workers | Lines | KD exit | Mode enters | Mode exits | Offered | Delegated | Handbacks | TC delegated | TC batches | TC parks |',
              '|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for c in report['cells']:
        for mode in ('exit-2','exit-1'):
            m=c['modes']; kd=m[mode]['kd_delta']; tc=m['tclock']['tc_delta']
            nums=[c['workers'],c['lines'],mode[-1],*[kd[k] for k in ('mode_enter','mode_exit','offered','delegated','handback')],
                  *[tc[k] for k in ('delegated','batches','parks')]]
            lines.append('| '+' | '.join(map(str,nums))+' |')
    return '\n'.join(lines)+'\n'

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--json', type=Path)
    parser.add_argument('--markdown', type=Path)
    args=parser.parse_args()
    if args.evidence.is_dir():
        directory=args.evidence/'evidence' if (args.evidence/'evidence').is_dir() else args.evidence
        result=analyze(lambda name:(directory/name).read_text())
    else:
        with tarfile.open(args.evidence,'r:*') as archive:
            result=analyze(lambda name:archive.extractfile('evidence/'+name).read().decode())
        result['archive_sha256']=hashlib.sha256(args.evidence.read_bytes()).hexdigest()
    if args.json: args.json.write_text(json.dumps(result,indent=2)+'\n')
    if args.markdown: args.markdown.write_text(markdown(result))
    else: print(markdown(result),end='')
