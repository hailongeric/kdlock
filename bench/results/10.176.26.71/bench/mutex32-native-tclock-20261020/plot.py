#!/usr/bin/env python3
"""Render the seven mutex comparisons; execute only in the VM plotting venv.

Complete same-class triplets receive median/min-max marks. Split one/two-sample
groups show their individual observed rates without a connecting line. No line
bridges an absent worker point or a different KD execution class.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path


WORKERS = (1, 2, 4, 8, 16, 32, 36, 48, 60)
WORKLOADS = (
    ('c01', 'c01 / post64', 'KD: generated-body entry witness'),
    ('c08', 'c08 / post64', 'KD: generated-body entry witness'),
    ('rcuht', 'RCUHT / exclusive updates', 'KD: generated-body entry witness'),
    ('seek-set', 'SEEK_SET / n16', 'KD: matching returned-body probe'),
    ('seek-end', 'SEEK_END / n16', 'KD: matching returned-body probe'),
    ('pipebytes', 'Pipe bytes / n16', 'KD: matching returned-body probe'),
    ('pipecap', 'Pipe capacity / n16', 'KD: matching returned-body probe'),
)
BACKENDS = ('native', 'tclock', 'kdlock')
COLORS = {'native': '#2864a0', 'tclock': '#c67512', 'kdlock': '#008574'}
LABELS = {'native': 'Linux Native', 'tclock': 'TCLock', 'kdlock': 'KD'}
CLASSES = ('NOT_APPLICABLE', 'WITNESSED_JIT', 'RETURNED_JIT', 'NO_JIT', 'PARTIAL_JIT')
MARKERS = {'WITNESSED_JIT': '^', 'RETURNED_JIT': 'D', 'NO_JIT': 'o', 'PARTIAL_JIT': 'P'}
STYLES = {'WITNESSED_JIT': '--', 'RETURNED_JIT': '-', 'NO_JIT': ':', 'PARTIAL_JIT': '-.'}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def marker(backend, execution):
    return {'native': 'o', 'tclock': 's'}.get(backend, MARKERS.get(execution, 'x'))


def rows_for(document):
    rows = document.get('groups')
    if not isinstance(rows, list) or not rows:
        raise ValueError('comparison groups are required')
    seen = set()
    collections = {name for name, _, _ in WORKLOADS}
    for row in rows:
        name = row.get('collection', row.get('workload'))
        backend, threads, execution = (row.get(k) for k in ('backend', 'threads', 'jit_class'))
        if name not in collections or backend not in BACKENDS or threads not in WORKERS or execution not in CLASSES:
            raise ValueError('unexpected comparison identity: ' + repr((name, backend, threads, execution)))
        identity = (name, backend, threads, execution)
        if identity in seen:
            raise ValueError('duplicate source/class group: ' + repr(identity))
        seen.add(identity)
        if (backend != 'kdlock') != (execution == 'NOT_APPLICABLE'):
            raise ValueError('execution class does not match backend: ' + repr(identity))
        if backend == 'kdlock' and execution in ('RETURNED_JIT', 'PARTIAL_JIT') and name in ('c01', 'c08', 'rcuht'):
            raise ValueError('synthetic entries cannot establish returned/partial execution')
        if backend == 'kdlock' and execution == 'WITNESSED_JIT' and name not in ('c01', 'c08', 'rcuht'):
            raise ValueError('API completion evidence cannot become entry-only')
        rates = row.get('whole_mops', {})
        count = rates.get('n')
        if count not in (0, 1, 2, 3) or row.get('planned') != 3 or row.get('valid') != count:
            raise ValueError('unexpected repetition count: ' + repr(identity))
        if row.get('status') == 'COMPLETE' and count != 3:
            raise ValueError('complete group needs three eligible repeats')
        if count:
            values = [rates.get(k) for k in ('min', 'median', 'max')]
            if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in values):
                raise ValueError('invalid throughput range: ' + repr(identity))
            if not values[0] <= values[1] <= values[2]:
                raise ValueError('unordered throughput range: ' + repr(identity))
        elif any(rates.get(k) is not None for k in ('min', 'median', 'max')):
            raise ValueError('ineligible group has throughput statistics')
        yield name, row


def complete_segments(rows):
    """Only adjacent worker points of one backend/class can share a line."""
    segment = []
    for row in sorted(rows, key=lambda r: r['threads']):
        if segment and WORKERS.index(row['threads']) != WORKERS.index(segment[-1]['threads']) + 1:
            yield segment
            segment = []
        segment.append(row)
    if segment:
        yield segment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.uname().release != '6.1.159-kdclobber2':
        raise RuntimeError('render only in the recovery VM plotting environment')
    document = json.loads(args.comparison.read_text())
    if document.get('complete') is not True or document.get('issues'):
        raise ValueError('require a complete, validated comparison before rendering')
    rows = list(rows_for(document))
    if {name for name, _ in rows} != {name for name, _, _ in WORKLOADS}:
        raise ValueError('all seven workload panels are required')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    paths = [output / ('mutex-comparison.' + extension) for extension in ('svg', 'png', 'json')]
    if any(path.exists() for path in paths):
        raise ValueError('refusing to overwrite an existing figure or receipt')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    matplotlib.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
        'axes.titlesize': 12, 'axes.labelsize': 10, 'svg.fonttype': 'none',
        'savefig.facecolor': 'white', 'axes.spines.top': False,
        'axes.spines.right': False})
    figure, panels = plt.subplots(4, 2, figsize=(14, 16), layout='constrained')
    figure.suptitle('Mutex workloads: Linux Native, TCLock and KD\n'
                    'Whole-run throughput; separate execution classes', fontsize=17)
    drawn, incomplete, omitted = 0, [], []
    for panel, (name, title, evidence) in zip(panels.flat, WORKLOADS):
        selected = [row for collection, row in rows if collection == name]
        panel.set_title(title + '\n' + evidence, loc='left')
        panel.set_xlabel('Workers')
        panel.set_ylabel('Mops/s')
        panel.set_xlim(-1, 62)
        panel.set_xticks([1, 8, 16, 32, 36, 48, 60])
        panel.grid(axis='y', color='#dddddd', linewidth=0.6)
        for backend in BACKENDS:
            for execution in CLASSES:
                same = [r for r in selected if r['backend'] == backend and r['jit_class'] == execution]
                complete = [r for r in same if r['status'] == 'COMPLETE']
                color, shape = COLORS[backend], marker(backend, execution)
                style = STYLES.get(execution, '-')
                face = 'white' if execution == 'NO_JIT' else color
                for chain in complete_segments(complete):
                    x = [r['threads'] for r in chain]
                    y = [r['whole_mops']['median'] for r in chain]
                    panel.errorbar(x, y, yerr=[
                        [r['whole_mops']['median'] - r['whole_mops']['min'] for r in chain],
                        [r['whole_mops']['max'] - r['whole_mops']['median'] for r in chain]],
                        color=color, linestyle=style, linewidth=1.5, marker=shape,
                        markersize=5.8, markerfacecolor=face, markeredgewidth=1.2,
                        capsize=3, elinewidth=0.9, zorder=3)
                    drawn += len(chain)
                for row in same:
                    if row['status'] == 'COMPLETE':
                        continue
                    rates, count = row['whole_mops'], row['whole_mops']['n']
                    record = dict(collection=name, backend=backend, threads=row['threads'],
                                  jit_class=execution, status=row['status'], eligible_repeats=count)
                    if count in (1, 2):
                        # For n=1 or n=2 the extrema are the individual samples,
                        # so no incomplete-class median/range is presented.
                        observations = [rates['min']] if count == 1 else [rates['min'], rates['max']]
                        panel.scatter([row['threads']] * count, observations, marker=shape,
                                      s=25, facecolors='none', edgecolors=color,
                                      linewidths=1, alpha=0.6, zorder=4)
                        incomplete.append(record)
                    else:
                        # Rejected NO_JIT and any ambiguous three-sample group
                        # have no accepted plotted rate. Keep them in the receipt.
                        omitted.append(record)
        panel.set_ylim(bottom=0)
        panel_omitted = [r for r in omitted if r['collection'] == name]
        if panel_omitted:
            counts = ', '.join(str(t) for t in sorted({r['threads'] for r in panel_omitted}))
            panel.text(0.02, 0.98, 'Unscored/incomplete points: ' + counts + ' workers',
                       transform=panel.transAxes, va='top', fontsize=8, color='#555555')

    legend = panels.flat[-1]
    legend.axis('off')
    handles = [Line2D([0], [0], color=COLORS[b], marker=marker(b, 'RETURNED_JIT'),
                      linewidth=1.5, label=LABELS[b]) for b in BACKENDS]
    handles.extend(Line2D([0], [0], color=COLORS['kdlock'], marker=MARKERS[c],
                          linestyle=STYLES[c], markerfacecolor='white' if c == 'NO_JIT' else COLORS['kdlock'],
                          label=label) for c, label in (
        ('WITNESSED_JIT', 'KD generated-body entry witnessed'),
        ('RETURNED_JIT', 'KD matching returned body witnessed'),
        ('NO_JIT', 'KD local execution / no generated entry'),
        ('PARTIAL_JIT', 'KD entry without returned completion')))
    legend.legend(handles=handles, loc='upper left', frameon=False, fontsize=10)
    legend.text(0.02, 0.48,
        'Filled marks and bars: median and observed min–max\n'
        'of three eligible repeats in one execution class.\n'
        'NO_JIT triplets use open circles and a dotted line.\n\n'
        'Small faint open marks: individual eligible rates\n'
        'from a split one/two-repeat class; no pooled median.\n'
        'Lines stop at missing or different-class worker points.\n'
        'Rejected synthetic NO_JIT rates are not plotted.\n\n'
        'Three repeats are not confidence intervals.\n'
        'Workload blocks are sequential; backend order rotates.\n'
        'No full-grid parity or returned-body claim for synthetic KD.',
        transform=legend.transAxes, va='top', fontsize=10, linespacing=1.45)
    figure.savefig(paths[0], metadata={'Date': None})
    figure.savefig(paths[1], dpi=180)
    plt.close(figure)
    receipt = dict(schema=1, comparison_sha256=sha256(args.comparison),
                   script_sha256=sha256(Path(__file__)), matplotlib_version=matplotlib.__version__,
                   complete_groups_plotted=drawn, individual_sample_groups=incomplete,
                   unscored_or_ambiguous_groups_omitted=omitted,
                   outputs={path.name: sha256(path) for path in paths[:2]},
                   kernel_release=os.uname().release,
                   note='Complete class triplets only are connected; min/max bars are observed ranges, not confidence intervals.')
    paths[2].write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'complete_groups_plotted': drawn, 'split_sample_groups': len(incomplete),
                      'omitted_groups': len(omitted), 'outputs': [str(path) for path in paths]}, sort_keys=True))


if __name__ == '__main__':
    main()
