#!/usr/bin/env python3
"""Plot audited c01 throughput offline; markers represent measured counts only."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--refill-label', default='refill')
    parser.add_argument('--ranges', action='store_true',
                        help='show the minimum-to-maximum range across the three rounds')
    args = parser.parse_args()
    statistics_path = args.directory / 'statistics.csv'
    coverage_path = args.directory / 'coverage.json'
    coverage = json.loads(coverage_path.read_text())
    assert coverage['passed'] and coverage['post_work_rounds'] == 64
    with statistics_path.open() as stream:
        rows = list(csv.DictReader(stream))

    series = [
        ('baseline', 'native', 'Linux mutex baseline', '#303030', 'o'),
        ('baseline', 'tclock', 'TCLock baseline', '#b77900', '^'),
        ('baseline', 'kdlock', 'Legacy KD baseline', '#1766a4', 's'),
        ('finite', 'kdlock', 'Owned finite FIFO', '#c13d39', 'D'),
        (args.refill_label, 'kdlock', 'Owned bounded FIFO refill', '#268653', '*'),
    ]
    plt.rcParams.update({'font.size': 10, 'svg.fonttype': 'none',
                         'svg.hashsalt': 'owned-mutex-c01-20261013'})
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2), sharey=True)
    all_values = []
    for group, arm, label, color, marker in series:
        receipt = coverage['runs'][group]
        assert receipt['score_eligible'] and not receipt['diagnostic'], group
        cohort = sorted((r for r in rows if r['group'] == group and r['arm'] == arm),
                        key=lambda r: int(r['threads']))
        assert cohort and len({r['threads'] for r in cohort}) == len(cohort), group
        assert all(r['diagnostic'] == 'False' and r['score_eligible'] == 'True' and
                   r['sessions'] == '3' for r in cohort), group
        counts = [int(r['threads']) for r in cohort]
        for axis, field, low, high in zip(axes,
                ('whole_median_mops', 'peak_best_mops'),
                ('whole_min_mops', 'peak_min_mops'),
                ('whole_max_mops', 'peak_best_mops')):
            values = [float(r[field]) for r in cohort]
            all_values.extend(values)
            errors = None
            if args.ranges:
                errors = [[max(0, float(r[field]) - float(r[low])) for r in cohort],
                          [max(0, float(r[high]) - float(r[field])) for r in cohort]]
            # No connecting lines: intermediate worker counts are unmeasured.
            axis.errorbar(counts, values, yerr=errors, linestyle='none', marker=marker,
                          markersize=8 if marker == '*' else 5, color=color,
                          markeredgewidth=.8, alpha=.9, elinewidth=.65, capsize=2,
                          label=f'{label} ({len(counts)} counts)')

    for axis, title in zip(axes, ('Median whole-run throughput', 'Best valid warmed peak')):
        axis.set(title=title, xlabel='Workers', xlim=(0, 62), ylim=(0, max(all_values) * 1.07))
        axis.set_xticks([1, 4, 8, 12, 16, 20, 24, 28, 32, 36, 48, 60])
        axis.grid(alpha=.18)
        axis.spines[['top', 'right']].set_visible(False)
    axes[0].set_ylabel('Throughput (Mops/s)')
    fig.suptitle('cacheline-c01 mutex: 64 post-work rounds', fontsize=13, y=.98)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='lower center', bbox_to_anchor=(.5, .07),
               ncol=3, frameon=False, fontsize=9)
    note = ('Three rounds; 48,000 warmup operations/worker; 2 s measurement; 300 ms warmed peak.\n'
            'Markers show measured counts only. Native is the baseline cohort; acceptance uses each candidate’s paired controls.')
    if args.ranges:
        note += '\nWhiskers show the minimum-to-maximum range across rounds, not confidence intervals.'
    fig.text(.5, .018, note, ha='center', va='bottom', fontsize=8)
    fig.subplots_adjust(left=.065, right=.99, top=.87, bottom=.27, wspace=.12)
    sha = hashlib.sha256(statistics_path.read_bytes()).hexdigest()
    output = args.directory / 'throughput.svg'
    fig.savefig(output, metadata={'Date': None,
        'Title': 'Audited cacheline-c01 mutex throughput, 64 post-work rounds',
        'Description': 'Only scored measurements; no interpolation. statistics.csv SHA256=' + sha})
    plt.close(fig)
    output.write_text('\n'.join(line.rstrip() for line in output.read_text().splitlines()) + '\n')
    print(output)


if __name__ == '__main__':
    main()
