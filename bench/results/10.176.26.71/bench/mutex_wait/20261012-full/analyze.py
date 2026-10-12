#!/usr/bin/env python3
"""Derive comparison summaries from the separately audited complete matrix.

Run in the benchmark guest after export.py. This reads only exported evidence;
it never starts a measurement or fills a missing/rejected round.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics


def read(path):
    return json.loads(path.read_text())


def distribution(values):
    return dict(min=min(values), median=statistics.median(values), max=max(values)) if values else None


def summarize(points, arm):
    def ratio(p, baseline, metric):
        return p[f'{arm}_over_{baseline}_{metric}']
    whole, peak = 'whole_ops_s_median', 'peak_ops_s_max'
    # One rejected policy/control does not invalidate the other policy's
    # independently complete three-round comparison with Native and TCLock.
    good = [p for p in points if all(ratio(p, b, m) is not None
            for b in ('native', 'tclock') for m in (whole, peak, 'cpu_ns_per_op_median'))]
    wins = lambda p, metric: all(ratio(p, b, metric) >= 1 for b in ('native', 'tclock'))
    return dict(points=len(points), complete=len(good),
        beats_both_whole=sum(wins(p, whole) for p in good),
        beats_both_peak=sum(wins(p, peak) for p in good),
        beats_both_both_metrics=sum(wins(p, whole) and wins(p, peak) for p in good),
        ratios={baseline: {metric: distribution([ratio(p, baseline, metric) for p in good])
                          for metric in (whole, peak, 'cpu_ns_per_op_median')}
                for baseline in ('native', 'tclock')})


def plot_mutex_policy(root, points):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9, 'svg.fonttype': 'none'})
    subjects = sorted({r['subject'] for r in points if r['lock_kind'] == 'mutex'})
    assert len(subjects) == 9
    fig, axes = plt.subplots(3, 3, figsize=(15, 11), squeeze=False)
    for ax, name in zip(axes.flat, subjects):
        rows = sorted((r for r in points if r['subject'] == name), key=lambda r:r['threads'])
        for metric, label, color in (
                ('whole_ops_s_median', 'Median whole-run', '#2563eb'),
                ('peak_ops_s_max', 'Best warmed peak', '#b45309')):
            ax.plot([r['threads'] for r in rows],
                    [r['kd-blocking_over_kd-spin_'+metric] for r in rows],
                    'o-', label=label, color=color, markersize=3)
        ax.axhline(1, color='#555555', linewidth=1)
        ax.axhspan(.95, 1.05, color='#777777', alpha=.08)
        ax.axvline(32, color='#bbbbbb', linestyle=':', linewidth=1)
        ax.set(title=name, xlabel='Pinned workers', ylabel='Blocking / spin throughput',
               xticks=[1, 8, 16, 24, 32, 40, 48, 56, 64])
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
    fig.text(.5, .01, 'Three rounds per policy; band marks +/-5% of parity, not a confidence interval. '
             'Values above 1 favor blocking.\nWorkers >32 span both NUMA nodes; '
             'at 64 workers, collector and last worker share a physical core.',
             ha='center', va='bottom', fontsize=9)
    fig.tight_layout(rect=(0, .055, 1, 1))
    fig.savefig(root/'mutex-policy-ratio.png', dpi=150)
    svg = root/'mutex-policy-ratio.svg'
    fig.savefig(svg)
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--plots', action='store_true')
    args = p.parse_args()
    root = args.report.resolve()
    verification = read(root/'verification.json')
    assert verification['passed'] and verification['sessions'] == 8910
    assert verification['subjects'] == 31 and verification['comparisons'] == 682
    samples, stats, points = [read(root/(name+'.json')) for name in ('samples', 'statistics', 'comparison')]
    lookup = {(r['subject'], r['threads'], r['backend']): r for r in stats}
    categories = {
        'all-multithread': lambda r: r['threads'] > 1,
        'mutex-multithread': lambda r: r['lock_kind'] == 'mutex' and r['threads'] > 1,
        'mutex-at-least-four': lambda r: r['lock_kind'] == 'mutex' and r['threads'] >= 4,
        'mutex-16-through-60': lambda r: r['lock_kind'] == 'mutex' and 16 <= r['threads'] <= 60,
        'mutex-single-thread': lambda r: r['lock_kind'] == 'mutex' and r['threads'] == 1,
        'spin-multithread': lambda r: r['lock_kind'] == 'spin' and r['threads'] > 1,
        'rwlock-multithread': lambda r: r['lock_kind'] == 'rwlock' and r['threads'] > 1,
        'api-multithread': lambda r: r['suite'] == 'api' and r['threads'] > 1,
    }
    for n in (1, 4, 8, 16, 32, 36, 60, 64):
        categories[f'all-t{n:02d}'] = lambda r, n=n: r['threads'] == n
        categories[f'mutex-t{n:02d}'] = lambda r, n=n: r['threads'] == n and r['lock_kind'] == 'mutex'
    totals = {label: {arm: summarize([r for r in points if select(r)], arm)
                      for arm in ('kd-spin', 'kd-blocking')}
              for label, select in categories.items()}
    policy = {}
    for label, select in categories.items():
        selected = [r for r in points if select(r) and
                    r['kd-blocking_over_kd-spin_whole_ops_s_median'] is not None]
        policy[label] = {}
        for metric in ('whole_ops_s_median', 'peak_ops_s_max', 'cpu_ns_per_op_median'):
            values = [r['kd-blocking_over_kd-spin_'+metric] for r in selected]
            policy[label][metric] = dict(distribution=distribution(values),
                within_5_percent=sum(.95 <= v <= 1.05 for v in values),
                within_10_percent=sum(.9 <= v <= 1.1 for v in values), points=len(values))
    transitions = []
    for subject in sorted({r['subject'] for r in points}):
        for start, finish in ((32, 36), (60, 64)):
            for arm in ('stock', 'native', 'tclock', 'kd-spin', 'kd-blocking'):
                a, b = lookup.get((subject, start, arm)), lookup.get((subject, finish, arm))
                if a and b:
                    transitions.append(dict(subject=subject, start=start, finish=finish, backend=arm,
                        whole_ratio=b['whole_ops_s_median']/a['whole_ops_s_median'] if a['complete'] and b['complete'] else None,
                        peak_ratio=b['peak_ops_s_max']/a['peak_ops_s_max'] if a['complete'] and b['complete'] else None))
    diagnostics = []
    for key, stat in sorted(lookup.items()):
        subject, n, arm = key
        if not arm.startswith('kd-'):
            continue
        rows = [r for r in samples if (r['subject'], r['threads'], r['backend']) == key and r['accepted']]
        completed = sum(r['completed'] for r in rows)
        eligible = sum(r['jit_eligible_ops'] for r in rows)
        diagnostics.append(dict(subject=subject, threads=n, backend=arm,
            complete=stat['complete'], execution_types=stat['execution_types'],
            jit_share=sum(r['jit_bodies'] for r in rows)/eligible if eligible else None,
            schedule_calls_per_million_ops=(sum(r['result_schedule_calls'] for r in rows)*1e6/completed
                if rows and all('result_schedule_calls' in r for r in rows) else None),
            gate_wait_calls_per_million_ops=(sum(r['gate_wait_calls'] for r in rows)*1e6/completed
                if rows and all('gate_wait_calls' in r for r in rows) else None),
            whole_spread_pct=stat['whole_ops_s_spread_pct'], peak_spread_pct=stat['peak_ops_s_spread_pct'],
            min_worker_share=min((r['min_worker_share'] for r in rows), default=None)))
    result = dict(totals=totals, policy=policy, transitions=transitions, diagnostics=diagnostics,
        exclusions=[{k:r[k] for k in ('group', 'name', 'subject', 'threads', 'backend',
            'repeat', 'execution_status', 'jit_bodies', 'drained', 'whole_ops_s', 'peak_ops_s')}
            for r in samples if not r['accepted']],
        single_worker_hash_samples=[dict(subject=r['subject'], backend=r['backend'], repeat=r['repeat'],
            whole_ops_s=r['whole_ops_s'], peak_ops_s=r['peak_ops_s'],
            move_share=r['hash_move_ops']/r['jit_eligible_ops'],
            destination_conflict_share=r['hash_destination_conflict_ops']/r['jit_eligible_ops'],
            source_miss_share=r['hash_source_miss_ops']/r['jit_eligible_ops'])
            for r in samples if r['threads'] == 1 and 'hash_move_ops' in r],
        mixed_execution_cohorts=sum(len(r['execution_types']) > 1 for r in stats if r['backend'].startswith('kd-')),
        execution_types=dict(Counter(r['execution_type'] for r in samples)),
        input_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest()
                      for name in ('samples.json', 'statistics.json', 'comparison.json', 'verification.json')})
    (root/'analysis.json').write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
    if Path(__file__).resolve() != root/'analyze.py':
        (root/'analyze.py').write_bytes(Path(__file__).read_bytes())
    text = ['# Derived comparison summaries', '',
        'Every count is an equally weighted workload/count point, not an independent application. '
        'A win against both backends requires KD >= Native and KD >= TCLock. Strict wins require '
        'both median whole-run throughput and best warmed peak. Incomplete/rejected cohorts are '
        'excluded from the affected arm\'s wins and ratios, and remain in the complete tables. '
        'A complete comparison for the other KD arm remains scored.', '',
        '| Cohort | KD policy | Complete/total | Whole wins | Peak wins | Strict wins |',
        '| --- | --- | ---: | ---: | ---: | ---: |']
    for label, arms in totals.items():
        for arm, r in arms.items():
            text.append(f"| {label} | {arm} | {r['complete']}/{r['points']} | {r['beats_both_whole']} | {r['beats_both_peak']} | {r['beats_both_both_metrics']} |")
    for n in (60, 64):
        text += ['', f'## All subjects at {n} workers', '',
            'Median whole-run Mops/s. At 64 workers, the last worker and collector share a physical core.', '',
            '| Subject | Stock | Native | TCLock | KD spin | KD blocking |',
            '| --- | ---: | ---: | ---: | ---: | ---: |']
        for name in sorted({r['subject'] for r in points}):
            rates=[]
            for arm in ('stock','native','tclock','kd-spin','kd-blocking'):
                r=lookup.get((name,n,arm))
                rates.append(f"{r['whole_ops_s_median']/1e6:.3f}" if r and r['complete'] else '—')
            text.append('| '+ ' | '.join([name,*rates])+' |')
    text += ['', '## Largest mutex blocking losses against spin', '',
        'Multithreaded cases sorted by median whole-run blocking/spin ratio; all original samples remain scored.', '',
        '| Subject | Workers | Blocking/spin whole | Blocking/spin peak |',
        '| --- | ---: | ---: | ---: |']
    for r in sorted((r for r in points if r['lock_kind']=='mutex' and r['threads']>1 and r['complete']),
                    key=lambda r:r['kd-blocking_over_kd-spin_whole_ops_s_median'])[:20]:
        text.append(f"| {r['subject']} | {r['threads']} | {r['kd-blocking_over_kd-spin_whole_ops_s_median']:.3f}× | {r['kd-blocking_over_kd-spin_peak_ops_s_max']:.3f}× |")
    text += ['', '## Retained exclusions', '',
        'These sessions remain in the raw evidence and samples. Their measured rates are '
        'unscored; an affected three-round cohort is incomplete. Repeat numbers are zero-based.', '',
        '| Subject | Workers | Backend | Repeat | Status | JIT bodies | Drained |',
        '| --- | ---: | --- | ---: | --- | ---: | --- |']
    for r in result['exclusions']:
        text.append(f"| {r['subject']} | {r['threads']} | {r['backend']} | {r['repeat']} | "
                    f"{r['execution_status']} | {r['jit_bodies']} | {r['drained']} |")
    (root/'HIGHLIGHTS.md').write_text('\n'.join(text)+'\n')
    if args.plots:
        plot_mutex_policy(root, points)
    print(json.dumps(dict(mixed_execution_cohorts=result['mixed_execution_cohorts'],
        execution_types=result['execution_types'], mutex=totals['mutex-multithread'],
        mutex_policy=policy['mutex-multithread']),indent=2))


if __name__ == '__main__':
    main()
