#!/usr/bin/env python3
"""Plot selected audited archive groups; never run a workload.

Repeat --series GROUP:ARM:LABEL to choose up to six distinct curves explicitly.
Default series show the fresh Native finite baseline, initial owned finite/refill
baselines and the explicitly named final finite/refill grids.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

HERE = Path(__file__).resolve().parent
COUNTS = (1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 28, 32, 36, 48, 60)
DEFAULT_SERIES = (
    'finite:native:Native · fresh finite baseline',
    'finite:kdlock:Owned · initial finite baseline',
    'refill:kdlock:Owned · initial refill baseline',
    'final_finite:kdlock:Owned · final finite screen',
    'final_refill:kdlock:Owned · final refill screen',
)
COLORS = ('#303030', '#D55E00', '#0072B2', '#009E73', '#CC79A7', '#E69F00')
MARKERS = ('o', 's', '^', 'D', 'v', 'P')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_series(path, declarations, coverage):
    with path.open(newline='') as source:
        rows = list(csv.DictReader(source))
    series, identities = [], set()
    if not 1 <= len(declarations) <= len(COLORS):
        raise ValueError('select between one and six series')
    for declaration in declarations:
        group, arm, label = declaration.split(':', 2)
        if (group, arm) in identities:
            raise ValueError('duplicate plotted group/arm')
        identities.add((group, arm))
        selected = sorted((row for row in rows if row['group'] == group and row['arm'] == arm),
                          key=lambda row: int(row['threads']))
        if not selected or arm not in ('native', 'kdlock'):
            raise ValueError('missing Native/owned series: ' + declaration)
        counts = [int(row['threads']) for row in selected]
        if len(set(counts)) != len(counts) or not set(counts) <= set(COUNTS):
            raise ValueError('duplicate/unexpected worker counts')
        if any(row['diagnostic'] != 'False' or row['score_eligible'] != 'True' or
               int(row['sessions']) != 3 for row in selected):
            raise ValueError('plots accept only audited three-round scored groups')
        if arm == 'kdlock' and any(row['implementation'] != 'owned-v1' for row in selected):
            raise ValueError('legacy KD is outside this report')
        receipt = coverage['runs'][group]
        if not receipt['source_and_raw_verified'] or receipt['diagnostic']:
            raise ValueError('group is not audited uninstrumented evidence')
        series.append(dict(group=group, arm=arm, label=label, rows=selected,
                           worker_counts=counts, role=receipt['role'],
                           source_manifest_sha256=receipt['source_manifest_sha256']))
    return series


def values(series, field):
    result = [float(row[field]) for row in series['rows']]
    if any(not math.isfinite(value) or value < 0 for value in result):
        raise ValueError('non-finite/negative plotted quantity: ' + field)
    return result


def setup_axes(axes):
    for axis in axes:
        axis.set_xticks(range(len(COUNTS)), COUNTS)
        axis.set_xlim(-0.6, len(COUNTS)-0.4)
        axis.set_xlabel('Workers (measured counts only)')
        axis.grid(axis='y', color='#dedede', linewidth=0.6)
        axis.set_axisbelow(True)
        axis.spines[['top', 'right']].set_visible(False)


def points(axis, x, y, index, label, bounds=None):
    kwargs = dict(color=COLORS[index], marker=MARKERS[index], markersize=4.8,
                  linestyle='none', label=label, zorder=3)
    if bounds is None:
        axis.plot(x, y, **kwargs)
    else:
        low, high = bounds
        if any(a > b or b > c for a, b, c in zip(low, y, high)):
            raise ValueError('plotted value is outside observed range')
        axis.errorbar(x, y, yerr=([b-a for a, b in zip(low, y)],
                                 [c-b for b, c in zip(y, high)]),
                      elinewidth=0.9, capsize=2, **kwargs)


def finish(figure, axes, title, subtitle, footnote, path):
    figure.suptitle(title, x=0.055, y=0.99, ha='left', fontsize=15, fontweight='bold')
    figure.text(0.055, 0.925, subtitle, fontsize=10, color='#444444')
    handles, labels = axes[0].get_legend_handles_labels()
    figure.legend(handles, labels, loc='lower left', bbox_to_anchor=(0.047, 0.065),
                  frameon=False, ncols=2, fontsize=8.8)
    figure.text(0.055, 0.025, footnote, fontsize=8.5, color='#444444')
    figure.subplots_adjust(left=0.065, right=0.985, top=0.84, bottom=0.24, wspace=0.23)
    figure.savefig(path, metadata={'Date': None, 'Creator': 'KD owned-mutex archived-evidence plot.py'})
    # Matplotlib pads multiline SVG paths; normalize source-only whitespace.
    path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines()) + '\n')
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--statistics', type=Path, default=HERE/'statistics.csv')
    parser.add_argument('--out', type=Path, default=HERE)
    parser.add_argument('--series', action='append', metavar='GROUP:ARM:LABEL')
    args = parser.parse_args()
    coverage_path = args.statistics.parent/'coverage.json'
    acceptance_path = args.statistics.parent/'acceptance.json'
    coverage = json.loads(coverage_path.read_text())
    acceptance = json.loads(acceptance_path.read_text())
    if not coverage['passed'] or coverage['post_work_rounds'] != 64:
        raise ValueError('requires a passed post64 archive audit')
    series = load_series(args.statistics, args.series or DEFAULT_SERIES, coverage)
    if acceptance['target_reached']:
        status = 'See acceptance.json for the accepted policy and confirmation blocks.'
    else:
        status = 'Screening evidence; the full 97% Native target has not been reached.'
    matplotlib.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                                'svg.fonttype': 'none', 'svg.hashsalt': 'owned-hybrid-20261014'})
    args.out.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(1, 2, figsize=(14, 6.2))
    execution, execution_axes = plt.subplots(1, 2, figsize=(14, 6.2))
    setup_axes(axes)
    setup_axes(execution_axes)
    for index, item in enumerate(series):
        offset = (index-(len(series)-1)/2)*0.07
        x = [COUNTS.index(count)+offset for count in item['worker_counts']]
        points(axes[0], x, values(item, 'whole_median_mops'), index, item['label'],
               bounds=(values(item, 'whole_min_mops'), values(item, 'whole_max_mops')))
        points(axes[1], x, values(item, 'peak_best_mops'), index, item['label'],
               bounds=(values(item, 'peak_min_mops'), values(item, 'peak_best_mops')))
        points(execution_axes[0], x, values(item, 'jit_share_median'), index, item['label'])
        points(execution_axes[1], x, values(item, 'worker_cpu_ns_per_op_median'), index, item['label'])
    axes[0].set_title('Median whole-run throughput')
    axes[1].set_title('Best valid warmed peak (observed 300 ms window)')
    for axis in axes:
        axis.set_ylabel('Million operations / second')
        axis.set_ylim(bottom=0)
    execution_axes[0].set_title('Median returned-JIT fraction')
    execution_axes[0].set_ylabel('JIT bodies / measured operations')
    execution_axes[0].yaxis.set_major_formatter(PercentFormatter(1))
    execution_axes[0].set_ylim(-0.03, 1.03)
    execution_axes[1].set_title('Median aggregate worker CPU cost')
    execution_axes[1].set_ylabel('Worker CPU ns / operation (log scale)')
    execution_axes[1].set_yscale('log')
    finish(figure, axes, 'Owned mutex c01 · throughput · 64 post-work rounds', status,
           'Markers show measured groups only; no interpolation. Whiskers retain all three-run ranges. Native controls are group-specific.',
           args.out/'throughput.svg')
    finish(execution, execution_axes, 'Owned mutex c01 · execution and CPU cost', status,
           'JIT fractions are measurement-only; SELF remains distinct. Worker CPU cost excludes collector and other VM/host overhead.',
           args.out/'execution.svg')
    receipt = dict(schema=1, source='offline audited archive statistics',
        statistics_sha256=digest(args.statistics), coverage_sha256=digest(coverage_path),
        acceptance_sha256=digest(acceptance_path), plot_script_sha256=digest(Path(__file__)),
        series=[{key: value for key, value in item.items() if key != 'rows'} for item in series],
        missing_counts='No marker; no interpolation or extrapolation',
        native_controls='Each group retains its own Native controls in CSV; a plotted Native series applies only to its named group.',
        target_reached=acceptance['target_reached'],
        output_sha256={name: digest(args.out/name) for name in ('throughput.svg', 'execution.svg')})
    (args.out/'plot-inputs.json').write_text(json.dumps(receipt, indent=2, sort_keys=True)+'\n')
    print(json.dumps(dict(plotted_groups=[(item['group'], item['arm']) for item in series],
                          target_reached=acceptance['target_reached'], output=str(args.out))))


if __name__ == '__main__':
    main()
