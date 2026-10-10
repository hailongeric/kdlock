#!/usr/bin/env python3
"""Audit and report the saved complete matrix; never execute benchmark code."""
import argparse
import collections
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import statistics

THREADS = [*range(1, 9), *range(12, 65, 4)]
ARMS = ('native', 'tclock', 'kdlock')
LABELS = dict(native='Linux Native', tclock='TCLock', kdlock='KDLock')
COLORS = dict(native='#626973', tclock='#0072B2', kdlock='#D55E00')


def json_write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


def csv_write(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows({k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v
                         for k, v in row.items()} for row in rows)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted(row):
    m = row.get('measurement', {})
    return (row.get('execution_status') == 'OK' and row.get('drained') is True and
            m.get('data_ok') is True and m.get('complete') is True and
            m.get('peak', {}).get('throughput_ops_s', 0) > 0 and
            m.get('completed', 0) > 0 and m.get('wall_ns', 0) > 0)


def independently_check_peak(row):
    """Recompute observed windows from raw progress, without runner imports."""
    m = row['measurement']
    start = max(w['active_started_ns'] for w in m['workers']) + m['peak_settle_ns']
    end = min(m['deadline_ns'], *(w['kernel_finished_ns'] for w in m['workers']))
    samples = m['samples']
    eligible = [s for s in samples if s['started_ns'] >= start and s['finished_ns'] <= end]
    best = None
    for i, first in enumerate(eligible):
        for last in eligible[i + 1:]:
            elapsed = last['finished_ns'] - first['started_ns']
            if elapsed < m['peak_window_ns']:
                continue
            deltas = [b - a for a, b in zip(first['completed'], last['completed'])]
            if min(deltas) > 0:
                total = sum(deltas)
                if best is None or total * best[1] > best[0] * elapsed:
                    best = (total, elapsed)
            break
    if best is None or not math.isclose(best[0] * 1e9 / best[1],
                                        m['peak']['throughput_ops_s'], rel_tol=1e-12):
        raise ValueError('raw peak differs: ' + row['name'])
    if m['completed'] != sum(w['completed'] for w in m['workers']):
        raise ValueError('worker operation totals differ: ' + row['name'])
    if [w['cpu'] for w in m['workers']] != row['cpus'] or any(
            w['observed_cpu'] != w['cpu'] or w['completed'] <= 0 for w in m['workers']):
        raise ValueError('worker placement/progress differs: ' + row['name'])
    if (m['collector_observed_cpu'] != row['collector_cpu'] or
            row['collector_cpu'] in row['cpus'] or m['collector_error'] != 0):
        raise ValueError('collector differs: ' + row['name'])


def sample(group, row):
    m = row.get('measurement', {})
    ok = accepted(row)
    jit = row.get('jit_bodies', 0)
    whole_nodes, peak_nodes = collections.Counter(), collections.Counter()
    for node, worker, delta in zip(row.get('cpu_nodes', []), m.get('workers', []),
                                   m.get('peak', {}).get('worker_completed', [])):
        whole_nodes[str(node)] += worker['completed']
        peak_nodes[str(node)] += delta
    return dict(group=group, lock_kind=row['lock_kind'], workload=row['workload'],
                cachelines=row['cachelines'], write_percent=row.get('write_percent'),
                threads=row['threads'], arm=row['arm'], repeat=row['repeat'], name=row['name'],
                accepted=ok, execution_status=row.get('execution_status'), drained=row.get('drained'),
                data_ok=m.get('data_ok'), complete=m.get('complete'),
                execution_type=('ACTUAL_JIT' if jit else 'NO_JIT') if row['arm'] == 'kdlock' else 'NATIVE_IMPLEMENTATION',
                jit_bodies=jit, jit_status=row.get('jit_status'), jit_acceptance=row.get('jit_acceptance'),
                jit_share=row.get('jit_share'), jit_writer_share=row.get('jit_writer_share'),
                delegated_bodies=row.get('delegated_bodies'), delegation_status=row.get('delegation_status'),
                delegation_share=row.get('delegation_share'),
                cpus=row['cpus'], cpu_nodes=row.get('cpu_nodes'), collector_cpu=row['collector_cpu'],
                post_work_rounds=row.get('post_work_rounds', 64),
                peak_ops_s=m.get('peak', {}).get('throughput_ops_s'),
                whole_ops_s=m['completed'] * 1e9 / m['wall_ns'] if m.get('wall_ns', 0) else None,
                completed=m.get('completed'), reads=m.get('reads'), writes=m.get('writes'), wall_ns=m.get('wall_ns'),
                whole_node_completed=dict(whole_nodes), peak_node_completed=dict(peak_nodes))


def aggregate(key, rows, execution_type=None):
    group, percent, threads, arm = key
    valid = [r for r in rows if r['accepted']]
    types = {r['execution_type'] for r in valid}
    result = dict(group=group, write_percent=percent, threads=threads, arm=arm,
                  sessions=len(rows), valid_rounds=len(valid), complete=len(valid) == 3,
                  actual_jit_rounds=sum(r['jit_bodies'] > 0 for r in valid),
                  no_jit_rounds=sum(r['jit_bodies'] == 0 for r in valid) if arm == 'kdlock' else None,
                  execution_type=execution_type or (next(iter(types)) if len(types) == 1 else
                                                    'MIXED' if types else 'NO_VALID_SAMPLE'))
    for metric in ('peak', 'whole'):
        rates = [r[metric + '_ops_s'] for r in valid]
        for label, fn in (('min', min), ('median', statistics.median), ('max', max)):
            result[f'{metric}_{label}_ops_s'] = fn(rates) if rates else None
        result[metric + '_spread_pct'] = (100 * (max(rates) - min(rates)) / statistics.median(rates)
                                          if rates else None)
    result['best_peak_ops_s'] = result['peak_max_ops_s']
    return result


def markdown(stats, comparisons, verification, run_name):
    rate = lambda v: f'{v / 1e6:.3f}' if v is not None else '—'
    count = verification['sessions']
    lines = [f'# Complete benchmark on 10.176.26.71: {run_name}', '',
             f"All **{count:,} planned timed sessions** were executed and drained; "
             f"**{verification['accepted_sessions']:,}** passed performance-data acceptance. "
             f"The remaining **{verification['excluded_sessions']}** sessions remain in the raw evidence and are excluded from scores.", '',
             'Thread counts: **1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60, 64**. '
             'Every configuration uses Linux Native, TCLock and KDLock, with three rounds per backend.', '',
             'Spin and mutex cover cacheline sizes 1/8/16 plus RCUHT. Rwlocks cover cacheline sizes '
             '1/2/4/8/16 plus RCUHT, each at 1% and 20% writes. Warmup is 48,000 operations per worker; '
             'measurement is 2,000 ms; peak selection uses an observed 300 ms window after 300 ms of settling. '
             'Spin/mutex use their frozen 64 post-work arithmetic rounds; rwlocks use four. Compare backends within each workload.', '',
             'The temporary VM exposes 66 vCPUs with 24 GiB RAM and two NUMA nodes. Workers use guest '
             'CPUs 0–31,33–64, pinned to host physical cores 0–63: 32 worker cores per NUMA node. '
             'Collector vCPU 65 is outside every guest worker cohort. **At 64 workers, collector 65 '
             'and QEMU service threads share host core 63 with worker vCPU 64.** CPU 32 is unused by the benchmark. '
             'The host has only 64 physical cores; the 64-worker point includes physical collection contention. '
             'Host frequency governor remains `ondemand`. These samples are separate from previous VM topologies.', '',
             f"Accepted KD sessions: **{verification['kd_jit_sessions']} ACTUAL_JIT**, "
             f"**{verification['kd_no_jit_sessions']} NO_JIT**. NO_JIT throughput is a native-path control, "
             'and does not prove JIT gain. Status-separated aggregates are retained. Three-round descriptive '
             'totals do not merge execution statuses to satisfy the rwlock runner’s strict parity criterion.', '',
             'Rates are **Mops/s**. Best peak is the highest valid warmed window across the three rounds. '
             'Whole-run is the median of completed operations divided by actual wall time. Ranges and spread '
             'are retained in CSV; spread is `(max-min)/median × 100%`, not a confidence interval.', '',
             '- [Every session](samples.csv)', '- [Three-round statistics](statistics.csv)',
             '- [Statistics by execution status](statistics-by-execution.csv)',
             '- [KD comparison ratios](comparison.csv)', '- [Independent verification](verification.json)',
             '- [Captured environment and commands](evidence.json)', '']
    if verification.get('interrupted_executed_sessions'):
        lines += [f"An earlier interrupted group contains **{verification['interrupted_executed_sessions']}** "
                  'additional completed, drained sessions. A disappearing `/proc/<pid>/task` entry stopped '
                  'the original idle scan. That attempt and failure remain archived; the whole group was '
                  'rerun using unchanged benchmark source and timing. A bounded retry requires an entire '
                  'original idle check to succeed. The interrupted samples are independently audited and '
                  'excluded from the final three-round statistics, without selecting among repeated scores.', '',
                  '- [Interrupted attempt samples](interrupted-attempts.csv)', '']
    for kind in ('spin', 'mutex', 'rwlock'):
        lines += [f'## {kind.capitalize()} scaling', '',
                  f'![{kind} whole-run throughput]({kind}-whole-throughput.png)', '',
                  f'![{kind} warmed peak throughput]({kind}-peak-throughput.png)', '']
    for group in dict.fromkeys(r['group'] for r in stats):
        percentages = sorted({r['write_percent'] for r in stats if r['group'] == group}, key=lambda p: p or -1)
        for percent in percentages:
            title = group + (f' · {percent}% writes' if percent is not None else '')
            lines += ['## ' + title, '',
                      '| Workers | Backend | Valid | Best peak | Median whole | Whole min / max | KD execution |',
                      '| --- | --- | --- | --- | --- | --- | --- |']
            for r in stats:
                if r['group'] != group or r['write_percent'] != percent:
                    continue
                evidence = (f"{r['actual_jit_rounds']} JIT / {r['no_jit_rounds']} NO_JIT" if r['arm'] == 'kdlock' else '—')
                lines.append(f"| {r['threads']} | {LABELS[r['arm']]} | {r['valid_rounds']}/3 | "
                             f"{rate(r['best_peak_ops_s'])} | {rate(r['whole_median_ops_s'])} | "
                             f"{rate(r['whole_min_ops_s'])} / {rate(r['whole_max_ops_s'])} | {evidence} |")
            lines.append('')
    return '\n'.join(lines)


def plots(stats, plan, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.lines import Line2D
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'svg.fonttype': 'none'})
    for kind in ('spin', 'mutex', 'rwlock'):
        panels = [(p['name'], percent) for p in plan if p['lock_kind'] == kind
                  for percent in ([1, 20] if kind == 'rwlock' else [None])]
        if not panels:
            continue
        height = 4 * math.ceil(len(panels) / 2)
        for metric in ('peak', 'whole'):
            fig, axes = plt.subplots(math.ceil(len(panels) / 2), 2,
                                     figsize=(15, height), squeeze=False)
            for ax, (group, percent) in zip(axes.flat, panels):
                subset = [r for r in stats if r['group'] == group and r['write_percent'] == percent]
                ax.set_title(group + (f' · {percent}% writes' if percent is not None else ''), loc='left')
                ax.axvspan(32.5, 66, color='#F2F4F7', zorder=0)
                ax.axvline(32.5, color='#88919D', linestyle=':', linewidth=1)
                ax.axvline(64, color='#B85B5B', linestyle=':', linewidth=1)
                for arm in ARMS:
                    rows = sorted((r for r in subset if r['arm'] == arm), key=lambda r: r['threads'])
                    field = 'best_peak_ops_s' if metric == 'peak' else 'whole_median_ops_s'
                    x = [r['threads'] for r in rows]
                    y = np.array([r[field] / 1e6 if r['complete'] else np.nan for r in rows])
                    low = np.array([r[metric + '_min_ops_s'] / 1e6 if r['complete'] else np.nan for r in rows])
                    high = np.array([r[metric + '_max_ops_s'] / 1e6 if r['complete'] else np.nan for r in rows])
                    ax.plot(x, y, color=COLORS[arm], marker='o', markersize=3.5, linewidth=1.7)
                    ax.errorbar(x, y, yerr=[np.maximum(0, y-low), np.maximum(0, high-y)], fmt='none',
                                ecolor=COLORS[arm], elinewidth=.8, alpha=.55, capsize=2)
                    if arm == 'kdlock':
                        for r, xx, yy in zip(rows, x, y):
                            if r['complete'] and r['execution_type'] in ('NO_JIT', 'MIXED'):
                                ax.plot(xx, yy, marker='o' if r['execution_type'] == 'NO_JIT' else 'D',
                                        markerfacecolor='white', markeredgecolor=COLORS[arm], markersize=5)
                ax.set(xlim=(0, 66), ylim=(0, None), ylabel='Throughput (Mops/s)', xlabel='Workers')
                ax.set_xticks(THREADS)
                ax.tick_params(axis='x', labelsize=7, rotation=45)
                ax.grid(axis='y', alpha=.25)
            for ax in list(axes.flat)[len(panels):]:
                ax.set_visible(False)
            title = 'Best warmed peak' if metric == 'peak' else 'Median whole-run throughput'
            fig.suptitle(f'{kind.capitalize()}: {title} on 10.176.26.71', fontsize=18, x=.06, ha='left')
            handles = [Line2D([0], [0], color=COLORS[a], marker='o', label=LABELS[a]) for a in ARMS]
            handles += [Line2D([0], [0], color=COLORS['kdlock'], marker=m, markerfacecolor='white',
                               linestyle='none', label=label) for m, label in [('o', 'KD NO_JIT'), ('D', 'KD mixed')]]
            fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.5, .42 / height),
                       ncol=5, frameon=False)
            fig.text(.06, .10 / height, '3 rounds · 2 s measured · 32 worker cores/node · 64 workers share a physical core with collection', fontsize=9)
            fig.tight_layout(rect=(0, .80 / height, 1, .97))
            stem = output / f'{kind}-{metric}-throughput'
            fig.savefig(str(stem) + '.png', dpi=160)
            fig.savefig(str(stem) + '.svg')
            plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--no-plots', action='store_true')
    args = parser.parse_args()
    root = args.input.resolve()
    plan = json.loads((root / 'matrix-plan.json').read_text())
    status = json.loads((root / 'matrix-status.json').read_text())
    if status['state'] != 'COMPLETE' or status['expected_sessions'] != 3960:
        raise ValueError('complete 3,960-session matrix required')
    expected_cpus = [*range(32), *range(33, 65)]
    if (status['threads'] != THREADS or status['worker_cpus'] != expected_cpus or
            status['collector_cpu'] != 65):
        raise ValueError('complete 22-point placement required')
    expected_groups = {
        f'{kind}-{workload}' + (f'-c{lines:02d}' if lines else ''):
        (kind, workload, lines)
        for kind in ('spin', 'mutex', 'rwlock')
        for workload, lines in [('rcuht', 0), *[('cacheline', n) for n in
                                 ((1, 2, 4, 8, 16) if kind == 'rwlock' else (1, 8, 16))]]
    }
    if len(plan) != 14 or {p['name'] for p in plan} != set(expected_groups):
        raise ValueError('all 14 payload groups required')
    approved = json.loads((root / 'source-sha256-approved.json').read_text())
    samples, interrupted, environments, parity = [], [], {}, {}
    counts = collections.Counter()
    for group in plan:
        folder = root / group['name']
        records = json.loads((folder / 'records.json').read_text())
        specs = json.loads((folder / 'plan.json').read_text())
        if len(records) != group['expected_sessions'] or {r['name'] for r in records} != {r['name'] for r in specs}:
            raise ValueError('group identities differ: ' + group['name'])
        kind, workload, lines = expected_groups[group['name']]
        expected_configs = {(kind, workload, lines, percent, threads, arm, repeat)
                            for percent in ([1, 20] if kind == 'rwlock' else [None])
                            for threads in THREADS for arm in ARMS for repeat in range(3)}
        actual_configs = {(r['lock_kind'], r['workload'], r['cachelines'],
                           r.get('write_percent'), r['threads'], r['arm'], r['repeat'])
                          for r in records}
        if len(records) != len(expected_configs) or actual_configs != expected_configs:
            raise ValueError('requested configuration matrix differs: ' + group['name'])
        for relative, expected in json.loads((folder / 'source-sha256.json').read_text()).items():
            if digest(folder / 'source' / relative) != expected or relative in approved and approved[relative] != expected:
                raise ValueError('frozen source differs: ' + relative)
            counts['frozen_source_hashes'] += 1
        binary_file = folder / 'binary-sha256.json'
        for original, expected in json.loads(binary_file.read_text()).items():
            _, marker, relative = original.partition('/' + group['name'] + '/')
            file = folder / relative if marker else folder / 'binaries' / Path(original).name
            if digest(file) != expected:
                raise ValueError('retained binary differs: ' + str(file))
            counts['binary_hashes'] += 1
        environments[group['name']] = json.loads((folder / 'environment.json').read_text())
        if (folder / 'parity.json').exists():
            parity[group['name']] = json.loads((folder / 'parity.json').read_text())
        for row in records:
            if row.get('drained') is not True or row.get('execution_status') == 'NOT_RUN':
                raise ValueError('unexecuted/undrained sample: ' + row['name'])
            if row['cpus'] != status['worker_cpus'][:row['threads']] or row['collector_cpu'] != 65:
                raise ValueError('planned placement differs')
            expected_nodes = [0 if cpu < 32 else 1 for cpu in row['cpus']]
            if row.get('cpu_nodes') != expected_nodes:
                raise ValueError('worker NUMA nodes differ')
            if row['arm'] == 'kdlock':
                if row['lock_kind'] == 'rwlock':
                    # RWSession retains its preparation publication and checks
                    # it again around measurement; it does not duplicate it.
                    publication = row.get('publication')
                else:
                    publication = row.get('published_before')
                    if publication != row.get('published_after'):
                        raise ValueError('JIT publication changed during session')
                if row.get('retired') != dict(state=2, modules=0, frames=0, writers=0):
                    raise ValueError('KD source did not fully retire')
                if publication:
                    entry = publication['entry']
                    images = folder / row['name'] / 'workspace/daemon' / hex(entry['entry']) / str(entry['tgid']) / 'asm'
                    for name, expected in publication['images'].items():
                        if digest(images / name) != expected:
                            raise ValueError('retained JIT image differs')
                        counts['jit_image_hashes'] += 1
            if accepted(row):
                independently_check_peak(row)
                counts['independently_recomputed_peaks'] += 1
            samples.append(sample(group['name'], row))
    for attempt in status.get('interrupted_attempts', []):
        folder = (root / attempt['path']).resolve()
        if not folder.is_relative_to(root / 'attempts'):
            raise ValueError('attempt outside retained evidence')
        records = json.loads((folder / 'records.json').read_text())
        executed = [r for r in records if r.get('execution_status') != 'NOT_RUN']
        if len(executed) != attempt['executed_sessions'] or not all(accepted(r) for r in executed):
            raise ValueError('interrupted attempt acceptance differs')
        for relative, expected in json.loads((folder / 'source-sha256.json').read_text()).items():
            if digest(folder / 'source' / relative) != expected or relative in approved and approved[relative] != expected:
                raise ValueError('interrupted source differs')
            counts['interrupted_frozen_source_hashes'] += 1
        for original, expected in json.loads((folder / 'binary-sha256.json').read_text()).items():
            _, marker, relative = original.partition('/' + attempt['group'] + '/')
            file = folder / relative if marker else folder / 'binaries' / Path(original).name
            if digest(file) != expected:
                raise ValueError('interrupted binary differs')
            counts['interrupted_binary_hashes'] += 1
        for row in executed:
            independently_check_peak(row)
            counts['interrupted_independently_recomputed_peaks'] += 1
            if row['arm'] == 'kdlock':
                if (row.get('published_before') != row.get('published_after') or
                        row.get('retired') != dict(state=2, modules=0, frames=0, writers=0)):
                    raise ValueError('interrupted KD publication/retirement differs')
                publication = row.get('published_before')
                if publication:
                    entry = publication['entry']
                    images = folder / row['name'] / 'workspace/daemon' / hex(entry['entry']) / str(entry['tgid']) / 'asm'
                    for name, expected in publication['images'].items():
                        if digest(images / name) != expected:
                            raise ValueError('interrupted JIT image differs')
                        counts['interrupted_jit_image_hashes'] += 1
            retained = sample(attempt['group'], row)
            retained.update(attempt_path=attempt['path'], included_in_statistics=False)
            interrupted.append(retained)
    grouped, separated = collections.defaultdict(list), collections.defaultdict(list)
    for row in samples:
        key = (row['group'], row['write_percent'], row['threads'], row['arm'])
        grouped[key].append(row)
        separated[key + (row['execution_type'],)].append(row)
    if len(samples) != 3960 or any(len(rows) != 3 or {r['repeat'] for r in rows} != {0, 1, 2}
                                   for rows in grouped.values()):
        raise ValueError('three-round matrix differs')
    stats = [aggregate(key, rows) for key, rows in grouped.items()]
    by_execution = [aggregate(key[:4], rows, key[4]) for key, rows in separated.items()]
    comparisons = []
    points = collections.defaultdict(dict)
    for row in stats:
        points[(row['group'], row['write_percent'], row['threads'])][row['arm']] = row
    for (group, percent, threads), arms in points.items():
        row = dict(group=group, write_percent=percent, threads=threads, status='INCOMPLETE')
        if set(arms) == set(ARMS) and all(r['complete'] for r in arms.values()):
            kd = arms['kdlock']
            for arm in ('native', 'tclock'):
                for metric in ('best_peak_ops_s', 'whole_median_ops_s'):
                    row[f'kd_over_{arm}_{metric}'] = kd[metric] / arms[arm][metric]
            row['descriptive_status'] = 'PASS' if all(v >= 1 for k, v in row.items() if k.startswith('kd_over_')) else 'FAIL'
            row['status'] = 'MIXED_EXECUTION' if kd['execution_type'] == 'MIXED' else row['descriptive_status']
        comparisons.append(row)
    verification = dict(counts, sessions=len(samples), accepted_sessions=sum(r['accepted'] for r in samples),
                        excluded_sessions=sum(not r['accepted'] for r in samples), drained_sessions=len(samples),
                        kd_jit_sessions=sum(r['accepted'] and r['arm'] == 'kdlock' and r['jit_bodies'] > 0 for r in samples),
                        kd_no_jit_sessions=sum(r['accepted'] and r['arm'] == 'kdlock' and r['jit_bodies'] == 0 for r in samples),
                        execution_status_counts=dict(collections.Counter(r['execution_status'] for r in samples)),
                        comparison_status_counts=dict(collections.Counter(r['status'] for r in comparisons)),
                        interrupted_attempts=len(status.get('interrupted_attempts', [])),
                        interrupted_executed_sessions=len(interrupted),
                        total_executed_sessions=len(samples)+len(interrupted))
    evidence = dict(matrix_status=status, environments=environments, original_runner_parity=parity,
                    report_generator_sha256=digest(Path(__file__)))
    for name in ('host-environment.json', 'host-final-state.json', 'source-state.json', 'final-audit.json'):
        if (root / name).exists():
            evidence[name] = json.loads((root / name).read_text())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name, rows in (('samples', samples), ('statistics', stats),
                       ('statistics-by-execution', by_execution), ('comparison', comparisons)):
        csv_write(output / (name + '.csv'), rows)
        json_write(output / (name + '.json'), rows)
    if interrupted:
        csv_write(output / 'interrupted-attempts.csv', interrupted)
        json_write(output / 'interrupted-attempts.json', interrupted)
    json_write(output / 'verification.json', verification)
    json_write(output / 'evidence.json', evidence)
    (output / 'README.md').write_text(markdown(stats, comparisons, verification, root.name))
    if not args.no_plots:
        if os.geteuid() != 0 or os.uname().release != '6.1.159-kdclobber2':
            raise ValueError('render plots in the guest')
        plots(stats, plan, output)
    print(json.dumps(verification, sort_keys=True))


if __name__ == '__main__':
    main()
