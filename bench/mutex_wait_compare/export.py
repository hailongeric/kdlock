#!/usr/bin/env python3
"""Audit saved spin/blocking matrix evidence and export every measurement.

Read-only with respect to the run. No module, daemon or benchmark is executed.
Plots require matplotlib; all verification and tables use the standard library.
"""
import argparse
import ast
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import runpy
import statistics

THREADS = [1, 8, 16, 32, 48, 60]
BUILD_ID = '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960'
ARMS = ('stock', 'native', 'tclock', 'kd-spin', 'kd-blocking')
LABELS = dict(zip(ARMS, ('Stock', 'Native', 'TCLock', 'KD spin', 'KD blocking')))
COLORS = dict(zip(ARMS, ('#999999', '#333333', '#0072b2', '#d55e00', '#009e73')))
SUBJECTS = {
    f'{kind}-{payload}' for kind in ('spin', 'mutex')
    for payload in ('cacheline-c01', 'cacheline-c08', 'cacheline-c16', 'rcuht')
} | {
    f'rwlock-{payload}-w{percent:02d}'
    for payload in ('cacheline-c01', 'cacheline-c02', 'cacheline-c04', 'cacheline-c08', 'cacheline-c16', 'rcuht')
    for percent in (1, 20)
} | {
    f'{kind}-{query}-n{count}-v64' for kind, queries, counts in (
        ('pipebytes', ['query'], [16, 128]), ('pipecap', ['query'], [16]),
        ('seek', ['set', 'end'], [16]), ('ofd', ['tail'], [16, 128]),
        ('setfd', ['toggle'], [16, 512]), ('utsname', ['host', 'domain'], [20]))
    for query in queries for count in counts
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


def csv_write(path, rows):
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows({k: json.dumps(v) if isinstance(v, (list, dict)) else v
                         for k, v in row.items()} for row in rows)


def subject(row):
    if 'kind' in row:
        return f"{row['kind']}-{row['query']}-n{row['entries']}-v{row['value_size']}"
    result = row['lock_kind'] + '-' + row['workload']
    if row['workload'] == 'cacheline':
        result += f"-c{row['cachelines']:02d}"
    if row['lock_kind'] == 'rwlock':
        result += f"-w{row['write_percent']:02d}"
    return result


def backend(row):
    if row['arm'] != 'kdlock':
        return row['arm']
    mode = row['mutex_wait_mode']
    require(mode in ('spin', 'blocking'), 'unknown KD policy')
    return 'kd-' + mode


def check_peak(row):
    """Recompute the peak selection independently of the runner's peak.py."""
    m = row['measurement']
    start = max(w['active_started_ns'] for w in m['workers']) + m['peak_settle_ns']
    end = min(m['deadline_ns'], *(w['kernel_finished_ns'] for w in m['workers']))
    eligible = [(i, s) for i, s in enumerate(m['samples'])
                if s['started_ns'] >= start and s['finished_ns'] <= end]
    best = None
    for i, (first_index, first) in enumerate(eligible):
        for last_index, last in eligible[i + 1:]:
            elapsed = last['finished_ns'] - first['started_ns']
            if elapsed < m['peak_window_ns']:
                continue
            deltas = [b - a for a, b in zip(first['completed'], last['completed'])]
            if min(deltas) > 0:
                total = sum(deltas)
                if best is None or total * best[1] > best[0] * elapsed:
                    best = (total, elapsed, first_index, last_index, deltas)
            break
    peak = m['peak']
    require(best is not None and best[0] == peak['completed'] and best[1] == peak['elapsed_ns']
            and best[2] == peak['start_sample_index'] and best[3] == peak['end_sample_index']
            and best[4] == peak['worker_completed']
            and math.isclose(best[0] * 1e9 / best[1], peak['throughput_ops_s'], rel_tol=1e-12),
            'raw peak differs: ' + row['name'])


def check_execution(row):
    jit = row.get('jit_bodies', 0)
    if row['arm'] != 'kdlock':
        require(jit == 0 and row['execution_status'] == 'OK', 'baseline claims JIT or failed execution')
        return
    api = 'kind' in row
    expected = ('PASS' if api or row['lock_kind'] == 'rwlock' else 'JIT') if jit else 'NO_JIT'
    require(row['jit_status'] == expected, 'returned-body classification differs')
    required = row.get('require_jit', False)
    if not api and row['lock_kind'] != 'rwlock':
        # This matrix has no disabled, functional or two/three-worker arms.
        required = row['threads'] > 1 and (row['threads'] >= 20 or row['lock_kind'] == 'mutex')
        require(row['jit_acceptance'] == ('PASS' if jit else 'NO_JIT'), 'JIT acceptance differs')
    require(row['execution_status'] == ('NO_JIT' if required and not jit else 'OK'),
            'execution verdict does not match returned-body requirement')


def audit_group(folder, group, approved, spin_limit, *, allow_not_run=False):
    counts = Counter()
    manifest = read(folder / 'source-sha256.json')
    for relative, expected in manifest.items():
        require(approved[relative] == expected and sha(folder / 'source' / relative) == expected,
                'source differs: ' + relative)
        counts['source_hashes'] += 1
    api = group['suite'] == 'api'
    binary_manifest = 'binaries.json' if api else 'binary-sha256.json'
    for name, expected in read(folder / binary_manifest).items():
        if api:
            path, expected = folder / 'build' / name, expected['sha256']
        else:
            _, marker, relative = name.partition('/' + folder.name + '/')
            path = folder / relative if marker else folder / 'binaries' / Path(name).name
        require(sha(path) == expected, 'binary differs: ' + name)
        counts['binary_hashes'] += 1
    kernel_manifest = folder / 'kernel-inputs-sha256.json'
    if kernel_manifest.exists():
        for relative, expected in read(kernel_manifest).items():
            require(sha(folder / 'kernel-inputs' / relative) == expected, 'kernel input differs')
            counts['kernel_input_hashes'] += 1
    environment = read(folder / 'environment.json')
    identity = folder / ('kernel-identity.json' if (folder / 'kernel-identity.json').exists() else 'baseline.json')
    identity = read(identity)
    require(identity['ok'] and identity['running_build_id'] == BUILD_ID, 'kernel identity differs')
    require({'nopvspin', 'nokaslr'} <= set(environment['cmdline'].split()), 'boot arguments differ')
    for imports in folder.glob('imports-*.txt'):
        require('__ubsan_' not in imports.read_text(), 'timed module imports UBSAN')
    specs, records = read(folder / 'plan.json'), read(folder / 'records.json')
    require(len(records) == group['expected'] and [r['name'] for r in records] == [s['name'] for s in specs],
            'group plan/record mismatch: ' + folder.name)
    replay = runpy.run_path(str(folder / 'source/bench/spin_cacheline/peak.py'))['analyze_peak']
    rw_validate = None
    if not api and group['family'] == 'rwlock':
        rw_validate = runpy.run_path(str(folder / 'source/bench/rwlock_compare/oracle.py'))['validate']
    context = runpy.run_path(str(folder / 'source/bench/tclock_compare/context_audit.py'))['audit']
    for path in folder.glob('*context-audit.json'):
        # API uses a family suffix; micro runners have one family per group.
        family = path.name.split('-')[1] if api else group['family']
        assembly = folder / (f'tclock-{family}-assembly.txt' if api else
                             'tclock-context.txt' if family == 'rwlock' else 'tclock-backend.txt')
        require(read(path) == context(assembly.read_text(), family), 'TCLock emitted context differs')
        counts['tclock_context_audits'] += 1
    runtime = ast.parse((folder / 'source/bench/spin_cacheline/bench_runtime.py').read_text())
    fault_node = next(n for n in runtime.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'FAULT' for t in n.targets))
    faults = re.compile(ast.literal_eval(fault_node.value.args[0]), re.I)
    samples = []
    for spec, r in zip(specs, records):
        path = folder / r['name']
        require(all(r[k] == v for k, v in spec.items()), 'session changed planned parameters')
        if allow_not_run and r['execution_status'] == 'NOT_RUN':
            require(not r['drained'] and not (path / 'session.json').exists(),
                    'NOT_RUN contradicts saved execution')
            counts['not_run'] += 1
            continue
        saved = read(path / 'session.json')
        require(all(k in r and r[k] == v for k, v in saved.items()), 'saved session differs')
        require(r['drained'] and r['execution_status'] in ('OK', 'NO_JIT'), 'undrained/failed session')
        require(r['threads'] in THREADS and r['cpus'] == list(range(r['threads']))
                and r['collector_cpu'] == 63 and r['duration_ms'] == 2000, 'placement/timing differs')
        require(not faults.search((path / 'kernel.log').read_text()), 'kernel fault in accepted sample')
        m = r['measurement']
        require(m.get('ok') if api else m['data_ok'] and m['complete'], 'failed business result')
        raw = read(path / 'measure.json')
        require({k: v for k, v in m.items() if k != 'peak'} == raw, 'raw measurement differs')
        require(m['peak'] == (rw_validate(raw, r) if rw_validate else replay(raw, r)), 'frozen peak replay differs')
        check_peak(r)
        counts['recomputed_peaks'] += 1
        workers = m['workers']
        require(len(workers) == r['threads'] and [w['cpu'] for w in workers] == r['cpus'],
                'worker cohort differs')
        require(m['completed'] == sum(w['completed'] for w in workers)
                and m['wall_ns'] == m['finished_ns'] - m['started_ns']
                and m['finished_ns'] >= max(w['finished_ns'] for w in workers), 'wrong totals')
        if api or r['lock_kind'] != 'rwlock':
            require(m['finished_ns'] == max(w['finished_ns'] for w in workers), 'wrong joined finish')
        require(all(w['completed'] > 0 and w['cpu_ns'] > 0 and w['error'] in (0, None)
                    and w['cpu'] == w['observed_cpu']
                    for w in workers), 'worker error/no progress')
        if api:
            for when in ('before', 'after'):
                require(read(path / f'check-{when}.json')['check'] is True, 'API oracle failed')
            warm = read(path / 'warmup.json')
            require(warm['ok'] and r['warmup'] == 48000 and r['warmup_ms'] == 1000
                    and all(w['completed'] >= 48000 and w['error'] == 0
                            and w['cpu'] == w['observed_cpu']
                            and w['finished_ns'] >= warm['started_ns'] + 1000000000
                            for w in warm['workers']), 'warmup failed')
            require(r['redirected_calls'] == (0 if r['arm'] == 'stock' else m['completed']), 'wrong hook count')
            if r['kind'] == 'utsname':
                require(m['reads'] + m['writes'] == m['completed'], 'wrong UTS read/write totals')
                if r['arm'] != 'stock':
                    require(r['source_quiescent'] is True, 'UTS source did not drain')
        elif not rw_validate:
            require(m['schema'] == 2 and m['measurement_mode'] == 'duration'
                    and m['workload'] == r['workload'] and m['cachelines'] == r['cachelines']
                    and m['threads'] == r['threads'] and m['iterations'] == 0,
                    'timed workload identity differs')
            before, after = m['before'], m['after']
            require(len(before) == len(after) == 16, 'wrong payload shape')
            if r['workload'] == 'rcuht':
                require(m['hash_integrity_ok'] and after[0] - before[0] == m['completed']
                        and before[0] == sum(before[1:4]) and after[0] == sum(after[1:4])
                        and all(a >= b for a, b in zip(after, before))
                        and not any(before[4:] + after[4:]), 'hash oracle differs')
            else:
                require(all(a - b == (m['completed'] if i < r['cachelines'] else 0)
                            for i, (b, a) in enumerate(zip(before, after))), 'payload delta differs')
        eligible = m['writes'] if r['lock_kind'] == 'rwlock' else m['completed']
        jit = r.get('jit_bodies', 0)
        require(0 <= jit <= eligible, 'JIT count exceeds operations')
        check_execution(r)
        if 'jit_before' in r:
            require(r['jit_after'] - r['jit_before'] == jit, 'JIT counter delta differs')
        if type(r.get('tclock_delegation')) is int:
            require(0 <= r['tclock_delegation'] <= m['completed'], 'TCLock delegation exceeds operations')
        if r['arm'] == 'tclock' and not api and r['lock_kind'] == 'mutex':
            require(r['delegated_bodies'] == r['tclock_after']['delegated'] - r['tclock_before']['delegated']
                    and 0 <= r['delegated_bodies'] <= m['completed'], 'TCLock returned-batch delta differs')
        if r['arm'] == 'tclock' and 'tclock_drained' in r:
            require(r['tclock_drained']['quiescent'] == 1, 'TCLock context did not drain')
        if r['arm'] == 'kdlock':
            policy = r['mutex_wait_mode']
            require(policy in ('spin', 'blocking') and
                    (group['mode'] == 'both' or policy == group['mode'])
                    and r['mutex_spin_limit'] == spin_limit, 'KD policy differs')
            params = r['parameters']
            require(params['mutex_blocking'] == ('Y' if policy == 'blocking' else 'N')
                    and int(params['mutex_spin_limit']) == spin_limit, 'actual module policy differs')
            require(r['retired'] == dict(state=2, modules=0, frames=0, writers=0), 'incomplete retirement')
            publication = r.get('publication', r.get('published_before'))
            if 'published_before' in r:
                require(publication == r['published_after'], 'publication changed')
            require(publication is not None, 'missing published JIT evidence')
            entry = publication['entry']
            require(entry['status'] == 0 and entry['code'] and entry['pid'] == 0
                    and entry['entry_abi'] == {'spin': 1, 'mutex': 2, 'rwlock': 3}[r['lock_kind']],
                    'publication ABI/status differs')
            if 'entry_range' in r:
                require(r['entry_range'][0] <= entry['entry'] < r['entry_range'][1], 'entry outside body')
            if api:
                require(len(r['registry_after']) == 1 and all(r['registry_after'][0][key] == entry[key]
                        for key in ('entry', 'code', 'entry_abi', 'lock_kind', 'status')), 'API publication changed')
            images = path / 'workspace/daemon' / hex(entry['entry']) / str(entry['tgid']) / 'asm'
            for name, expected in publication['images'].items():
                require(sha(images / name) == expected, 'JIT image differs')
                counts['jit_image_hashes'] += 1
            if r['lock_kind'] != 'rwlock':
                require(r['mutex_wait_delta'] == {k: v - r['mutex_wait_before'][k]
                    for k, v in r['mutex_wait_after'].items()} and
                    all(v >= 0 for v in r['mutex_wait_delta'].values()), 'wait observations differ')
        whole = m['completed'] * 1e9 / m['wall_ns']
        require(math.isclose(r.get('whole_throughput_ops_s', whole), whole, rel_tol=1e-12), 'whole rate differs')
        cpu_ns = sum(w['cpu_ns'] for w in workers)
        if 'worker_cpu_ns' in m:
            require(m['worker_cpu_ns'] == cpu_ns, 'CPU accounting differs')
        row = dict(subject=subject(r), suite=group['suite'], lock_kind=r['lock_kind'],
            group=folder.name, name=r['name'], threads=r['threads'], backend=backend(r), repeat=r['repeat'],
            execution_status=r['execution_status'], accepted=r['execution_status'] == 'OK',
            drained=True, jit_bodies=jit, jit_eligible_ops=eligible,
            execution_type=('ACTUAL_JIT' if jit else 'NO_JIT') if r['arm'] == 'kdlock' else 'BASELINE',
            jit_share=jit / eligible if eligible else 0, completed=m['completed'], wall_ns=m['wall_ns'],
            whole_ops_s=whole, peak_ops_s=m['peak']['throughput_ops_s'], cpu_ns_per_op=cpu_ns / m['completed'],
            min_worker_share=min(w['completed'] for w in workers) / m['completed'],
            max_worker_share=max(w['completed'] for w in workers) / m['completed'],
            post_work_rounds=None if api else r.get('post_work_rounds', 64),
            mutex_spin_limit=r.get('mutex_spin_limit'),
            tclock_delegated=r.get('tclock_delegation', r.get('delegated_bodies')) if r['arm'] == 'tclock' else None,
            **r.get('mutex_wait_delta', {}))
        samples.append(row)
    return samples, dict(counts), dict(environment=environment, kernel_identity=identity,
        records_sha256=sha(folder / 'records.json'), source_manifest_sha256=sha(folder / 'source-sha256.json'),
        binary_manifest_sha256=sha(folder / binary_manifest))


def aggregate(rows, *, split_execution=False):
    """Keep both policy and subject in the key; never silently pool rounds."""
    groups = defaultdict(list)
    for row in rows:
        groups[(row['subject'], row['threads'], row['backend'],
                row['execution_type'] if split_execution else 'ALL')].append(row)
    output = []
    for (name, threads, arm, execution), samples in sorted(groups.items()):
        require(len(samples) == len({r['repeat'] for r in samples}) and
                (split_execution or len(samples) == 3 and {r['repeat'] for r in samples} == {0, 1, 2}),
                'need distinct rounds; complete aggregates require three')
        require(len({r['mutex_spin_limit'] for r in samples}) == 1, 'mixed spin limits')
        good = [r for r in samples if r['accepted']]
        row = dict(subject=name, threads=threads, backend=arm, lock_kind=samples[0]['lock_kind'],
            suite=samples[0]['suite'], rounds=len(samples), execution_filter=execution,
            accepted_rounds=len(good), complete=len(good) == 3,
            jit_rounds=sum(r['jit_bodies'] > 0 for r in good),
            jit_bodies=sum(r['jit_bodies'] for r in good),
            jit_eligible_ops=sum(r['jit_eligible_ops'] for r in good),
            execution_types=dict(Counter(r['execution_type'] for r in good)),
            mutex_spin_limit=samples[0]['mutex_spin_limit'])
        for metric in ('whole_ops_s', 'peak_ops_s', 'cpu_ns_per_op'):
            values = [r[metric] for r in good]
            for label, fn in (('min', min), ('median', statistics.median), ('max', max)):
                row[metric + '_' + label] = fn(values) if values else None
            row[metric + '_spread_pct'] = 100 * (max(values) - min(values)) / statistics.median(values) if values else None
        for key in ('result_schedule_calls', 'result_wakes', 'gate_wait_calls'):
            values = [r[key] for r in good if key in r]
            row[key + '_total'] = sum(values) if good and len(values) == len(good) else None
        output.append(row)
    return output


def comparisons(stats):
    points = defaultdict(dict)
    for r in stats:
        points[(r['subject'], r['threads'])][r['backend']] = r
    rows = []
    for (name, threads), arms in sorted(points.items()):
        require(set(arms) == ({'native', 'tclock', 'kd-spin', 'kd-blocking'} |
                             ({'stock'} if next(iter(arms.values()))['suite'] == 'api' else set())), 'missing backend')
        row = dict(subject=name, threads=threads, lock_kind=arms['kd-spin']['lock_kind'],
                   suite=arms['kd-spin']['suite'], spin_jit_rounds=arms['kd-spin']['jit_rounds'],
                   blocking_jit_rounds=arms['kd-blocking']['jit_rounds'],
                   complete=all(a['complete'] for a in arms.values()))
        for arm in ('kd-spin', 'kd-blocking'):
            for baseline in ('native', 'tclock', *(['kd-spin'] if arm == 'kd-blocking' else [])):
                for metric in ('whole_ops_s_median', 'peak_ops_s_max', 'cpu_ns_per_op_median'):
                    row[arm + '_over_' + baseline + '_' + metric] = (arms[arm][metric] / arms[baseline][metric]
                        if arms[arm]['complete'] and arms[baseline]['complete'] else None)
        rows.append(row)
    return rows


def tables(out, stats, ratios):
    by_point = {(r['subject'], r['threads']): r for r in ratios}
    text = ['# Every workload and worker count', '',
        'Rates are Mops/s. Whole-run tables use three-round medians; peak tables use the highest '
        'valid warmed window of at least 300 ms. B/S is KD blocking divided by KD spin. CPU cost is '
        'summed worker CPU nanoseconds per completed operation. It is not acquisition latency.', '',
        '[Statistics](statistics.csv) retain min/median/max/spread for every arm and metric; '
        '[samples](samples.csv) retain all individual rounds. Shaded plot ranges are the three '
        'observed rounds, not confidence intervals.', '',
        'JIT counts give the number of rounds with returned JIT bodies. A zero is a native-path '
        'control; a NORMAL publication alone is insufficient. Spin/rwlock policy pairs are regression '
        'controls: the mutex parameter does not change those algorithms.', '']
    for name in sorted({r['subject'] for r in stats}):
        text += ['## ' + name, '', 'Whole-run throughput:', '',
            '| Workers | Stock | Native | TCLock | KD spin | KD blocking | B/S whole | B/S CPU | Spin / blocking JIT rounds |',
            '| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
        for threads in THREADS:
            arms = {r['backend']: r for r in stats if r['subject'] == name and r['threads'] == threads}
            r = by_point[name, threads]
            rates = [f"{arms[a]['whole_ops_s_median']/1e6:.3f}" if a in arms and arms[a]['complete'] else '—' for a in ARMS]
            values = [r['kd-blocking_over_kd-spin_' + m] for m in
                      ('whole_ops_s_median', 'cpu_ns_per_op_median')]
            ratio = [f'{v:.3f}×' if v is not None else '—' for v in values]
            text.append('| ' + ' | '.join([str(threads), *rates, *ratio,
                        f"{r['spin_jit_rounds']}/3 · {r['blocking_jit_rounds']}/3"]) + ' |')
        text += ['', 'Best warmed peak throughput:', '',
            '| Workers | Stock | Native | TCLock | KD spin | KD blocking | B/S peak |',
            '| ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
        for threads in THREADS:
            arms = {r['backend']: r for r in stats if r['subject'] == name and r['threads'] == threads}
            r = by_point[name, threads]
            rates = [f"{arms[a]['peak_ops_s_max']/1e6:.3f}" if a in arms and arms[a]['complete'] else '—' for a in ARMS]
            value = r['kd-blocking_over_kd-spin_peak_ops_s_max']
            text.append('| ' + ' | '.join([str(threads), *rates,
                        f'{value:.3f}×' if value is not None else '—']) + ' |')
        text.append('')
    (out / 'TABLES.md').write_text('\n'.join(text))


def plots(out, stats):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9, 'svg.fonttype': 'none'})
    categories = {
        'mutex-micro': lambda r: r['suite'] == 'micro' and r['lock_kind'] == 'mutex',
        'mutex-api': lambda r: r['suite'] == 'api' and r['lock_kind'] == 'mutex',
        'spin-micro': lambda r: r['suite'] == 'micro' and r['lock_kind'] == 'spin',
        'rwlock-micro': lambda r: r['suite'] == 'micro' and r['lock_kind'] == 'rwlock',
        'spin-rwlock-api': lambda r: r['suite'] == 'api' and r['lock_kind'] != 'mutex'}
    for category, select in categories.items():
        subjects = sorted({r['subject'] for r in stats if select(r)})
        for metric, ylabel in (('whole_ops_s', 'Median whole-run Mops/s'), ('peak_ops_s', 'Best warmed peak Mops/s')):
            fig, axes = plt.subplots(math.ceil(len(subjects) / 2), 2, figsize=(14, 3.7 * math.ceil(len(subjects) / 2)), squeeze=False)
            for ax, name in zip(axes.flat, subjects):
                for arm in ARMS:
                    rows = sorted((r for r in stats if r['subject'] == name and r['backend'] == arm), key=lambda r: r['threads'])
                    if not rows:
                        continue
                    xs = [r['threads'] for r in rows]
                    score = '_median' if metric == 'whole_ops_s' else '_max'
                    def values(suffix):
                        return [r[metric + suffix] / 1e6 if r['complete'] else float('nan') for r in rows]
                    ax.plot(xs, values(score), 'o-', color=COLORS[arm], label=LABELS[arm], markersize=3)
                    ax.fill_between(xs, values('_min'), values('_max'), color=COLORS[arm], alpha=.08)
                ax.set(title=name, xlabel='Pinned workers', ylabel=ylabel, xticks=THREADS)
                ax.axvline(32, color='#bbbbbb', linestyle=':', linewidth=1)
                ax.grid(alpha=.2)
                ax.legend(fontsize=8)
            for ax in list(axes.flat)[len(subjects):]:
                ax.set_visible(False)
            fig.text(.5, .006, 'Three rounds; shading = observed range, not a confidence interval. '
                     'Workers >32 span both NUMA nodes.\n'
                     'NO_JIT controls are included (TABLES.md). Spin/rwlock policy pairs repeat unchanged algorithms.',
                     ha='center', va='bottom', fontsize=8)
            fig.tight_layout(rect=(0, .035, 1, 1))
            stem = out / (category + '-' + metric)
            fig.savefig(str(stem) + '.png', dpi=150)
            svg = Path(str(stem) + '.svg')
            fig.savefig(svg)
            svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
            plt.close(fig)


def pilots(root, out):
    """Audit tuning independently; never append it to the final matrix."""
    directories = sorted(root.glob('mutex-blocking-pilot-*'))
    directories += sorted(root.glob('mutex-blocking-acceptance-pipebytes*'))
    require(directories, 'no retained pilots found')
    samples, stats, receipts = [], [], {}
    for folder in directories:
        records = read(folder / 'records.json')
        kd = next(r for r in records if r['arm'] == 'kdlock')
        group = dict(suite='api' if 'kind' in kd else 'micro', family='mutex',
                     expected=len(records), mode=kd['mutex_wait_mode'])
        rows, counts, evidence = audit_group(folder, group, read(folder / 'source-sha256.json'), kd['mutex_spin_limit'])
        summaries = aggregate(rows)
        for r in [*rows, *summaries]:
            r.update(run=folder.name, included_in_final_matrix=False)
        samples += rows
        stats += summaries
        receipts[folder.name] = dict(counts=counts, **evidence)
    for name, data in (('pilot-samples', samples), ('pilot-statistics', stats)):
        write(out / (name + '.json'), data)
        csv_write(out / (name + '.csv'), data)
    write(out / 'pilot-verification.json', dict(passed=True, sessions=len(samples), runs=receipts))


def paired(directories, out, approved):
    samples, stats, receipts = [], [], {}
    for folder in directories:
        records = read(folder / 'records.json')
        require(records and all(r['arm'] == 'kdlock' for r in records), 'paired diagnostic requires KD-only records')
        manifest = read(folder / 'source-sha256.json')
        # Runner/docs can change for the interleaved follow-up; executed kernel
        # and translator sources must remain byte-identical to the main grid.
        for relative, expected in manifest.items():
            path = Path(relative)
            if path.parts[0] in ('include', 'kernel_module', 'disassem', 'workload_modules') and path.suffix != '.md':
                require(approved[relative] == expected, 'paired implementation changed: ' + relative)
        for i in range(0, len(records), 2):
            a, b = records[i:i + 2]
            order = ['blocking', 'spin'] if a['repeat'] % 2 else ['spin', 'blocking']
            require(subject(a) == subject(b) and a['threads'] == b['threads'] and a['repeat'] == b['repeat']
                    and [a['mutex_wait_mode'], b['mutex_wait_mode']] == order, 'policies not paired/alternating')
        group = dict(suite='micro', family=records[0]['lock_kind'], expected=len(records), mode='both')
        rows, counts, evidence = audit_group(folder, group, manifest, records[0]['mutex_spin_limit'])
        summaries = aggregate(rows)
        for r in [*rows, *summaries]:
            r.update(run=folder.name, included_in_final_matrix=False)
        samples += rows
        stats += summaries
        receipts[folder.name] = dict(counts=counts, **evidence)
    for name, data in (('paired-samples', samples), ('paired-statistics', stats)):
        write(out / (name + '.json'), data)
        csv_write(out / (name + '.csv'), data)
    write(out / 'paired-verification.json', dict(passed=True, sessions=len(samples), runs=receipts))


def superseded(directories, out):
    """Retain an intentionally stopped version without filling or pooling it."""
    samples, receipts = [], {}
    for root in directories:
        state = read(root / 'matrix-status.json')
        require(state['state'] in ('STOPPED', 'FAILED') and (root / 'STOP').is_file(),
                'explicitly stopped superseded matrix required')
        counts, evidence, executed = Counter(), {}, []
        approved = read(root / 'source-sha256-approved.json')
        for group in read(root / 'matrix-plan.json'):
            folder = root / group['name']
            if not (folder / 'records.json').exists():
                require(not folder.exists(), 'started group lacks records')
                counts['not_run'] += group['expected']
                continue
            rows, checked, saved = audit_group(folder, group, approved,
                state['mutex_spin_limit'], allow_not_run=True)
            executed += rows
            counts.update(checked)
            evidence[group['name']] = saved
        require(len(executed) + counts['not_run'] == state['expected_sessions'],
                'superseded coverage differs')
        for r in executed:
            r.update(run=root.name, included_in_final_matrix=False)
        samples += executed
        receipts[root.name] = dict(matrix_status=state, counts=dict(counts),
            executed_sessions=len(executed), stop_reason=(root / 'STOP').read_text(),
            groups=evidence)
    write(out / 'superseded-samples.json', samples)
    csv_write(out / 'superseded-samples.csv', samples)
    write(out / 'superseded-verification.json', dict(passed=True, sessions=len(samples), runs=receipts))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--plots', action='store_true')
    p.add_argument('--pilots', type=Path, help='optional parent directory of retained tuning/acceptance runs')
    p.add_argument('--paired', nargs='+', type=Path, help='optional separate interleaved KD-only diagnostics')
    p.add_argument('--superseded', nargs='+', type=Path, help='optional deliberately stopped earlier versions')
    args = p.parse_args()
    root, out = args.input.resolve(), args.output.resolve()
    require(not out.exists() and not out.is_relative_to(root), 'use a new report directory outside raw evidence')
    state, plan = read(root / 'matrix-status.json'), read(root / 'matrix-plan.json')
    require(state['state'] == 'COMPLETE' and state['expected_sessions'] == 2430
            and state['threads'] == THREADS and state['collector_cpu'] == 63 and len(plan) == 24,
            'complete default matrix required')
    approved = read(root / 'source-sha256-approved.json')
    samples, counts, evidence = [], Counter(), {}
    for group in plan:
        rows, checked, saved = audit_group(root / group['name'], group, approved, state['mutex_spin_limit'])
        samples += rows
        counts.update(checked)
        evidence[group['name']] = saved
        print(group['name'], len(rows), 'verified', flush=True)
    require(len(samples) == 2430 and {r['subject'] for r in samples} == SUBJECTS, 'incomplete workload coverage')
    stats = aggregate(samples)
    ratios = comparisons(stats)
    require(len(stats) == 810 and len(ratios) == 186, 'incomplete comparison grid')
    out.mkdir(parents=True)
    (out / 'export.py').write_bytes(Path(__file__).read_bytes())
    for name, data in (('samples', samples), ('statistics', stats), ('comparison', ratios),
                       ('statistics-by-execution', aggregate(samples, split_execution=True))):
        write(out / (name + '.json'), data)
        csv_write(out / (name + '.csv'), data)
    receipt = dict(passed=True, sessions=len(samples), statistics=len(stats), comparisons=len(ratios),
        subjects=31, counts=dict(counts), statuses=dict(Counter(r['execution_status'] for r in samples)),
        execution_types=dict(Counter(r['execution_type'] for r in samples)), matrix_status=state,
        timed_operations=sum(r['completed'] for r in samples), jit_bodies=sum(r['jit_bodies'] for r in samples),
        exporter_sha256=sha(Path(__file__)))
    write(out / 'verification.json', receipt)
    write(out / 'evidence.json', evidence)
    tables(out, stats, ratios)
    if args.plots:
        plots(out, stats)
    if args.pilots:
        pilots(args.pilots.resolve(), out)
    if args.paired:
        paired([p.resolve() for p in args.paired], out, approved)
    if args.superseded:
        superseded([p.resolve() for p in args.superseded], out)
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
