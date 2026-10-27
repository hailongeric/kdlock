#!/usr/bin/env python3
"""Plot retained single-round receipts without promoting them to repeated evidence."""
import argparse
import csv
import json
from pathlib import Path


def receipt_rows(source, host_qualified):
    """Select publishable receipt values independently of plotting packages."""
    plan = json.loads((source / 'plan.json').read_text())
    records_path = source / 'records.json'
    records = json.loads(records_path.read_text()) if records_path.exists() else []
    by_name = {row['name']: row for row in records}
    rows = []
    for spec in plan:
        row = by_name.get(spec['name'], {})
        m = row.get('measurement') or {}
        data_ok = (m.get('ok') is True if 'kind' in spec else
                   m.get('complete') is True and m.get('data_ok') is True)
        evidence = row.get('execution_class', row.get('jit_status',
                                                    row.get('jit_acceptance', 'UNMEASURED')))
        if spec['arm'] == 'kdlock' and row.get('jit_completions') is not None:
            evidence = ('RETURNED_JIT' if row['jit_completions'] else
                        'PARTIAL_JIT' if row.get('jit_bodies') else 'NO_JIT')
        if row.get('execution_status', 'NOT_RUN') != 'OK':
            evidence = row.get('execution_status', 'NOT_RUN')
        # Preserve the runner's eligibility decision. An entered JIT body
        # without a recorded return cannot qualify a throughput comparison.
        eligible = (row.get('score_eligible') is not False and
                    (spec['arm'] != 'kdlock' or evidence not in ('PARTIAL_JIT', 'UNMEASURED')))
        valid = (row.get('execution_status') == 'OK' and row.get('drained') is True
                 and data_ok and eligible)
        rate = m['completed'] * 1e3 / m['wall_ns'] if valid else None
        peak = (m.get('peak') or {}).get('throughput_ops_s') if valid else None
        rows.append(dict(workers=spec['threads'], backend=spec['arm'],
                         whole_mops_s=rate, peak_mops_s=peak / 1e6 if peak else None,
                         status=row.get('execution_status', 'NOT_RUN'),
                         drained=row.get('drained', False),
                         jit_status=evidence,
                         jit_entries=row.get('jit_bodies'),
                         jit_completions=row.get('jit_completions'),
                         host_qualified=host_qualified, session=spec['name']))
    return rows


def render(source, output, title, host_qualified, exploratory=False):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    rows = receipt_rows(source, host_qualified)
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'table.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    label = ('Host endpoints passed' if host_qualified else
             'UNQUALIFIED: host endpoint checks did not pass')
    if exploratory:
        label = 'EXPLORATORY: strict timing qualification remains failed'
    text = [f'# {title}', '', 'One timed repetition per point; no repeat variability estimate.',
            f'{label}. Rates include post-lock work. Failed, unrun or score-ineligible cases have no plotted rate.', '',
            '| Workers | Native Mops/s | TCLock Mops/s | KD Mops/s | KD execution |',
            '| ---: | ---: | ---: | ---: | --- |']
    lookup = {(r['workers'], r['backend']): r for r in rows}
    for workers in sorted({r['workers'] for r in rows}):
        rates = []
        for backend in ('native', 'tclock', 'kdlock'):
            value = lookup.get((workers, backend), {}).get('whole_mops_s')
            rates.append(f'{value:.3f}' if value is not None else '—')
        kd = lookup.get((workers, 'kdlock'), {})
        text.append(f'| {workers} | ' + ' | '.join(rates) +
                    f" | {kd.get('jit_status', 'NOT_RUN')} |")
    text += ['', '[Full receipt table](table.csv)', '', '![Throughput](throughput.png)', '']
    (output / 'README.md').write_text('\n'.join(text))
    fig, ax = plt.subplots(figsize=(9, 5))
    for backend, name, color in [('native', 'Native', '#64748b'),
                                  ('tclock', 'TCLock', '#db8b20'),
                                  ('kdlock', 'KD', '#147d92')]:
        selected = [r for r in rows if r['backend'] == backend]
        if selected:
            ax.plot([r['workers'] for r in selected],
                    [r['whole_mops_s'] if r['whole_mops_s'] is not None else float('nan') for r in selected],
                    marker='o', markersize=4, label=name, color=color)
    ax.set(xlabel='Workers', ylabel='Whole-run throughput (Mops/s)', ylim=(0, None),
           title=title + '\nOne repetition per point')
    ax.grid(alpha=.2)
    if ax.lines:
        ax.legend()
    fig.text(.5, .01, label + ' · No error bars: n=1', ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, 1))
    fig.savefig(output / 'throughput.png', dpi=160)
    fig.savefig(output / 'throughput.svg')
    svg = output / 'throughput.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
    plt.close(fig)
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--title', required=True)
    parser.add_argument('--host-qualified', action='store_true')
    args = parser.parse_args()
    render(args.source, args.output, args.title, args.host_qualified)
