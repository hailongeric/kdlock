#!/usr/bin/env python3
"""Export recorded rwlock measurements; performs no live benchmark or module I/O.

Usage: python3 export.py /path/to/matrix/records.json /path/to/report
Requires matplotlib only for the standalone SVG figures.
"""
import argparse
import collections
import csv
import json
from pathlib import Path
import statistics


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def export(source, out):
    rows = json.loads(source.read_text())
    threads = [1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 28, 32, 36]
    expected = {(p, n, arm, repeat) for p in (1, 20) for n in threads
                for arm in ('native', 'tclock', 'kdlock') for repeat in range(3)}
    actual = [(r['write_percent'], r['threads'], r['arm'], r['repeat']) for r in rows]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError('expected exactly 270 distinct two-mix comparison sessions')
    groups = collections.defaultdict(list)
    samples, nodes = [], []
    for r in rows:
        m = r.get('measurement', {})
        if (r['execution_status'] != 'OK' or not r['drained'] or
                not m.get('complete') or not m.get('data_ok')):
            raise ValueError('incomplete or failed session: ' + r['name'])
        if (r['workload'] != 'rcuht' or r['cachelines'] != 0 or r['functional'] or
                r['post_work_rounds'] != 4 or r['duration_ms'] != 2000):
            raise ValueError('different workload or measurement contract')
        peak = m['peak']
        samples.append(dict(name=r['name'], write_percent=r['write_percent'], threads=r['threads'],
            arm=r['arm'], repeat=r['repeat'], jit_status=r['jit_status'],
            completed=m['completed'], reads=m['reads'], writes=m['writes'],
            peak_ops_s=peak['throughput_ops_s'], peak_read_ops_s=peak['read_ops_s'],
            peak_write_ops_s=peak['write_ops_s'], peak_elapsed_ns=peak['elapsed_ns'],
            whole_ops_s=m['completed'] * 1e9 / m['wall_ns'],
            whole_read_ops_s=m['reads'] * 1e9 / m['wall_ns'],
            whole_write_ops_s=m['writes'] * 1e9 / m['wall_ns'],
            jit_bodies=r['jit_bodies'], jit_writer_share=r['jit_writer_share'],
            peak_worker_min=min(peak['worker_completed']),
            whole_worker_min=min(w['completed'] for w in m['workers']), drained=r['drained']))
        groups[r['write_percent'], r['threads'], r['arm'], r['jit_status']].append(samples[-1])
        for node in sorted(set(r['cpu_nodes'])):
            indices = [i for i, n in enumerate(r['cpu_nodes']) if n == node]
            peak_count = sum(peak['worker_completed'][i] for i in indices)
            whole_count = sum(m['workers'][i]['completed'] for i in indices)
            nodes.append(dict(name=r['name'], write_percent=r['write_percent'], threads=r['threads'],
                arm=r['arm'], repeat=r['repeat'], jit_status=r['jit_status'], node=node,
                workers=len(indices), peak_completed=peak_count,
                peak_share=peak_count / peak['completed'], whole_completed=whole_count,
                whole_share=whole_count / m['completed']))
    stats = []
    for (percent, count, arm, status), cohort in sorted(groups.items()):
        s = dict(write_percent=percent, threads=count, arm=arm, jit_status=status,
                 rounds=len(cohort), expected_rounds=3, complete=len(cohort) == 3)
        for label in ('peak', 'whole'):
            values = [r[label + '_ops_s'] for r in cohort]
            s.update({label + '_min_ops_s': min(values),
                      label + '_median_ops_s': statistics.median(values),
                      label + '_max_ops_s': max(values),
                      label + '_spread_pct': (max(values) - min(values)) * 100 / min(values)})
        shares = [r['jit_writer_share'] for r in cohort]
        s.update(jit_bodies=sum(r['jit_bodies'] for r in cohort),
                 jit_writer_share_min=min(shares), jit_writer_share_max=max(shares),
                 samples=';'.join(r['name'] for r in cohort))
        stats.append(s)
    out.mkdir(parents=True, exist_ok=True)
    for name, data in (('samples.csv', samples), ('statistics.csv', stats), ('node-progress.csv', nodes)):
        write_csv(out / name, data)
    lookup = {(r['write_percent'], r['threads'], r['arm'], r['jit_status']): r for r in stats}
    text = ['# RCUHT rwlock scaling: all measured thread counts', '',
            'Each cell is **best warmed peak / median whole-run Mops/s (rounds/3)**.',
            'KD JIT-positive and NO_JIT rounds are separate groups. All 270 sessions completed.',
            ('All execution-status groups contain three rounds.' if all(r['complete'] for r in stats) else
             'Some groups are partial after separating JIT and NO_JIT rounds; see their counts.'), '',
            'Workers use CPUs `0..N-1`; counts above 20 cross from node 0 to node 1.',
            'TCLock delegation share is unmeasured. Spread in the CSV uses `(max-min)/min`.', '']
    def cell(percent, count, arm, status):
        row = lookup.get((percent, count, arm, status))
        return ('—' if row is None else
                f'{row["peak_max_ops_s"] / 1e6:.3f} / {row["whole_median_ops_s"] / 1e6:.3f} ({row["rounds"]}/3)')
    for percent in (1, 20):
        text += [f'## {percent}% writes / {100 - percent}% reads', '',
                 '| Workers | Linux native | TCLock | KD, JIT observed | KD, NO_JIT |',
                 '| ---: | ---: | ---: | ---: | ---: |']
        for count in threads:
            text.append('| ' + str(count) + ' | ' + ' | '.join(
                cell(percent, count, arm, status) for arm, status in
                (('native', 'NATIVE'), ('tclock', 'NATIVE'), ('kdlock', 'PASS'), ('kdlock', 'NO_JIT'))) + ' |')
        text.append('')
    (out / 'matrix.md').write_text('\n'.join(text))

    # Preserve the runner's strict decision alongside rates, including partial
    # execution-status groups instead of silently pooling them.
    parity = json.loads(source.with_name('parity.json').read_text())
    (out / 'parity.json').write_text(json.dumps(parity, indent=2) + '\n')
    parity_text = ['# RCUHT throughput target', '', parity['criterion'] + '.', '',
                   'Overall result: **' + parity['status'] + '**. Ratios below 1 fail.',
                   'Both metrics must meet both comparators. Mixed JIT/NO_JIT groups are incomplete.', '',
                   '| Writes | Workers | KD/native peak | KD/native whole | KD/TCLock peak | KD/TCLock whole | Result |',
                   '| ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for r in parity['points']:
        if 'ratios' in r:
            values = [f"{r['ratios'][arm][metric]:.4f}" for arm in ('native', 'tclock')
                      for metric in ('best_peak', 'median_whole')]
        else:
            values = ['—'] * 4
        parity_text.append('| ' + ' | '.join([str(r['write_percent']) + '%', str(r['threads']),
                           *values, r['status']]) + ' |')
    (out / 'parity.md').write_text('\n'.join(parity_text) + '\n')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'svg.hashsalt': 'rwlock-rcuht-20261010', 'font.size': 10})
    series = [('native', 'NATIVE', 'Linux native', '#2563eb', 'o', '-'),
              ('tclock', 'NATIVE', 'TCLock', '#c76b13', 's', '-'),
              ('kdlock', 'PASS', 'KD: JIT observed', '#7e22ce', 'D', '-'),
              ('kdlock', 'NO_JIT', 'KD: NO_JIT', '#7e22ce', 'o', '--')]
    for filename, field, title, minimum in (
            ('peak-scaling.svg', 'peak_max_ops_s', 'Best validated warmed peak', 1),
            ('whole-scaling.svg', 'whole_median_ops_s', 'Median whole-run throughput', 1),
            ('contended-scaling.svg', 'peak_max_ops_s', 'Best validated warmed peak: 2–36 workers', 2)):
        plotted = [n for n in threads if n >= minimum]
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout='constrained')
        for ax, percent in zip(axes, (1, 20)):
            for arm, status, label, color, marker, style in series:
                cohort = [lookup.get((percent, count, arm, status)) for count in plotted]
                values = [r[field] / 1e6 if r else float('nan') for r in cohort]
                ax.plot(plotted, values, label=label, color=color, marker=marker,
                        linestyle=style, markersize=4,
                        markerfacecolor='none' if status == 'NO_JIT' else color)
                # Show run-to-run range within each execution-status group.
                low = [r[field.split('_')[0] + '_min_ops_s'] / 1e6 if r else float('nan') for r in cohort]
                high = [r[field.split('_')[0] + '_max_ops_s'] / 1e6 if r else float('nan') for r in cohort]
                ax.fill_between(plotted, low, high, color=color, alpha=.08)
            ax.axvline(20, color='#777777', linewidth=.8, linestyle=':')
            ax.set(title=f'{percent}% writes / {100 - percent}% reads', xlabel='Workers',
                   ylabel='Million operations / second', xlim=(minimum - .5, 36.5), ylim=(0, None))
            ax.set_xticks([minimum, 4, 8, 12, 16, 20, 24, 28, 32, 36])
            ax.grid(axis='y', alpha=.2)
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc='outside lower center', ncols=4, frameon=False)
        fig.suptitle(title + '\nRCUHT, four post-work rounds; bands show min–max within each group')
        fig.savefig(out / filename, metadata={'Date': None})
        svg = out / filename
        svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
        # PNG companion makes the scientific plot easy to preview and share.
        fig.savefig(out / filename.replace('.svg', '.png'), dpi=150)
        plt.close(fig)
    print(f'Exported {len(samples)} sessions and {len(stats)} separate execution-status groups.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('records', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    export(args.records, args.output)
