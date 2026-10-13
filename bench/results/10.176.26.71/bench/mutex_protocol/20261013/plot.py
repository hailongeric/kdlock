#!/usr/bin/env python3
"""Render offline figures from the audited, unpooled statistics table."""
import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--directory', type=Path, default=Path(__file__).resolve().parent)
parser.add_argument('--candidates', nargs='+', default=['frame-width', 'epoch'])
args = parser.parse_args()
rows = list(csv.DictReader((args.directory/'statistics.csv').open()))
rounds = {row['post_work_rounds'] for row in rows}
assert len(rounds) == 1, 'do not mix workloads in a figure'
data = {(row['series'], int(row['threads']), row['arm']): row for row in rows}
plt.rcParams.update({'font.size': 10, 'svg.hashsalt': 'mutex-protocol-c01'})
fig, axes = plt.subplots(1, 2, figsize=(12, 4.3), constrained_layout=True)
colors = {'native': '#333333', 'tclock': '#d48806', 'kdlock': '#1766a4'}
labels = {'native': 'Linux mutex', 'tclock': 'TCLock mutex', 'kdlock': 'Baseline KD'}
counts = sorted({t for name, t, arm in data if name == 'baseline'})
for arm in ('native', 'tclock', 'kdlock'):
    axes[0].plot(counts, [float(data['baseline', t, arm]['whole_median_mops'])
                         for t in counts], marker='.', color=colors[arm], label=labels[arm])
axes[0].set(title=f'Fresh baseline: {next(iter(rounds))} post-work rounds',
            xlabel='Workers', ylabel='Median whole-run throughput (Mops/s)')
axes[0].set_xticks([1, 8, 16, 28, 36, 48, 60])
axes[0].legend(frameon=False)
for name, color in zip(args.candidates, ['#1766a4', '#268653', '#c34940', '#875ca6']):
    counts = [t for t in (4, 16, 28) if (name, t, 'kdlock') in data]
    for field, style, label in [('whole_median_mops', '-', 'median'),
                                ('best_peak_mops', '--', 'peak')]:
        ratios = [float(data[name, t, 'kdlock'][field]) /
                  float(data[name, t, 'native'][field]) for t in counts]
        axes[1].plot(counts, ratios, marker='o', linestyle=style, color=color,
                     label=f'{name}: {label}')
axes[1].axhline(.97, color='#555555', linewidth=1, linestyle=':', label='97% gate')
axes[1].set(title='Candidates / their paired Native controls', xlabel='Workers',
            ylabel='Throughput ratio', xticks=[4, 16, 28])
axes[1].legend(frameon=False, fontsize=9)
for axis in axes:
    axis.grid(alpha=.2)
    axis.spines[['top', 'right']].set_visible(False)
output = args.directory/'throughput.svg'
fig.savefig(output, metadata={'Date': None})
output.write_text('\n'.join(line.rstrip() for line in output.read_text().splitlines()) + '\n')
