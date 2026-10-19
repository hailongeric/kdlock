#!/usr/bin/env python3
"""Plot completed compact-mutex comparison.json; never execute workloads.

Run in the guest plotting environment after mutex32-screen-report.py. Both
standalone artifacts are written beside the input report; sources and results
are read-only. Error bars are observed ranges, not confidence intervals.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator


THREADS = (1, 8, 32, 60)
CASES = (('c01', 'c01 · one cacheline'),
         ('c08', 'c08 · eight cachelines'),
         ('rcuht', 'RCUHT · hash updates'))
ARMS = (('native', 'Linux Native', '#4c566a', 's'),
        ('tclock', 'TCLock', '#0072b2', '^'),
        ('kdlock', 'KD', '#d55e00', 'o'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def point(group, label):
    """Return a plotted median and observed range, or a genuine missing point."""
    if group is None:
        return None, 0, 3
    valid, planned = group.get('valid'), group.get('planned')
    require(type(valid) is int and type(planned) is int and 0 <= valid <= planned == 3,
            f'{label}: invalid repeat count')
    values = group.get('whole_mops', {})
    median, low, high = (values.get(name) for name in ('median', 'min', 'max'))
    if not valid:
        require(median is None and low is None and high is None,
                f'{label}: unscored group must not supply plotted rates')
        return None, valid, planned
    require(all(type(value) in (int, float) and math.isfinite(value)
                for value in (median, low, high)) and 0 < low <= median <= high,
            f'{label}: invalid whole-run range')
    return (median, median - low, high - median), valid, planned


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path(
        '/root/kdlock-evidence/10.176.26.71/bench/mutex32-screen-20261019/comparison.json'))
    args = parser.parse_args()
    raw = args.input.read_bytes()
    report = json.loads(raw)
    require(report.get('schema') == 1 and isinstance(report.get('rows'), list),
            'expected compact-mutex comparison schema 1')
    rows = {}
    for row in report['rows']:
        key = (row['case'], row['threads'])
        require(key not in rows, f'duplicate comparison row: {key}')
        require(key[0] in {case for case, _ in CASES} and key[1] in THREADS,
                f'unexpected comparison row: {key}')
        rows[key] = row

    values = {}
    for case, _ in CASES:
        for arm, _, _, _ in ARMS:
            for threads in THREADS:
                group = rows.get((case, threads), {}).get('backends', {}).get(arm)
                values[case, arm, threads] = point(group, f'{case}/{threads}/{arm}')
    all_complete = all(valid == planned == 3 for _, valid, planned in values.values())
    provenance = ('Input comparison.json SHA256: ' + hashlib.sha256(raw).hexdigest() +
                  '. Median whole-run Mops/s; error bars show observed min–max over eligible repeats.')
    plt.rcParams.update({
        'font.family': 'DejaVu Sans', 'font.size': 10,
        'axes.titlesize': 12, 'axes.labelsize': 10,
        'xtick.labelsize': 9, 'ytick.labelsize': 9,
        'svg.fonttype': 'none', 'svg.hashsalt': 'mutex32-screen',
        'savefig.facecolor': 'white', 'figure.facecolor': 'white',
    })
    figure, axes = plt.subplots(1, 3, figsize=(13.2, 5.1), sharex=True)
    figure.subplots_adjust(left=0.065, right=0.985, bottom=0.30, top=0.72, wspace=0.27)
    figure.suptitle('Compact mutex workload comparison', fontsize=16, y=0.97)
    count_note = ('n = 3 valid runs at every point' if all_complete else
                  'Eligible runs only; incomplete points show valid runs / 3')
    figure.text(0.5, 0.90, 'Median whole-run throughput · ' + count_note,
                ha='center', va='center', color='#3e4650', fontsize=10)
    handles = [Line2D([0], [0], color=color, marker=marker, linewidth=1.7,
                      markersize=5.5, label=label) for _, label, color, marker in ARMS]
    figure.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, 0.86),
                  ncol=3, frameon=False, handlelength=2.8, columnspacing=3.0)

    for axis, (case, title) in zip(axes, CASES):
        absent = {}
        maximum = 0.0
        for arm, label, color, marker in ARMS:
            medians, lowers, uppers = [], [], []
            for threads in THREADS:
                value, valid, planned = values[case, arm, threads]
                if value is None:
                    # NaN breaks the connecting line; no marker is placed at
                    # zero or any other invented throughput for absent data.
                    medians.append(float('nan'))
                    lowers.append(float('nan'))
                    uppers.append(float('nan'))
                    absent.setdefault(label, []).append(threads)
                    continue
                median, lower, upper = value
                medians.append(median)
                lowers.append(lower)
                uppers.append(upper)
                maximum = max(maximum, median + upper)
                if valid < planned:
                    axis.annotate(f'n={valid}/{planned}', (threads, median),
                                  xytext=(0, 9), textcoords='offset points',
                                  ha='center', va='bottom', color=color, fontsize=8,
                                  bbox=dict(facecolor='white', edgecolor='none', pad=0.6))
            if any(math.isfinite(value) for value in medians):
                axis.errorbar(THREADS, medians, yerr=[lowers, uppers],
                              color=color, marker=marker, linewidth=1.7, markersize=5.5,
                              elinewidth=1.1, capsize=3.2, capthick=1.1, zorder=3)
        axis.set_title(title, pad=12)
        axis.set_xlabel('Workers', labelpad=7)
        axis.set_xticks(THREADS)
        axis.set_xlim(0, 64)
        axis.set_ylim(0, maximum * 1.18 if maximum else 1)
        axis.yaxis.set_major_locator(MaxNLocator(nbins=5))
        if not maximum:
            axis.set_yticks([])
            axis.text(0.5, 0.5, 'No valid measurements', transform=axis.transAxes,
                      ha='center', va='center', color='#555b63')
        axis.tick_params(axis='both', length=3.0, color='#89919a')
        axis.grid(axis='y', color='#d9dee4', linewidth=0.7, zorder=0)
        axis.spines['top'].set_visible(False)
        axis.spines['right'].set_visible(False)
        axis.spines['left'].set_color('#a8afb7')
        axis.spines['bottom'].set_color('#a8afb7')
        if absent:
            # Missing groups are described outside the data area, never as
            # a throughput point or an interpolated segment across the gap.
            notes = [f'{label}: no valid runs at ' + ', '.join(map(str, counts))
                     for label, counts in absent.items()]
            axis.text(0, -0.34, '\n'.join(notes), transform=axis.transAxes,
                      ha='left', va='top', fontsize=7.5, color='#555b63')
    axes[0].set_ylabel('Throughput (million operations/s)', labelpad=8)
    figure.text(0.065, 0.075,
                'Error bars show observed min–max variation, not confidence intervals. '
                'Lines connect measured worker counts; no smoothing.',
                ha='left', va='center', fontsize=9, color='#555b63')
    figure.text(0.065, 0.035,
                'Fresh Native and TCLock controls. Failed or unscored sessions are excluded; '
                'single-worker KD throughput does not imply delegation.',
                ha='left', va='center', fontsize=9, color='#555b63')
    output = args.input.resolve().parent
    figure.savefig(output / 'comparison.svg', metadata={
        'Title': 'Compact mutex workload comparison', 'Description': provenance,
        'Creator': 'mutex32-screen-plot.py'})
    figure.savefig(output / 'comparison.png', dpi=220, metadata={
        'Title': 'Compact mutex workload comparison', 'Description': provenance,
        'Software': 'mutex32-screen-plot.py'})
    plt.close(figure)
    print(json.dumps(dict(input=str(args.input.resolve()),
                          comparison_sha256=hashlib.sha256(raw).hexdigest(),
                          all_groups_complete=all_complete,
                          outputs=[str(output / name) for name in ('comparison.svg', 'comparison.png')]),
                     sort_keys=True))


if __name__ == '__main__':
    main()
