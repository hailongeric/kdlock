#!/usr/bin/env python3
"""VM-only plot of the four-version mutex comparison; never run workloads.

Read summarize.py's comparison.json and export comparison.svg/comparison.png
beside it. Plot only plain-session aggregates, retaining execution classes.
Observed min/max bars are repetition ranges, not confidence intervals.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import textwrap

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator


ARMS = (
    ('compact-rcu', '32 B · RCU registry', '#536175', 's'),
    ('precompact-256', '256 B · inline state', '#0072b2', '^'),
    ('compact-index', '32 B · direct index', '#d55e00', 'o'),
    ('compact-transfer', '32 B · index + ref transfer', '#009e73', 'D'),
)
CASES = (
    ('c01', 'c01 · one cacheline', 'synthetic', (8, 60),
     'Shared counter payload · outer clobber caller'),
    ('c08', 'c08 · eight cachelines', 'synthetic', (8, 60),
     'Shared counter payload · outer clobber caller'),
    ('seek-set-n16', 'File position · SEEK_SET', 'seek', (8, 60),
     'n16 · shared 64 KiB file'),
    ('pipebytes-query-n16', 'Pipe byte count · FIONREAD', 'pipe', (8, 60),
     'n16 · 16 occupied buffers, 64 KiB buffered'),
)
CLASSES = {'RETURNED_JIT', 'WITNESSED_JIT', 'NO_JIT', 'PARTIAL_JIT', 'MIXED', 'UNSCORED'}
STATUSES = {'COMPLETE', 'INCOMPLETE', 'MIXED_EXECUTION_CLASSES'}
SHORT_NAMES = {'compact-rcu': 'RCU', 'precompact-256': 'Inline',
               'compact-index': 'Indexed', 'compact-transfer': 'Transfer'}
CLASS_NAMES = {'RETURNED_JIT': 'returned JIT', 'WITNESSED_JIT': 'entry witnessed',
               'NO_JIT': 'NO_JIT',
               'PARTIAL_JIT': 'PARTIAL_JIT', 'MIXED': 'mixed · no point',
               'UNSCORED': 'unscored · no point'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def point(group, label, collection):
    """Validate a group; missing or mixed results never become zero-valued dots."""
    if group is None:
        return dict(value=None, valid=0, planned=3, status='MISSING',
                    category='UNSCORED', source_commit=None)
    valid, planned = group.get('valid'), group.get('planned')
    status, category = group.get('status'), group.get('jit_class')
    require(type(valid) is int and type(planned) is int and 0 <= valid <= planned == 3,
            f'{label}: invalid repeat counts')
    require(status in STATUSES and category in CLASSES, f'{label}: unknown group state')
    require((status == 'MIXED_EXECUTION_CLASSES') == (category == 'MIXED'),
            f'{label}: inconsistent mixed-class state')
    require((category == 'UNSCORED') == (valid == 0),
            f'{label}: inconsistent unscored state')
    require(status != 'COMPLETE' or valid == 3, f'{label}: incomplete repeats labelled complete')
    require(group.get('collection') == collection, f'{label}: collection/profile differs')
    identity = group.get('identity')
    require(isinstance(identity, dict), f'{label}: missing measurement identity')
    require(not any(identity.get(key) for key in ('diagnostic', 'perf_record', 'pmu')),
            f'{label}: profiled data cannot enter the plain plot')
    repeats = group.get('repeats')
    require(isinstance(repeats, list) and len(repeats) == valid
            and all(type(repeat) is int and repeat in (0, 1, 2) for repeat in repeats)
            and len(set(repeats)) == valid, f'{label}: invalid repeat identities')
    source = group.get('source_commit')
    require(isinstance(source, str) and source, f'{label}: missing source version')
    values = group.get('whole_mops')
    require(isinstance(values, dict), f'{label}: missing throughput object')
    median, low, high = (values.get(key) for key in ('median', 'min', 'max'))
    result = dict(value=None, valid=valid, planned=planned, status=status,
                  category=category, source_commit=source)
    if not valid or category == 'MIXED':
        require(values.get('n') == 0 and median is None and low is None and high is None,
                f'{label}: unscored/mixed groups must not contain pooled rates')
        return result
    require(values.get('n') == valid, f'{label}: throughput sample count differs')
    require(all(type(value) in (int, float) and math.isfinite(value)
                for value in (low, median, high)) and 0 < low <= median <= high,
            f'{label}: invalid throughput range')
    result['value'] = (median, median - low, high - median)
    return result


def draw_series(axis, points, color, marker, offset):
    previous = None
    for position, item in enumerate(points):
        if item['value'] is None:
            previous = None
            continue
        x = position + offset
        median, lower, upper = item['value']
        category = item['category']
        if previous is not None and previous[2] == category:
            axis.plot([previous[0], x], [previous[1], median], color=color,
                      linewidth=1.4, zorder=2)
        face = 'white' if category == 'NO_JIT' else color
        symbol = 'x' if category == 'PARTIAL_JIT' else marker
        axis.errorbar([x], [median], yerr=[[lower], [upper]], color=color,
                      marker=symbol, markerfacecolor=face, markeredgecolor=color,
                      fillstyle='left' if category == 'WITNESSED_JIT' else 'full',
                      markerfacecoloralt='white',
                      markeredgewidth=1.4, markersize=6.4, linestyle='none',
                      elinewidth=1.15, capsize=3.8, capthick=1.15, zorder=3)
        if item['valid'] != item['planned']:
            axis.annotate(f"n={item['valid']}/{item['planned']}", (x, median),
                          xytext=(0, 10), textcoords='offset points', ha='center',
                          va='bottom', color=color, fontsize=8,
                          bbox=dict(facecolor='white', edgecolor='none', pad=0.8))
        previous = (x, median, category)


def execution_note(values, workload, workers):
    labels = []
    for arm, _, _, _ in ARMS:
        states = [values[workload, arm, count] for count in workers]
        descriptions = [CLASS_NAMES[item['category']] if item['status'] != 'MISSING'
                        else 'missing · no point' for item in states]
        if len(set(descriptions)) == 1:
            detail = descriptions[0]
        else:
            detail = ', '.join(f'{count}w {description}' for count, description
                               in zip(workers, descriptions))
        labels.append(f'{SHORT_NAMES[arm]}: {detail}')
    note = textwrap.fill(' · '.join(labels), width=79)
    different_classes = any(len({values[workload, arm, count]['category']
                                 for arm, _, _, _ in ARMS
                                 if values[workload, arm, count]['value'] is not None}) > 1
                            for count in workers)
    if different_classes:
        note += '\nExecution classes differ across versions; timing is not like-for-like.'
    return note


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path(
        '/root/kdlock-evidence/10.176.26.71/bench/mutex32-index-20261019/comparison.json'))
    args = parser.parse_args()
    require(os.uname().release == '6.1.159-kdclobber2',
            'run plotting only in the recovery VM')
    raw = args.input.read_bytes()
    report = json.loads(raw)
    digest = hashlib.sha256(raw).hexdigest()
    require(report.get('schema') == 1 and isinstance(report.get('comparison'), list),
            'expected mutex32-index comparison schema 1')
    require(report.get('arms') == [arm for arm, _, _, _ in ARMS],
            'source-version order differs')
    allowed = {(workload, threads) for workload, _, _, workers, _ in CASES
               for threads in workers}
    rows = {}
    for row in report['comparison']:
        key = (row['workload'], row['arm'], row['threads'])
        require(key not in rows, f'duplicate comparison group: {key}')
        require((key[0], key[2]) in allowed and key[1] in SHORT_NAMES,
                f'unexpected comparison group: {key}')
        rows[key] = row
    values = {}
    for workload, _, collection, workers, _ in CASES:
        for arm, _, _, _ in ARMS:
            for threads in workers:
                key = (workload, arm, threads)
                values[key] = point(rows.get(key), '/'.join(map(str, key)), collection)
    for arm, _, _, _ in ARMS:
        sources = {item['source_commit'] for key, item in values.items()
                   if key[1] == arm and item['source_commit'] is not None}
        require(len(sources) <= 1, f'{arm}: multiple source versions in one series')
    profiles = report.get('profiles')
    require(isinstance(profiles, list) and all(row.get('collection') == 'profile'
            and row.get('score_eligible') is False for row in profiles),
            'profile sessions must remain unscored')
    eligible = sum(item['valid'] for item in values.values())
    require(report.get('scored_plain_sessions') == eligible,
            'eligible plain-session count differs from comparison groups')
    complete = all(item['value'] is not None and item['valid'] == 3
                   for item in values.values())
    provenance = (
        f'Input comparison.json SHA256: {digest}. {eligible}/{24 * len(ARMS)} eligible plain sessions; '
        'three planned repeats per version/workload/worker group. Median whole-interval '
        'Mops/s with observed min-max ranges, not confidence intervals. Source versions '
        'ran sequentially, not randomized. Profile sessions are excluded. Mixed execution '
        'classes have no pooled point; lines stop at execution-class changes or missing data.')
    plt.rcParams.update({
        'font.family': 'DejaVu Sans', 'font.size': 10,
        'axes.titlesize': 12, 'axes.labelsize': 10,
        'xtick.labelsize': 9, 'ytick.labelsize': 9,
        'svg.fonttype': 'none', 'svg.hashsalt': 'mutex32-index',
        'savefig.facecolor': 'white', 'figure.facecolor': 'white',
    })
    figure, axes = plt.subplots(2, 2, figsize=(12.4, 9.4))
    figure.subplots_adjust(left=0.075, right=0.98, bottom=0.245, top=0.76,
                           hspace=0.85, wspace=0.24)
    figure.suptitle('KD mutex · storage and registry comparison', fontsize=17, y=0.97)
    figure.text(0.5, 0.925,
                f'Median whole-interval throughput · {eligible}/{24 * len(ARMS)} eligible plain sessions · '
                '3 repeats per group', ha='center', va='center', fontsize=10,
                color='#3e4650')
    handles = [Line2D([0], [0], color=color, marker=marker, linewidth=1.4,
                      markersize=6.4, label=label) for _, label, color, marker in ARMS]
    figure.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, 0.90),
                  ncol=2, frameon=False, handlelength=2.5, columnspacing=2.4)
    for axis, (workload, title, _, workers, setup) in zip(axes.flat, CASES):
        maximum = 0.0
        for index, (arm, _, color, marker) in enumerate(ARMS):
            points = [values[workload, arm, count] for count in workers]
            draw_series(axis, points, color, marker, (index - (len(ARMS) - 1) / 2) * 0.09)
            for item in points:
                if item['value'] is not None:
                    median, _, upper = item['value']
                    maximum = max(maximum, median + upper)
        axis.set_title(title, loc='left', pad=28)
        axis.text(0, 1.07, setup, transform=axis.transAxes, ha='left', va='bottom',
                  fontsize=9, color='#555b63')
        axis.set_xlabel('Workers', labelpad=7)
        axis.set_ylabel('Throughput (million operations/s)', labelpad=8)
        axis.set_xticks(range(len(workers)), [str(count) for count in workers])
        axis.set_xlim(-0.38, len(workers) - 0.62 if len(workers) > 1 else 0.38)
        axis.set_ylim(0, maximum * 1.22 if maximum else 1)
        axis.yaxis.set_major_locator(MaxNLocator(nbins=5))
        axis.tick_params(axis='both', length=3, color='#89919a')
        axis.grid(axis='y', color='#d9dee4', linewidth=0.7, zorder=0)
        for side in ('top', 'right'):
            axis.spines[side].set_visible(False)
        for side in ('left', 'bottom'):
            axis.spines[side].set_color('#a8afb7')
        if not maximum:
            axis.set_yticks([])
            axis.text(0.5, 0.5, 'No eligible aggregate measurements',
                      transform=axis.transAxes, ha='center', va='center', color='#555b63')
        axis.text(0, -0.30, execution_note(values, workload, workers),
                  transform=axis.transAxes, ha='left', va='top', fontsize=8,
                  color='#555b63', linespacing=1.4)
    notes = (
        'Error bars: observed min-max across eligible repeats, not confidence intervals.',
        'Filled: returned JIT. Half-filled: entry witnessed, completion unmeasured. '
        'Hollow: NO_JIT (local). ×: PARTIAL_JIT.',
        'Versions ran sequentially, not randomized; time/order and frequency drift can affect comparisons.',
        f'Profiles excluded ({len(profiles)} sessions). Mixed execution classes have no pooled point; '
        'lines stop at class changes or missing data.',
    )
    for y, note in zip((0.115, 0.087, 0.059, 0.031), notes):
        figure.text(0.075, y, note, ha='left', va='center', fontsize=8.8, color='#555b63')
    output = args.input.resolve().parent
    figure.savefig(output / 'comparison.svg', metadata={
        'Title': 'KD mutex storage and registry comparison', 'Description': provenance,
        'Creator': 'mutex32-index-20261019/plot.py'})
    figure.savefig(output / 'comparison.png', dpi=220, metadata={
        'Title': 'KD mutex storage and registry comparison', 'Description': provenance,
        'Software': 'mutex32-index-20261019/plot.py'})
    plt.close(figure)
    receipt = dict(input=str(args.input.resolve()), comparison_sha256=digest,
                   all_plotted_groups_complete=complete, eligible_plain_sessions=eligible,
                   planned_plain_sessions=24 * len(ARMS), excluded_profile_sessions=len(profiles),
                   mixed_groups=sum(item['category'] == 'MIXED' for item in values.values()),
                   absent_points=sum(item['value'] is None for item in values.values()),
                   outputs=[str(output / name) for name in ('comparison.svg', 'comparison.png')])
    (output / 'plot-input.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    print(json.dumps(receipt, sort_keys=True))


if __name__ == '__main__':
    main()
