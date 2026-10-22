#!/usr/bin/env python3
"""Summarize this single frozen matrix without merging execution classes."""
import argparse
import collections
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import tempfile


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def table(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: json.dumps(value) if isinstance(value, (list, dict)) else value
                         for key, value in row.items()} for row in rows)


def execution(row):
    if row['arm'] != 'kdlock':
        return row['arm'].upper()
    entries, returned = row.get('jit_bodies', 0), row.get('jit_completions')
    if returned is not None:
        assert type(entries) is int and type(returned) is int and 0 <= returned <= entries
        return 'RETURNED_JIT' if returned else 'PARTIAL_JIT' if entries else 'NO_JIT'
    return 'WITNESSED_JIT' if entries else 'NO_JIT'


def reconstruct_provider(base, output):
    root = Path('/root/host_fs/kdlock')
    frozen = read(base / 'source-sha256.json')
    script = root / 'bench/spin_cacheline/provider/prepare.py'
    assert hashlib.sha256(script.read_bytes()).hexdigest() == frozen[str(script.relative_to(root))]
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('nano_provider_prepare', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='nano-provider-review-') as temporary:
        expected = module.prepare(Path(temporary) / 'provider', root)
    for name, digest in expected['production'].items():
        assert frozen[name] == digest, name
    for name, digest in expected['observation'].items():
        assert frozen['bench/spin_cacheline/provider/' + name] == digest, name
    write(output / 'provider-reconstruction.json', expected)
    return expected


def collect(base, provider):
    jobs = read(base / 'matrix-plan.json')
    frozen = read(base / 'source-sha256.json')
    samples, manifests = [], {}
    for job in jobs:
        folder = base / 'matrix' / job['name']
        specs = read(folder / 'plan.json')
        assert len(specs) == job['expected_sessions']
        prefix = 'bench/spin_cacheline/.build/provider/'
        for relative, digest in read(folder / 'source-sha256.json').items():
            path = folder / 'source' / relative
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, relative
            if relative.startswith(prefix):
                prepared = relative[len(prefix):]
                if prepared == 'manifest.json':
                    assert read(path) == provider, relative
                else:
                    assert provider['prepared'][prepared] == digest, relative
            else:
                assert frozen[relative] == digest, relative
        for name in ('source-sha256.json', 'binary-sha256.json', 'environment.json', 'plan.json'):
            path = folder / name
            manifests[str(path.relative_to(base))] = hashlib.sha256(path.read_bytes()).hexdigest()
        for spec in specs:
            path = folder / spec['name'] / 'session.json'
            row = read(path)
            measurement = row.get('measurement', {})
            klass = execution(row)
            correct = (measurement.get('complete') is True and measurement.get('data_ok') is True
                       and row.get('drained') is True and not row.get('cleanup_error'))
            eligible = (correct and row.get('execution_status') == 'OK'
                        and klass != 'PARTIAL_JIT'
                        and not any(row.get(k, False) for k in ('diagnostic', 'pmu', 'perf_record')))
            family = job['family']
            payload = (f'c{row["cachelines"]:02d}' if row['workload'] == 'cacheline' else
                       f'list{row["list_nodes"]}' if row['workload'] == 'list' else 'rcuht')
            eligible_ops = measurement.get('writes', measurement['completed'])
            entries, returns = row.get('jit_bodies'), row.get('jit_completions')
            sample = dict(job=job['name'], session=spec['name'], lock=family,
                          payload=payload, workload=row['workload'],
                          write_percent=row.get('write_percent', 100),
                          workers=row['threads'], repeat=row['repeat'], backend=row['arm'],
                          execution_class=klass, execution_status=row['execution_status'],
                          correct_and_drained=correct, score_eligible=eligible,
                          jit_entries=row.get('jit_bodies'), jit_completions=row.get('jit_completions'),
                          jit_eligible_operations=eligible_ops,
                          jit_entry_share=entries / eligible_ops if entries is not None and eligible_ops else None,
                          jit_completion_share=returns / eligible_ops if returns is not None and eligible_ops else None,
                          whole_ops_s=measurement['completed'] * 1e9 / measurement['wall_ns'],
                          peak_ops_s=measurement['peak']['throughput_ops_s'],
                          operations=measurement['completed'],
                          collector_cpu=row['collector_cpu'], cpus=row['cpus'],
                          caller_shell=row.get('caller_shell', row.get('rwsem_writer_shell')),
                          receipt=str(path.relative_to(base)),
                          receipt_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            assert sample['collector_cpu'] == 38 and sample['cpus'] == list(range(sample['workers']))
            samples.append(sample)
    assert len(samples) == 3600
    return samples, manifests


def summarize(samples):
    groups = collections.defaultdict(list)
    keys = ('lock', 'payload', 'write_percent', 'workers', 'backend', 'execution_class')
    for row in samples:
        groups[tuple(row[key] for key in keys)].append(row)
    summary = []
    for key, rows in sorted(groups.items()):
        good = [row for row in rows if row['score_eligible']]
        result = dict(zip(keys, key))
        result.update(planned_class_samples=len(rows), valid_samples=len(good),
                      complete=len(good) == 3 and {row['repeat'] for row in good} == {0, 1, 2},
                      sessions=[row['receipt'] for row in rows])
        for metric in ('whole_ops_s', 'peak_ops_s'):
            values = [row[metric] for row in good]
            for name, function in (('min', min), ('median', statistics.median), ('max', max)):
                result[metric + '_' + name] = function(values) if values else None
            result[metric + '_spread_pct'] = (
                100 * (max(values) - min(values)) / statistics.median(values) if values else None)
        summary.append(result)
    controls = {(row['lock'], row['payload'], row['write_percent'], row['workers'], row['backend']): row
                for row in summary if row['backend'] != 'kdlock' and row['complete']}
    comparisons = []
    for row in summary:
        if row['backend'] != 'kdlock' or not row['complete']:
            continue
        for backend in ('native', 'tclock'):
            other = controls.get((row['lock'], row['payload'], row['write_percent'], row['workers'], backend))
            if other:
                comparisons.append(dict(lock=row['lock'], payload=row['payload'],
                    write_percent=row['write_percent'], workers=row['workers'],
                    kd_execution_class=row['execution_class'], control=backend,
                    whole_median_ratio=row['whole_ops_s_median'] / other['whole_ops_s_median'],
                    peak_median_ratio=row['peak_ops_s_median'] / other['peak_ops_s_median'],
                    best_peak_ratio=row['peak_ops_s_max'] / other['peak_ops_s_max']))
    return summary, comparisons


def figures(summary, destination):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors = {'native': '#52525b', 'tclock': '#2563eb', 'kdlock': '#dc2626'}
    markers = {'NATIVE': 'o', 'TCLOCK': 's', 'RETURNED_JIT': '^',
               'WITNESSED_JIT': '^', 'NO_JIT': 'D', 'PARTIAL_JIT': 'x'}
    labels = {'native': 'Linux Native', 'tclock': 'TCLock', 'kdlock': 'KD'}
    for family, percent in (('spin', 100), ('mutex', 100), ('rwlock', 1),
                            ('rwlock', 20), ('rwsem', 1), ('rwsem', 20)):
        for metric in ('whole', 'peak'):
            fig, axes = plt.subplots(2, 3, figsize=(16, 8), constrained_layout=True)
            handles = {}
            for axis, payload in zip(axes.flat, ('c01', 'c08', 'list16', 'list128', 'rcuht')):
                selected = [row for row in summary if row['lock'] == family
                            and row['write_percent'] == percent and row['payload'] == payload]
                groups = collections.defaultdict(list)
                worker_grid = sorted({row['workers'] for row in selected})
                for row in selected:
                    if row['valid_samples']:
                        groups[(row['backend'], row['execution_class'])].append(row)
                for (backend, klass), rows in sorted(groups.items()):
                    rows.sort(key=lambda row: row['workers'])
                    label = labels[backend] + (': ' + klass if backend == 'kdlock' else '')
                    by_workers = {row['workers']: row for row in rows}
                    # Missing or rejected repeats break the curve rather than
                    # implying measured performance across an unscored cohort.
                    values = [by_workers[count][f'{metric}_ops_s_median'] / 1e6
                              if count in by_workers and by_workers[count]['complete']
                              else float('nan') for count in worker_grid]
                    line, = axis.plot(worker_grid, values, color=colors[backend], marker=markers[klass],
                                      linestyle='--' if klass == 'NO_JIT' else '-', linewidth=1.5,
                                      markersize=4, label=label)
                    handles[label] = line
                    for row in rows:
                        if row['complete']:
                            middle = row[f'{metric}_ops_s_median'] / 1e6
                            low = row[f'{metric}_ops_s_min'] / 1e6
                            high = row[f'{metric}_ops_s_max'] / 1e6
                            axis.errorbar(row['workers'], middle, yerr=[[middle-low], [high-middle]],
                                          color=colors[backend], capsize=2, linewidth=.6)
                        else:
                            axis.scatter(row['workers'], row[f'{metric}_ops_s_median'] / 1e6,
                                         edgecolors=colors[backend], facecolors='none',
                                         marker=markers[klass], s=24)
                axis.axvline(20, color='#a1a1aa', linestyle=':', linewidth=1)
                axis.set(title=payload, xlabel='Workers', ylabel='Mops/s', xlim=(0, 37), ylim=(0, None))
                axis.set_xticks((1, 4, 8, 12, 16, 20, 24, 28, 32, 36))
                axis.grid(alpha=.2)
            axes.flat[-1].axis('off')
            axes.flat[-1].legend(handles.values(), handles.keys(), loc='upper left', fontsize=10)
            axes.flat[-1].text(0, .35, 'Median of 3 repeats; bars show min/max.\n'
                              'Hollow points: fewer than 3 eligible repeats.\n'
                              'Execution classes remain separate.\n'
                              'NUMA boundary: 20 workers.\n'
                              + ('TCLock rwsem: unavailable.\n' if family == 'rwsem' else ''),
                              transform=axes.flat[-1].transAxes, fontsize=10, va='top')
            mix = f'{percent}% writes' if family in ('rwlock', 'rwsem') else 'exclusive updates'
            title = 'whole-run throughput' if metric == 'whole' else 'best warmed 300 ms window per run'
            fig.suptitle(f'{family} — {mix} — {title}\n050c1aa · 380G10 temporary VM · 40 vCPUs · collector 38', fontsize=14)
            name = family + (f'-w{percent:02d}' if family in ('rwlock', 'rwsem') else '') + '-' + metric
            fig.savefig(destination / (name + '.png'), dpi=160)
            fig.savefig(destination / (name + '.svg'))
            plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--plots', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    provider = reconstruct_provider(args.base, args.output)
    samples, manifests = collect(args.base, provider)
    summary, comparisons = summarize(samples)
    table(args.output / 'samples.csv', samples)
    table(args.output / 'summary.csv', summary)
    table(args.output / 'comparisons.csv', comparisons)
    write(args.output / 'summary.json', summary)
    write(args.output / 'comparisons.json', comparisons)
    write(args.output / 'input-manifests.json', manifests)
    counts = collections.Counter((row['lock'], row['backend'], row['execution_status'], row['execution_class'])
                                 for row in samples)
    status = dict(expected_sessions=3600, recorded_sessions=len(samples),
                  report_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  correct_and_drained=sum(row['correct_and_drained'] for row in samples),
                  eligible_sessions=sum(row['score_eligible'] for row in samples),
                  complete_summary_groups=sum(row['complete'] for row in summary),
                  classes=[dict(lock=k[0], backend=k[1], status=k[2], execution_class=k[3], count=v)
                           for k, v in sorted(counts.items())],
                  tclock_rwsem='UNAVAILABLE', failed_preflight='64-vCPU shared-collector expectation on 40-vCPU guest')
    write(args.output / 'collection.json', status)
    if args.plots:
        figures(summary, args.output)
    print(json.dumps(status, indent=2))


if __name__ == '__main__':
    main()
