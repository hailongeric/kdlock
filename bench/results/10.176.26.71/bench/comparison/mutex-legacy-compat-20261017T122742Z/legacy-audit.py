#!/usr/bin/env python3
"""Replay frozen legacy mutex evidence. No benchmark execution or module access."""
import argparse
import ast
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import runpy
import statistics
import sys

THREADS = [*range(1, 9), *range(12, 61, 4)]
ARMS = ('native', 'tclock', 'kdlock')
GROUPS = ('c01-post64', 'api-pipebytes-query-n16')
LABELS = dict(native='Linux Native', tclock='TCLock', kdlock='KD mutex legacy')
COLORS = dict(native='#626973', tclock='#0072B2', kdlock='#D55E00')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


def table(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v
                             for k, v in row.items()})


def manifest(folder, name, prefix, binary=False):
    items = read(folder / name)
    for rel, value in items.items():
        expected = value['sha256'] if binary else value
        check(sha(folder / prefix / rel) == expected, f'{name}: {rel}')
    return len(items)


def independent_peak(row):
    """Replay the first qualifying endpoint per sampled start, using integer ratios."""
    m = row['measurement']
    start = max(w['active_started_ns'] for w in m['workers']) + m['peak_settle_ns']
    end = min(m['deadline_ns'], *(w['kernel_finished_ns'] for w in m['workers']))
    eligible = [s for s in m['samples'] if s['started_ns'] >= start and s['finished_ns'] <= end]
    best = None
    for i, first in enumerate(eligible):
        for last in eligible[i + 1:]:
            elapsed = last['finished_ns'] - first['started_ns']
            if elapsed < m['peak_window_ns']:
                continue
            delta = [b - a for a, b in zip(first['completed'], last['completed'])]
            if min(delta) > 0:
                total = sum(delta)
                if best is None or total * best[1] > best[0] * elapsed:
                    best = (total, elapsed)
            break
    check(best and math.isclose(best[0] * 1e9 / best[1], m['peak']['throughput_ops_s'],
                               rel_tol=1e-12), 'independent peak: ' + row['name'])


def post_work(folder):
    audit = read(folder / 'post-work-audit.json')
    check(set(audit) == set(ARMS), 'post-work arms')
    for arm in ARMS:
        check(audit[arm]['sha256'] == sha(folder / 'variants' / arm / 'mutex_cacheline.ko'),
              'post-work module identity')
        instructions = []
        for line in (folder / f'{arm}-post-work-assembly.txt').read_text().splitlines():
            match = re.match(r'^\s*[0-9a-f]+:\s+([a-z][a-z0-9]*)\s*(.*)$', line)
            if match:
                instructions.append((match[1], re.sub(r'\s+', '', match[2].split('#')[0])))
        groups, i = [], 0
        while i + 1 < len(instructions):
            count = 0
            while i + 1 < len(instructions):
                op, operand = instructions[i]
                match = re.fullmatch(r'\$0x19660d,(%[a-z0-9]+),\1', operand)
                if not (op == 'imul' and match and
                        instructions[i + 1] == ('add', '$0x3c6ef35f,' + match[1])):
                    break
                count += 1
                i += 2
            if count:
                groups.append(count)
            else:
                i += 1
        check(groups == audit[arm]['dependent_multiply_add_groups'] == [64, 64],
              'post-work assembly groups')
    return audit


def prepared_provider(prepared, source):
    record = read(prepared / 'manifest.json')
    check(record['complete'] is True, 'incomplete prepared provider')
    for name, expected in record['production'].items():
        check(sha(source / name) == expected, 'provider production identity: ' + name)
    for name, expected in record['prepared'].items():
        check(sha(prepared / name) == expected, 'prepared provider identity: ' + name)
    for name, expected in record['observation'].items():
        check(sha(source / 'bench/spin_cacheline/provider' / name) == expected, 'provider observation identity')
    return dict(production=len(record['production']), prepared=len(record['prepared']),
                observation=len(record['observation']))


def audit_c01(folder):
    counts = dict(source=manifest(folder, 'source-sha256.json', 'source'))
    counts['prepared_provider'] = prepared_provider(folder / 'source/bench/spin_cacheline/.build/provider',
                                                     folder / 'source')
    if (folder / 'kernel-inputs-sha256.json').exists():
        counts['kernel'] = manifest(folder, 'kernel-inputs-sha256.json', 'kernel-inputs')
    context = runpy.run_path(str(folder / 'source/bench/tclock_compare/context_audit.py'))['audit']
    check(read(folder / 'tclock-context-audit.json') ==
          context((folder / 'tclock-backend.txt').read_text(), 'mutex'),
          'c01 TCLock emitted context')
    for path in folder.glob('imports-*.txt'):
        check('__ubsan_' not in path.read_text(), 'c01 timed UBSAN imports')
    binaries = read(folder / 'binary-sha256.json')
    for original, expected in binaries.items():
        _, mark, rel = original.partition('/' + folder.name + '/')
        path = folder / rel if mark else folder / 'binaries' / Path(original).name
        check(sha(path) == expected, 'binary hash: ' + original)
    counts['binary'] = len(binaries)
    counts['post_work'] = post_work(folder)
    source = folder / 'source/bench/spin_cacheline'
    # Extract only the pure validators; importing the full runtime would pull in device helpers.
    tree = ast.parse((source / 'bench_runtime.py').read_text())
    names = {'Failure', 'require', 'validate_measurement', 'validate_payload', 'validate_timed_measurement'}
    functions = ast.Module(body=[n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))
                                and n.name in names], type_ignores=[])
    scope = {}
    exec(compile(functions, str(source / 'bench_runtime.py'), 'exec'), scope)
    sys.path.insert(0, str(source))
    fault = next(n for n in tree.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'FAULT' for t in n.targets))
    faults = re.compile(ast.literal_eval(fault.value.args[0]), re.I)
    plan, records = read(folder / 'plan.json'), read(folder / 'records.json')
    check([r['name'] for r in records] == [r['name'] for r in plan], 'c01 plan/records')
    images = 0
    for row in records:
        path = folder / row['name']
        session = read(path / 'session.json')
        derived = {'whole_throughput_ops_s', 'whole_amortized_ns_op', 'throughput_ops_s', 'amortized_ns_op'}
        check({k: v for k, v in row.items() if k not in derived} == session, 'c01 session differs')
        check(row['execution_status'] in ('OK', 'NO_JIT') and row['drained'], 'c01 failed/undrained')
        check(not faults.search((path / 'kernel.log').read_text()), 'c01 kernel fault')
        warm = read(path / 'warmup.json')
        scope['validate_measurement'](warm, dict(row, duration_ms=0), 48000)
        raw = read(path / 'measure.json')
        check({k: v for k, v in row['measurement'].items() if k != 'peak'} == raw, 'c01 raw changed')
        peak = scope['validate_measurement'](raw, row, 0)
        check(peak == row['measurement']['peak'], 'c01 peak changed')
        check(read(path / 'drain.counts.json')['active'] == 0, 'c01 caller drain')
        check(row['warmup_iterations_per_worker'] == 48000 and row['warmup_pause_seconds'] == 0,
              'c01 warmup setting')
        jit = row['jit_bodies']
        check(0 <= jit <= raw['completed'] and row['jit_share'] == jit / raw['completed'],
              'c01 JIT accounting')
        if row['arm'] == 'kdlock':
            check(row['jit_after'] - row['jit_before'] == jit, 'c01 JIT counters')
            check(row['published_before'] == row['published_after'], 'c01 publication changed')
            check(row['retired'] == dict(state=2, modules=0, frames=0, writers=0), 'c01 exact retirement')
            pub = row['published_before']
            entry = pub['entry']
            check(entry['entry_abi'] == 2 and entry['lock_kind'] == 2 and entry['status'] == 0
                  and entry['code'] != 0 and entry['pid'] == 0, 'c01 publication identity')
            check(row['entry_range'][0] <= entry['entry'] < row['entry_range'][1], 'c01 entry range')
            asm = path / 'workspace/daemon' / hex(entry['entry']) / str(entry['tgid']) / 'asm'
            for filename, expected in pub['images'].items():
                check(sha(asm / filename) == expected, 'c01 JIT image hash')
                images += 1
            if row['execution_status'] == 'NO_JIT':
                check(jit == 0 and row['threads'] >= 4, 'unexpected c01 NO_JIT failure')
            elif row['threads'] >= 4:
                check(jit > 0 and row['jit_acceptance'] == 'PASS', 'missing contended JIT')
        elif row['arm'] == 'tclock':
            check(row['tclock_drained']['quiescent'] == 1, 'c01 TCLock drain')
            check(row['delegated_bodies'] == row['tclock_after']['delegated'] -
                  row['tclock_before']['delegated'], 'c01 TCLock accounting')
        if row['execution_status'] == 'OK':
            check(row['whole_throughput_ops_s'] == raw['completed'] * 1e9 / raw['wall_ns'] and
                  row['throughput_ops_s'] == peak['throughput_ops_s'], 'c01 derived rates')
        else:
            check(all(row[k] is None for k in derived), 'failed c01 acquired a score')
    counts['jit_images'] = images
    return counts, records


def sample(group, row):
    m = row['measurement']
    counts = [w['completed'] for w in m['workers']]
    check([w['cpu'] for w in m['workers']] == row['cpus'] == list(range(row['threads'])), 'worker CPUs')
    check(row['collector_cpu'] == m['collector_cpu'] == m['collector_observed_cpu'] == 63,
          'collector CPU')
    check(m['collector_error'] == 0 and all(w['error'] == 0 and w['observed_cpu'] == w['cpu']
          for w in m['workers']), 'worker errors/affinity')
    independent_peak(row)
    ok = row['execution_status'] == 'OK' and row['drained']
    jit = row['jit_bodies']
    whole_nodes, peak_nodes = Counter(), Counter()
    for worker, delta in zip(m['workers'], m['peak']['worker_completed']):
        node = str(worker['cpu'] // 32)
        whole_nodes[node] += worker['completed']
        peak_nodes[node] += delta
    return dict(workload=group, threads=row['threads'], arm=row['arm'], repeat=row['repeat'],
                name=row['name'], accepted=ok, status=row['execution_status'], drained=row['drained'],
                execution_type=('ACTUAL_JIT' if jit else 'NO_JIT') if row['arm'] == 'kdlock'
                               else 'NATIVE_IMPLEMENTATION',
                jit_bodies=jit, jit_share=row['jit_share'], jit_status=row['jit_status'],
                jit_acceptance=row.get('jit_acceptance'),
                delegated_bodies=row.get('tclock_delegation') if group.startswith('api-')
                                 else row.get('delegated_bodies'),
                completed=m['completed'], wall_ns=m['wall_ns'],
                whole_ops_s=m['completed'] * 1e9 / m['wall_ns'], peak_ops_s=m['peak']['throughput_ops_s'],
                min_worker_ops=min(counts), max_worker_ops=max(counts),
                worker_jain_index=sum(counts)**2 / (len(counts) * sum(v*v for v in counts)),
                min_worker_peak_ops=min(m['peak']['worker_completed']),
                worker_cpu_ns=sum(w.get('cpu_ns', 0) for w in m['workers']),
                worker_cpu_ns_per_op=sum(w.get('cpu_ns', 0) for w in m['workers']) / m['completed'],
                worker_cpu_cores=sum(w.get('cpu_ns', 0) for w in m['workers']) / m['wall_ns'],
                whole_node_completed=dict(whole_nodes), peak_node_completed=dict(peak_nodes))


def aggregate(key, rows):
    valid = [r for r in rows if r['accepted']]
    types = {r['execution_type'] for r in valid}
    result = dict(workload=key[0], threads=key[1], arm=key[2], sessions=len(rows),
                  valid_rounds=len(valid), complete=len(valid) == 3,
                  execution_type=next(iter(types)) if len(types) == 1 else 'MIXED' if types else 'NONE',
                  jit_rounds=sum(r['jit_bodies'] > 0 for r in valid),
                  no_jit_rounds=sum(r['jit_bodies'] == 0 for r in valid) if key[2] == 'kdlock' else None,
                  aggregate_jit_share=sum(r['jit_bodies'] for r in valid) / sum(r['completed'] for r in valid)
                                      if valid else None,
                  min_worker_ops=min((r['min_worker_ops'] for r in valid), default=None),
                  min_worker_jain_index=min((r['worker_jain_index'] for r in valid), default=None),
                  median_worker_cpu_ns_per_op=statistics.median(r['worker_cpu_ns_per_op'] for r in valid)
                                             if valid else None,
                  median_worker_cpu_cores=statistics.median(r['worker_cpu_cores'] for r in valid)
                                          if valid else None)
    for metric in ('whole', 'peak'):
        values = [r[metric + '_ops_s'] for r in valid]
        for name, fn in (('min', min), ('median', statistics.median), ('max', max)):
            result[f'{metric}_{name}_ops_s'] = fn(values) if values else None
        result[metric + '_spread_pct'] = 100 * (max(values) - min(values)) / statistics.median(values) if values else None
    result['best_peak_ops_s'] = result['peak_max_ops_s']
    return result


def plots(stats, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'svg.fonttype': 'none'})
    for metric in ('whole', 'peak'):
        fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=False)
        for ax, group in zip(axes, GROUPS):
            ax.axvspan(32.5, 60.5, color='#F2F4F7', zorder=0)
            ax.axvline(32.5, color='#88919D', linestyle=':', linewidth=1)
            for arm in ARMS:
                rows = [r for r in stats if r['workload'] == group and r['arm'] == arm]
                field = 'whole_median_ops_s' if metric == 'whole' else 'best_peak_ops_s'
                x = [r['threads'] for r in rows]
                y = [r[field] / 1e6 if r['complete'] else math.nan for r in rows]
                low = [r[metric + '_min_ops_s'] / 1e6 if r['complete'] else math.nan for r in rows]
                high = [r[metric + '_max_ops_s'] / 1e6 if r['complete'] else math.nan for r in rows]
                ax.plot(x, y, color=COLORS[arm], marker='o', markersize=3.5, linewidth=1.7)
                ax.fill_between(x, low, high, color=COLORS[arm], alpha=.12)
                if arm == 'kdlock':
                    for r, xx, yy in zip(rows, x, y):
                        if r['complete'] and r['execution_type'] in ('NO_JIT', 'MIXED'):
                            ax.plot(xx, yy, marker='o' if r['execution_type'] == 'NO_JIT' else 'D',
                                    markerfacecolor='white', markeredgecolor=COLORS[arm], markersize=5)
            ax.set(title='One cacheline · 64 post-unlock rounds' if group == GROUPS[0] else 'pipebytes query · 16 occupied buffers',
                   xlim=(0, 60.5), ylim=(0, None), xlabel='Workers', ylabel='Throughput (Mops/s)')
            ax.set_xticks([1, 4, 8, 12, 16, 24, 32, 40, 48, 56, 60])
            ax.grid(axis='y', alpha=.25)
        handles = [Line2D([0], [0], color=COLORS[a], marker='o', label=LABELS[a]) for a in ARMS]
        handles.append(Line2D([0], [0], color=COLORS['kdlock'], marker='o', markerfacecolor='white',
                              linestyle='none', label='KD: no returned JIT body'))
        title = 'Median whole-run throughput' if metric == 'whole' else 'Best warmed peak across three repetitions'
        fig.suptitle('Recovered legacy KD mutex: ' + title, fontsize=15, x=.06, ha='left')
        fig.legend(handles=handles, loc='lower center', ncol=4, frameon=False, bbox_to_anchor=(.5, .045))
        fig.text(.06, .015, 'Three repetitions; bands show min–max. Gray region uses both NUMA nodes. Host governor: ondemand.', fontsize=9)
        fig.tight_layout(rect=(0, .14, 1, .92))
        for extension in ('png', 'svg'):
            fig.savefig(out / f'{metric}-throughput.{extension}', dpi=170)
        plt.close(fig)


def markdown(stats, comparison, out):
    lines = ['# Full scaling tables', '',
             'All rates are Mops/s. Whole is the three-repetition median; peak is the highest valid '
             'warmed 300 ms window across three repetitions. Ratios use whole-run medians. '
             'Min/median/max/spread and execution-separated aggregates are in the CSV files.', '']
    indexed = {(r['workload'], r['threads'], r['arm']): r for r in stats}
    for group in GROUPS:
        lines += ['## ' + group, '',
                  '| Workers | Native whole | TCLock whole | KD whole | KD / Native | KD / TCLock | Native peak | TCLock peak | KD peak | KD JIT rounds |',
                  '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
        for count in THREADS:
            rows = [indexed[(group, count, arm)] for arm in ARMS]
            values = [r['whole_median_ops_s'] / 1e6 for r in rows]
            peaks = [r['best_peak_ops_s'] / 1e6 for r in rows]
            lines.append(f'| {count} | ' + ' | '.join(f'{x:.3f}' for x in values) +
                         f' | {values[2]/values[0]:.2f}× | {values[2]/values[1]:.2f}× | ' +
                         ' | '.join(f'{x:.3f}' for x in peaks) + f" | {rows[2]['jit_rounds']}/3 |")
        lines.append('')
    (out / 'SCALING.md').write_text('\n'.join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--plots', action='store_true')
    args = parser.parse_args()
    root, out = args.root.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    check(read(root / 'status.json')['state'] == 'COMPLETE', 'unfinished matrix')
    source = read(root / 'control/source-sha256.json')
    historical = read(root / 'control/historical-source-sha256.json')
    for rel, expected in source.items():
        check(sha(root / 'frozen-source' / rel) == expected, 'frozen source: ' + rel)
    for rel, expected in historical.items():
        check(source[rel] == expected, 'historical source: ' + rel)
    checks = dict(frozen_source_files=len(source), historical_source_files=len(historical))
    c01_checks, c01_records = audit_c01(root / GROUPS[0])
    checks[GROUPS[0]] = c01_checks
    api_spec = importlib.util.spec_from_file_location('api_audit', Path(__file__).with_name('api-audit.py'))
    api_audit = importlib.util.module_from_spec(api_spec)
    api_spec.loader.exec_module(api_audit)
    checks[GROUPS[1]] = api_audit.audit(root / GROUPS[1])
    checks[GROUPS[1]]['prepared_provider'] = prepared_provider(root / 'control/api-prepared-provider',
                                                               root / GROUPS[1] / 'source')
    api_records = read(root / GROUPS[1] / 'records.json')
    samples, workers = [], []
    for group, records in zip(GROUPS, (c01_records, api_records)):
        # The synthetic runner captures the common bundle; the API runner stores
        # its own identity receipt plus the syscall source files, not a second bundle.
        identity = root / group / ('baseline.json' if group == GROUPS[0] else 'kernel-identity.json')
        check(read(identity) == read(root / 'control/kernel-identity.json'), 'phase kernel identity')
        baseline = root / GROUPS[0] / 'kernel-baseline'
        bundle = read(baseline / 'manifest.json')['bundle_files']
        for name, expected_hash in bundle.items():
            check(sha(baseline / name) == expected_hash, 'captured kernel bundle: ' + name)
        checks[group]['kernel_bundle_files'] = len(bundle)
        expected = {(t, a, r) for t in THREADS for a in ARMS for r in range(3)}
        check(len(records) == 189 and {(r['threads'], r['arm'], r['repeat']) for r in records} == expected,
              'incomplete configuration matrix: ' + group)
        captured = read(root / group / 'source-sha256.json')
        overlap = set(captured) & set(source)
        check(all(captured[p] == source[p] for p in overlap),
              'frozen source sets differ: ' + group)
        checks[group]['shared_source_files'] = len(overlap)
        for row in records:
            check(row['lock_kind'] == 'mutex' and row['duration_ms'] == 2000 and row['drained'],
                  'timing/lock/drain')
            check(row['peak_window_ms'] == row['peak_settle_ms'] == 300 and row['sample_ms'] == 10,
                  'peak sampling settings')
            if group == GROUPS[1]:
                check(row['kind'] == 'pipebytes' and row['query'] == 'query' and row['entries'] == 16
                      and row['warmup'] == 48000 and row['warmup_ms'] == 1000, 'API workload settings')
            samples.append(sample(group, row))
            for w in row['measurement']['workers']:
                workers.append(dict(workload=group, name=row['name'], threads=row['threads'],
                                    arm=row['arm'], repeat=row['repeat'], **w))
    buckets, separated = defaultdict(list), defaultdict(list)
    for row in samples:
        key = (row['workload'], row['threads'], row['arm'])
        buckets[key].append(row)
        separated[key + (row['execution_type'],)].append(row)
    stats = [aggregate(k, rows) for k, rows in sorted(buckets.items())]
    by_execution = [aggregate(k[:3], rows) for k, rows in sorted(separated.items())]
    comparisons = []
    for group in GROUPS:
        for count in THREADS:
            arms = {r['arm']: r for r in stats if r['workload'] == group and r['threads'] == count}
            complete = all(r['complete'] for r in arms.values())
            row = dict(workload=group, threads=count, complete=complete,
                       kd_execution_type=arms['kdlock']['execution_type'])
            for metric in ('whole_median_ops_s', 'best_peak_ops_s'):
                for arm in ('native', 'tclock'):
                    row[f'kd_over_{arm}_{metric}'] = arms['kdlock'][metric] / arms[arm][metric] if complete else None
            comparisons.append(row)
    for name, rows in [('samples', samples), ('workers', workers), ('statistics', stats),
                       ('statistics-by-execution', by_execution), ('comparison', comparisons)]:
        save(out / f'{name}.json', rows)
        table(out / f'{name}.csv', rows)
    verification = dict(status='PASS', sessions=len(samples), accepted=sum(r['accepted'] for r in samples),
                        drained=sum(r['drained'] for r in samples),
                        excluded=[r['name'] for r in samples if not r['accepted']],
                        statuses=dict(Counter(r['status'] for r in samples)),
                        kd_jit_sessions=sum(r['arm'] == 'kdlock' and r['jit_bodies'] > 0 for r in samples),
                        kd_no_jit_sessions=sum(r['arm'] == 'kdlock' and r['jit_bodies'] == 0 for r in samples),
                        independent_peaks=len(samples), timed_operations=sum(r['completed'] for r in samples),
                        checks=checks)
    save(out / 'verification.json', verification)
    markdown(stats, comparisons, out)
    if args.plots:
        plots(stats, out)
    print(json.dumps({k: v for k, v in verification.items() if k != 'checks'}, indent=2), flush=True)


if __name__ == '__main__':
    main()
