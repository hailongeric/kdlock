#!/usr/bin/env python3
"""Plot audited report tables; no workload or archived-code execution."""
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
rows = list(csv.DictReader((ROOT/'comparisons.csv').open()))
plt.rcParams.update({'font.size': 10, 'svg.fonttype': 'none',
                     'svg.hashsalt': 'kdlock-linux-local-20261014'})
groups = [('baseline', 'Previous KD', '#777777'),
          ('c4', 'Local path, no reuse allowance', '#bd6e25'),
          ('c5-reuse32', 'Reuse 32: screen', '#2872b5'),
          ('c5-reuse32-confirm1', 'Reuse 32: confirmation 1', '#168b80'),
          ('c5-reuse32-confirm2', 'Reuse 32: confirmation 2', '#774ca5')]
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharex=True, sharey=True)
for ax, field, title in zip(axes, ('whole_ratio', 'peak_ratio'),
                             ('Median whole-run throughput', 'Best valid warmed peak')):
    for group, label, color in groups:
        data = sorted((r for r in rows if r['group'] == group), key=lambda r: int(r['threads']))
        assert len(data) == 8
        ax.plot([int(r['threads']) for r in data], [100*float(r[field]) for r in data],
                marker='o', markersize=4, linewidth=1.6, color=color, label=label)
    ax.axhline(97, color='#b33d3d', linestyle='--', linewidth=1)
    ax.set(title=title, xlabel='Workers (CPU 0 through N−1)', xticks=range(1, 9),
           ylim=(0, 165), xlim=(.8, 8.2))
    ax.grid(axis='y', alpha=.2)
    ax.spines[['top', 'right']].set_visible(False)
axes[0].set_ylabel('KD / paired Native throughput (%)')
axes[1].text(7.9, 94, '97% acceptance floor', ha='right', va='top', color='#b33d3d', fontsize=9)
fig.suptitle('c01 / post-work 64: each block uses its own Native control', y=.99)
fig.legend(*axes[0].get_legend_handles_labels(), loc='lower center', ncol=3, frameon=False)
fig.tight_layout(rect=(0, .15, 1, .94))
fig.savefig(ROOT/'throughput.svg', metadata={'Date': None})
svg = ROOT/'throughput.svg'
svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
fig.savefig('/tmp/kdlock-linux-local-throughput.png', dpi=130)
