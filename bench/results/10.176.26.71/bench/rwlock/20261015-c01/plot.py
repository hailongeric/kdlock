#!/usr/bin/env python3
"""Plot verified rwlock throughput; each execution-status group stays separate."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
rows = json.loads((ROOT / 'summary.json').read_text())
threads = [*range(1, 9), *range(12, 61, 4)]
styles = [('native', 'NATIVE', 'Linux Native', '#4c78a8', 'o', '-'),
          ('tclock', 'NATIVE', 'TCLock', '#e58b2b', 's', '-'),
          ('kdlock', 'PASS', 'KD: delegated writers observed', '#237a50', '^', '-'),
          ('kdlock', 'NO_JIT', 'KD: no delegated writers observed', '#237a50', 'v', '--'),
          ('kdlock', 'PARTIAL_JIT', 'KD: partial JIT only', '#ad5797', 'D', ':')]
plt.rcParams.update({'font.size': 10, 'svg.fonttype': 'none', 'svg.hashsalt': 'rwlock-c01-20261015'})
fig, axes = plt.subplots(2, 2, figsize=(13, 8.5), sharex=True)
for row_index, percent in enumerate((1, 20)):
    for column, (field, low, high, title) in enumerate((
            ('best_peak_ops_s', 'peak_min_ops_s', 'peak_max_ops_s', 'Best warmed peak'),
            ('whole_median_ops_s', 'whole_min_ops_s', 'whole_max_ops_s', 'Median whole-run throughput'))):
        ax = axes[row_index, column]
        for arm, status, label, color, marker, line in styles:
            selected = {r['threads']: r for r in rows if r['variant'] == 'cacheline-c01-' + arm
                        and r['jit_status'] == status and r['write_percent'] == percent}
            if not selected:
                continue
            # Missing/mixed-status points create breaks; incomplete groups are hollow markers.
            values = lambda key: [selected[t][key] / 1e6 if t in selected and selected[t]['complete']
                                  else np.nan for t in threads]
            ax.plot(threads, values(field), color=color, marker=marker, linestyle=line,
                    markersize=4, linewidth=1.6, label=label)
            ax.fill_between(threads, values(low), values(high), color=color, alpha=.10)
            for t, r in selected.items():
                if not r['complete']:
                    ax.plot(t, r[field] / 1e6, marker=marker, markerfacecolor='none',
                            markeredgecolor=color, markersize=6, linestyle='none')
        ax.axvline(32, color='#777777', linewidth=.8, linestyle=':')
        ax.set_title(f'{percent}% writes / {100 - percent}% reads — {title}')
        ax.set_ylabel('Million operations / second')
        ax.set_ylim(bottom=0)
        ax.set_xlim(0, 61)
        ax.set_xticks([1, 4, 8, 12, 20, 28, 32, 40, 48, 60])
        ax.grid(axis='y', alpha=.2)
        if row_index == 1:
            ax.set_xlabel('Worker threads')
handles, labels = [], []
for ax in axes.flat:
    for handle, label in zip(*ax.get_legend_handles_labels()):
        if label not in labels:
            handles.append(handle)
            labels.append(label)
fig.legend(handles, labels, loc='lower center', ncol=2, bbox_to_anchor=(.5, .025), frameon=False)
fig.suptitle('One-cacheline rwlock comparison · 64-vCPU VM · 3 rounds per configuration', fontsize=14)
fig.text(.5, .005, 'Bands: observed min–max, not confidence intervals. Hollow markers: fewer than 3 rounds in that JIT-status group.\n'
         'Workers use CPU prefixes; counts above 32 span NUMA nodes. Collector: CPU 63. Four post-work rounds.',
         ha='center', fontsize=9)
fig.tight_layout(rect=(0, .13, 1, .95))
fig.savefig(ROOT / 'throughput.svg', metadata={'Date': None})
fig.savefig(ROOT / 'throughput.png', dpi=180)
# Matplotlib emits spaces before newlines inside SVG paths; normalize the report copy.
svg = ROOT / 'throughput.svg'
svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
