#!/usr/bin/env python3
"""Plot the compact-mutex API screen's comparison.json in the guest.

Run with the guest plotting environment after summarize.py. The input report is
read-only; comparison.svg and comparison.png are written beside it. Error bars
show the observed eligible-repeat range, not a confidence interval. Separate KD
execution groups are never combined into a plotted rate.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import textwrap

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator


THREADS = (1, 8, 32, 60)
CASES = (
    ('pipebytes-query', 'Pipe byte count · FIONREAD',
     'n16 · 16 occupied buffers, 64 KiB buffered'),
    ('pipecap-query', 'Pipe capacity · F_GETPIPE_SZ',
     'n16 · requested capacity of 64 KiB'),
    ('seek-set', 'File position · SEEK_SET', 'n16 · shared 64 KiB file'),
    ('seek-end', 'File position · SEEK_END', 'n16 · shared 64 KiB file'),
)
ARMS = (
    ('native', 'Linux Native', '#4c566a', 's'),
    ('tclock', 'TCLock', '#0072b2', '^'),
    ('kdlock', 'KD', '#d55e00', 'o'),
)
STATUSES = {'COMPLETE', 'PARTIAL', 'NO_VALID', 'MIXED_EXECUTION_GROUPS'}
EXECUTION_GROUPS = {'NOT_APPLICABLE', 'PASS', 'PARTIAL_JIT', 'NO_JIT', 'MIXED'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def point(group, label, arm):
    """Validate an aggregate without replacing missing rates with zeros."""
    if group is None:
        return dict(value=None, valid=0, planned=3, status='MISSING', execution=None)
    valid, planned = group.get('valid'), group.get('planned')
    status, execution = group.get('status'), group.get('execution_group')
    require(type(valid) is int and type(planned) is int and 0 <= valid <= planned == 3,
            f'{label}: invalid repeat count')
    require(status in STATUSES, f'{label}: unknown aggregate status: {status}')
    require(execution in EXECUTION_GROUPS or not valid,
            f'{label}: unknown execution group: {execution}')
    require(arm == 'kdlock' or execution == 'NOT_APPLICABLE'
            or (valid == 0 and execution == 'UNSCORED'),
            f'{label}: non-KD execution group differs')
    require((status == 'MIXED_EXECUTION_GROUPS') == (execution == 'MIXED'),
            f'{label}: mixed execution labels disagree')
    result = dict(value=None, valid=valid, planned=planned,
                  status=status, execution=execution)
    values = group.get('whole_mops', {})
    require(isinstance(values, dict), f'{label}: whole_mops must be an object')
    median, low, high = (values.get(name) for name in ('median', 'min', 'max'))
    if not valid or execution == 'MIXED':
        require(median is None and low is None and high is None,
                f'{label}: absent or mixed groups must not supply pooled rates')
        return result
    require(status != 'NO_VALID', f'{label}: valid runs labelled NO_VALID')
    require(all(type(value) in (int, float) and math.isfinite(value)
                for value in (median, low, high)) and 0 < low <= median <= high,
            f'{label}: invalid whole-interval throughput range')
    result['value'] = (median, median - low, high - median)
    return result


def plot_series(axis, points, arm, color, marker):
    """Break lines at missing points and changes in KD execution category."""
    last = None
    for threads, item in zip(THREADS, points):
        value = item['value']
        if value is None:
            last = None
            continue
        median, lower, upper = value
        category = item['execution'] if arm == 'kdlock' else arm
        if last is not None and last[2] == category:
            axis.plot([last[0], threads], [last[1], median], color=color,
                      linewidth=1.6, zorder=2)
        current_marker = 'x' if arm == 'kdlock' and category == 'PARTIAL_JIT' else marker
        face = 'white' if arm == 'kdlock' and category == 'NO_JIT' else color
        axis.errorbar([threads], [median], yerr=[[lower], [upper]],
                      color=color, marker=current_marker, markerfacecolor=face,
                      markeredgecolor=color, markeredgewidth=1.3, markersize=5.7,
                      linestyle='none', elinewidth=1.1, capsize=3.2, capthick=1.1,
                      zorder=3)
        if item['valid'] < item['planned']:
            axis.annotate(f"n={item['valid']}/{item['planned']}", (threads, median),
                          xytext=(0, 9), textcoords='offset points', ha='center',
                          va='bottom', color=color, fontsize=8,
                          bbox=dict(facecolor='white', edgecolor='none', pad=0.6))
        last = (threads, median, category)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path(
        '/root/kdlock-evidence/10.176.26.71/bench/mutex32-api-screen-20261019/comparison.json'))
    args = parser.parse_args()
    raw = args.input.read_bytes()
    report = json.loads(raw)
    require(report.get('schema') == 1 and isinstance(report.get('rows'), list),
            'expected compact-mutex API comparison schema 1')
    rows = {}
    for row in report['rows']:
        key = (row['case'], row['threads'])
        require(key not in rows, f'duplicate comparison row: {key}')
        require(key[0] in {case for case, _, _ in CASES} and key[1] in THREADS,
                f'unexpected comparison row: {key}')
        require(row.get('entries') == 16, f'{key}: expected n16 workload setup')
        rows[key] = row
    values = {}
    for case, _, _ in CASES:
        for arm, _, _, _ in ARMS:
            for threads in THREADS:
                group = rows.get((case, threads), {}).get('backends', {}).get(arm)
                values[case, arm, threads] = point(group, f'{case}/{threads}/{arm}', arm)
    complete = all(item['value'] is not None and item['valid'] == 3
                   for item in values.values())
    digest = hashlib.sha256(raw).hexdigest()
    provenance = ('Input comparison.json SHA256: ' + digest +
                  '. Median whole-interval Mops/s; error bars are observed min–max. '
                  'Mixed KD execution groups have no combined point.')
    plt.rcParams.update({
        'font.family': 'DejaVu Sans', 'font.size': 10,
        'axes.titlesize': 12, 'axes.labelsize': 10,
        'xtick.labelsize': 9, 'ytick.labelsize': 9,
        'svg.fonttype': 'none', 'svg.hashsalt': 'mutex32-api-screen',
        'savefig.facecolor': 'white', 'figure.facecolor': 'white',
    })
    figure, axes = plt.subplots(2, 2, figsize=(12.4, 9.6), sharex=True)
    figure.subplots_adjust(left=0.08, right=0.98, bottom=0.22, top=0.79,
                           hspace=0.80, wspace=0.25)
    figure.suptitle('Compact mutex · kernel API workloads', fontsize=17, y=0.97)
    count_note = ('3 eligible runs at every point' if complete else
                  '3 planned repeats per point; incomplete points show eligible runs / 3')
    figure.text(0.5, 0.925, 'Median whole-interval throughput · ' + count_note,
                ha='center', va='center', color='#3e4650', fontsize=10)
    handles = [Line2D([0], [0], color=color, marker=marker, linewidth=1.6,
                      markersize=5.7, label=label) for _, label, color, marker in ARMS]
    figure.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, 0.90),
                  ncol=3, frameon=False, handlelength=2.8, columnspacing=3.0)

    for axis, (case, title, setup) in zip(axes.flat, CASES):
        maximum = 0.0
        missing = {}
        for arm, label, color, marker in ARMS:
            points = [values[case, arm, threads] for threads in THREADS]
            plot_series(axis, points, arm, color, marker)
            for threads, item in zip(THREADS, points):
                if item['value'] is not None:
                    median, _, upper = item['value']
                    maximum = max(maximum, median + upper)
                elif arm != 'kdlock':
                    missing.setdefault(label, []).append(threads)
        axis.set_title(title, pad=28, loc='left')
        axis.text(0, 1.07, setup, transform=axis.transAxes, ha='left', va='bottom',
                  fontsize=9, color='#555b63')
        axis.set_xlabel('Workers', labelpad=7)
        axis.set_ylabel('Throughput (million operations/s)', labelpad=8)
        axis.set_xticks(THREADS)
        axis.tick_params(axis='x', labelbottom=True)
        axis.set_xlim(-1, 64)
        axis.set_ylim(0, maximum * 1.20 if maximum else 1)
        axis.yaxis.set_major_locator(MaxNLocator(nbins=5))
        if not maximum:
            axis.set_yticks([])
            axis.text(0.5, 0.5, 'No eligible aggregate measurements',
                      transform=axis.transAxes, ha='center', va='center', color='#555b63')
        axis.tick_params(axis='both', length=3.0, color='#89919a')
        axis.grid(axis='y', color='#d9dee4', linewidth=0.7, zorder=0)
        for side in ('top', 'right'):
            axis.spines[side].set_visible(False)
        for side in ('left', 'bottom'):
            axis.spines[side].set_color('#a8afb7')
        kd_labels = []
        for threads in THREADS:
            item = values[case, 'kdlock', threads]
            label = item['execution'] or item['status']
            if item['value'] is None and label != 'MIXED':
                label = 'NO POINT'
            kd_labels.append(f'{threads}w {label}')
        note = 'KD execution: ' + '; '.join(kd_labels)
        if missing:
            note += '\n' + '; '.join(
                f'{label} missing: ' + '/'.join(map(str, counts)) + 'w'
                for label, counts in missing.items())
        note = '\n'.join(textwrap.fill(line, width=79) for line in note.splitlines())
        axis.text(0, -0.29, note, transform=axis.transAxes, ha='left', va='top',
                  fontsize=8, color='#555b63', linespacing=1.4)

    footnotes = (
        'Error bars show observed min–max variation across eligible repeats, not confidence intervals.',
        'KD markers: filled circle = PASS (returned JIT); hollow circle = NO_JIT; × = PARTIAL_JIT.',
        'Mixed execution groups have no combined point. Lines stop at missing data or a change in KD execution group.',
    )
    for y, note in zip((0.080, 0.052, 0.024), footnotes):
        figure.text(0.08, y, note, ha='left', va='center', fontsize=9, color='#555b63')
    output = args.input.resolve().parent
    figure.savefig(output / 'comparison.svg', metadata={
        'Title': 'Compact mutex kernel API workloads', 'Description': provenance,
        'Creator': 'mutex32-api-screen/plot.py'})
    figure.savefig(output / 'comparison.png', dpi=220, metadata={
        'Title': 'Compact mutex kernel API workloads', 'Description': provenance,
        'Software': 'mutex32-api-screen/plot.py'})
    plt.close(figure)
    print(json.dumps(dict(input=str(args.input.resolve()), comparison_sha256=digest,
                          all_groups_complete=complete,
                          mixed_points=sum(item['execution'] == 'MIXED'
                                           for item in values.values()),
                          absent_points=sum(item['value'] is None for item in values.values()),
                          outputs=[str(output / name) for name in
                                   ('comparison.svg', 'comparison.png')]), sort_keys=True))


if __name__ == '__main__':
    main()
