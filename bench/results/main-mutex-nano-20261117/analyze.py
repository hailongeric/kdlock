#!/usr/bin/env python3
"""Summarize collected ordinary mutex receipts on the host."""
import argparse
from collections import Counter, defaultdict
from itertools import product
import json
import math
from pathlib import Path
from statistics import median
import sys


BACKENDS = ('native', 'kd', 'tclock')
KD_KEYS = ('delegated', 'handback', 'offered', 'sessions', 'plain', 'parked',
           'head_sleep', 'handoff', 'mode_enter', 'mode_exit', 'stop_plain',
           'numa_deferred', 'cl_offered', 'cl_done')
TC_KEYS = ('delegated', 'batches', 'parks')
TUNING = (2, 3, 5)
SPREAD_PCT = 5.0


def load_json(file):
    return json.loads(file.read_text())


def validate_point(row, identity):
    ops = row['worker_ops']
    writes = row['worker_writes']
    elapsed = row['elapsed_ns']
    workers = row['workers']
    kd = row['kd_delta']
    tc = row['tc_delta']
    functional = row['phase'].startswith('functional-')
    threshold = int(row['parameters']['kd_deleg_enter_sleep'])
    expected_policy = f'enter-{threshold}' if row['phase'].startswith('threshold') else 'default'
    checks = {
        'worker array lengths': len(ops) == len(writes) == workers,
        'all workers progress': all(n > 0 for n in ops),
        'worker write accounting': writes == ops and sum(writes) == row['writes'],
        'total accounting': sum(ops) == row['ops'] == row['writes'],
        'min/max worker ops': ops and min(ops) == row['min_worker_ops'] and max(ops) == row['max_worker_ops'],
        'protected data': row['sum_delta'] == row['writes'] * row['lines'] and row['torn_reads'] == 0,
        'rate': elapsed > 0 and math.isclose(row['mops'], row['ops'] * 1000 / elapsed, rel_tol=1e-12),
        'runner status': row['ok'] is True,
        'identity': all(row[k] == identity[k] for k in ('boot_id', 'kernel', 'source')),
        'workload': row['write_pct'] == 100 and row['post'] == identity['post']
                    and row['first_cpu'] == (4 if workers == 32 else 0),
        'family': row['family'] in (('mix', 'mutex_cl') if functional else ('mutex',)),
        'policy': row['policy'] == expected_policy,
        'parameters': row['parameters'] == {**identity['parameters'], 'kd_deleg_enter_sleep': str(threshold)},
        'delegation enabled': row['delegation'] == 1,
        'KD counters': set(KD_KEYS) <= kd.keys() and all(n >= 0 for n in kd.values()),
        'selected KD counters': all(k in kd and kd[k] == v for k, v in row['execution_counts'].items()),
        'TCLock counters': set(tc) == set(TC_KEYS) and all(n >= 0 for n in tc.values()),
        'TCLock activity': row['backend'] == 'tclock' or not any(tc.values()),
    }
    if row['phase'] in ('threshold', 'three-way', 'threshold-warmup', 'three-way-warmup'):
        checks['timing window'] = row['ms'] == (250 if row['phase'].endswith('-warmup') else 1000)
        checks['reference threshold'] = threshold == 3 or (row['phase'].startswith('threshold') and row['backend'] == 'kd')
    if row['phase'] == 'functional-control':
        checks['functional control'] = row['backend'] == 'native' and workers == 8 and row['round'] == 0 and row['ms'] == 400
    if row['phase'] == 'functional-kd':
        checks['functional pattern'] = (row['backend'] == 'kd' and 0 <= row['round'] < 4 and
                                        workers == (8 if row['round'] == 0 else 32) and row['ms'] == 750)
    if row['phase'] == 'learning':
        checks['learning configuration'] = row['backend'] == 'kd' and workers == 32 and row['ms'] == 600
    if functional or row['phase'] == 'learning':
        checks['functional and learning settings'] = row['lines'] == 1 and threshold == 3
    return [key for key, ok in checks.items() if not ok]


def expected_keys(identity):
    all_keys = []
    for phase in ('three-way', 'threshold'):
        workers = identity['standard_workers' if phase == 'three-way' else 'tuning_workers']
        configurations = [(name, 3) for name in BACKENDS]
        if phase == 'threshold':
            configurations += [('kd', 2), ('kd', 5)]
        for w, lines, (backend, threshold), rnd, suffix in product(workers, (1, 16), configurations, range(3), ('', '-warmup')):
            all_keys.append((phase + suffix, w, lines, backend, threshold, rnd))
    return Counter(all_keys)


def point_key(row):
    return (row['phase'], row['workers'], row['lines'], row['backend'],
            int(row['parameters']['kd_deleg_enter_sleep']), row['round'])


def summarize(rows):
    rates = {r['round']: r['mops'] for r in rows}
    values = list(rates.values())
    center = median(values)
    spread = 100 * (max(values) - min(values)) / center
    return dict(n=len(rows), median=center, low=min(values), high=max(values),
                spread_pct=spread, rates=rates, ops=sum(r['ops'] for r in rows),
                kd={key: sum(r['kd_delta'][key] for r in rows) for key in KD_KEYS},
                tc={key: sum(r['tc_delta'][key] for r in rows) for key in TC_KEYS})


def paired(a, b):
    rounds = sorted(a['rates'].keys() & b['rates'].keys())
    gains = [100 * (a['rates'][r] / b['rates'][r] - 1) for r in rounds]
    return dict(n=len(rounds), wins=sum(g > 0 for g in gains), ties=sum(g == 0 for g in gains),
                losses=sum(g < 0 for g in gains), paired_pct=gains,
                median_pct=100 * (a['median'] / b['median'] - 1))


def analyze(directory):
    identity = load_json(directory / 'identity.json')
    errors = []
    point_counts = Counter()
    actual = Counter()
    cells = defaultdict(list)
    functional = []
    other_kd_activity = Counter()
    functional_counts = defaultdict(Counter)
    for index, line in enumerate((directory / 'points.jsonl').read_text().splitlines(), start=1):
        try:
            row = json.loads(line)
            phase = row['phase']
            point_counts[phase] += 1
            issues = validate_point(row, identity)
            if issues:
                errors.append(f'Line {index}, {phase}: ' + ', '.join(issues))
                continue
            if row['backend'] != 'kd':
                other_kd_activity.update({key: value for key, value in row['kd_delta'].items() if value})
            key = point_key(row)
            if phase in ('three-way', 'threshold', 'three-way-warmup', 'threshold-warmup'):
                actual[key] += 1
                if phase in ('three-way', 'threshold'):
                    if actual[key] > 1:
                        errors.append(f'Duplicate measured round at line {index}: {key}')
                    else:
                        cells[key[:-1]].append(row)
            elif phase == 'learning' or phase.startswith('functional-'):
                functional.append({k: row[k] for k in ('phase', 'family', 'backend', 'workers', 'round', 'ops',
                                                       'kd_delta', 'tc_delta')})
                functional_counts[(phase, row['family'])].update([row['backend']])
            else:
                errors.append(f'Unknown phase at line {index}: {phase}')
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f'Line {index}: {exc!r}')
    expected = expected_keys(identity)
    for message, differences in [('Missing valid point', expected - actual), ('Unexpected point', actual - expected)]:
        for key, count in differences.items():
            errors.append(f'{message} {key} × {count}')
    if not 1 <= functional_counts[('learning', 'mutex')]['kd'] <= 8:
        errors.append('Expected one to eight learning attempts')
    for family in ('mix', 'mutex_cl'):
        if functional_counts[('functional-control', family)]['native'] != 1:
            errors.append(f'Missing or repeated Native control for {family}')
        if not 2 <= functional_counts[('functional-kd', family)]['kd'] <= 4:
            errors.append(f'Missing or unexpected KD functional checks for {family}')
    result = load_json(directory / 'result.json') if (directory / 'result.json').exists() else {}
    api = load_json(directory / 'api.json') if (directory / 'api.json').exists() else {}
    cleanup = load_json(directory / 'cleanup.json') if (directory / 'cleanup.json').exists() else {}
    measured = load_json(directory / 'measurements-complete.json') if (directory / 'measurements-complete.json').exists() else {}
    if result.get('status') != 'completed' or result.get('boot_id') != identity['boot_id']:
        errors.append(f'Campaign completion receipt: {result}')
    if api.get('failed_checks') != 0:
        errors.append(f'API receipt: {api}')
    if (cleanup.get('boot_id') != identity['boot_id'] or cleanup.get('cleanup_errors') != []
            or cleanup.get('final_params') != identity['parameters'] or cleanup.get('modules') != identity['initial_modules']
            or cleanup.get('taint') != identity['taint'] or cleanup.get('daemon_rc') != 0):
        errors.append('Missing or inconsistent cleanup receipt')
    if measured.get('standard_rows') != point_counts['three-way'] or measured.get('threshold_rows') != point_counts['threshold']:
        errors.append('Measured phase counts disagree with completion marker')
    summary = {key: summarize(rows) for key, rows in sorted(cells.items())}
    standards = []
    controls = []
    for phase, w, lines in sorted({key[:3] for key in summary}):
        baseline = summary.get((phase, w, lines, 'kd', 3))
        native = summary.get((phase, w, lines, 'native', 3))
        tc = summary.get((phase, w, lines, 'tclock', 3))
        if not all((baseline, native, tc)):
            continue
        if phase == 'three-way':
            standards.append(dict(workers=w, lines=lines, native=native, kd=baseline, tclock=tc,
                                  vs_native=paired(baseline, native), vs_tclock=paired(baseline, tc)))
        else:
            for setting in TUNING:
                current = summary.get((phase, w, lines, 'kd', setting))
                if current:
                    controls.append(dict(workers=w, lines=lines, threshold=setting, kd=current,
                                         native=native, tclock=tc, vs_default=paired(current, baseline),
                                         vs_native=paired(current, native), vs_tclock=paired(current, tc)))
    return dict(identity=identity, phase_counts=dict(point_counts), errors=errors,
                reference_kd_activity=dict(other_kd_activity), api=api, completion=result,
                standard=standards, threshold=controls, functional=functional)


def rate(stats):
    return f"{stats['median']:.4f} ({stats['low']:.4f}–{stats['high']:.4f})"


def comparison(stats):
    return f"{stats['median_pct']:+.2f}% ({stats['wins']}/{stats['n']})"


def counts(stats, group, fields):
    return ' / '.join(f"{stats[group][key]:,}" for key in fields)


def markdown(report):
    out = []
    def paragraph(line):
        out.extend([line, ''])

    def table(labels, entries):
        out.append('| ' + ' | '.join(labels) + ' |')
        out.append('| ' + ' | '.join('---' for _ in labels) + ' |')
        for row in entries:
            out.append('| ' + ' | '.join(map(str, row)) + ' |')
        out.append('')

    identity = report['identity']
    paragraph('# Ordinary mutex measurements')
    paragraph(f"Source `{identity['source']}`, kernel `{identity['kernel']}`, boot `{identity['boot_id']}`. "
              f"Post work is {identity['post']}. The 32-worker rows use CPUs 4–35. Other rows start on CPU 0.")
    paragraph(f"Campaign status **{report['completion'].get('status', 'missing')}**. "
              f"Raw record or coverage discrepancies **{len(report['errors'])}**. "
              f"API failed checks **{report['api'].get('failed_checks', 'unavailable')}**.")
    if report['errors']:
        paragraph('Coverage and validation details')
        for item in report['errors']:
            out.append('- ' + item)
        out.append('')
    table(['Phase', 'Raw points'], sorted(report['phase_counts'].items()))
    paragraph('## Standard three-way comparison')
    paragraph('Rates are medians in Mops/s with the minimum and maximum in parentheses. '
              'Comparisons use the ratio of medians. Wins count strict wins in matched rounds. '
              'The rate uses the guest stop timestamp and includes operations that finish during drain. '
              'All event totals cover the measured repetitions for their own cells.')
    table(['Workers', 'Lines', 'Native', 'KD', 'TCLock', 'KD vs Native (wins)', 'KD vs TCLock (wins)'],
          [(r['workers'], r['lines'], rate(r['native']), rate(r['kd']), rate(r['tclock']),
            comparison(r['vs_native']), comparison(r['vs_tclock'])) for r in report['standard']])
    paragraph('KD columns count approximate kernel events. TCLock accumulates executed waiters when each batch returns. '
              'Its parks counter advances after a waiter changes its state to parked, just before scheduling. '
              'The KD handback counter applies to translated execution. '
              'Physical chain lengths were unmeasured.')
    table(['Workers', 'Lines', 'KD delegated / handback', 'KD offered / sessions', 'KD plain / parked',
           'KD head sleep / handoff', 'TCLock delegated / batches / parks'],
          [(r['workers'], r['lines'], counts(r['kd'], 'kd', ('delegated', 'handback')),
            counts(r['kd'], 'kd', ('offered', 'sessions')), counts(r['kd'], 'kd', ('plain', 'parked')),
            counts(r['kd'], 'kd', ('head_sleep', 'handoff')), counts(r['tclock'], 'tc', TC_KEYS)) for r in report['standard']])
    paragraph('## Matched sleepable entry thresholds')
    paragraph('Threshold 3 is the compiled default. The Native and TCLock controls in this block ran '
              'in the same rotation as each KD setting. Changes and wins use this block’s threshold-3 KD rows.')
    table(['Workers', 'Lines', 'Native', 'TCLock', 'TCLock delegated / batches / parks'],
          [(r['workers'], r['lines'], rate(r['native']), rate(r['tclock']), counts(r['tclock'], 'tc', TC_KEYS))
           for r in report['threshold'] if r['threshold'] == 3])
    table(['Workers', 'Lines', 'Threshold', 'KD', 'Change vs 3 (wins)', 'KD vs Native (wins)', 'KD vs TCLock (wins)',
           'KD delegated / handback', 'KD plain / parked', 'Mode enter / exit'],
          [(r['workers'], r['lines'], r['threshold'], rate(r['kd']),
            comparison(r['vs_default']) if r['threshold'] != 3 else 'reference',
            comparison(r['vs_native']), comparison(r['vs_tclock']), counts(r['kd'], 'kd', ('delegated', 'handback')),
            counts(r['kd'], 'kd', ('plain', 'parked')), counts(r['kd'], 'kd', ('mode_enter', 'mode_exit')))
           for r in report['threshold']])
    paragraph(f'The spread flag marks a within-cell range of at least {SPREAD_PCT:g}% of its median. '
              'Three matched rounds give a descriptive comparison.')
    variation = []
    for setting in (2, 5):
        rows = [r for r in report['threshold'] if r['threshold'] == setting]
        total = len(rows)
        higher = [r for r in rows if r['vs_default']['wins'] == r['vs_default']['n']]
        lower = [r for r in rows if r['vs_default']['losses'] == r['vs_default']['n']]
        fmt = lambda items: ', '.join(f"{r['workers']}w/{r['lines']}L" for r in items) or 'none'
        paragraph(f"At threshold {setting}, KD won every matched round in {len(higher)}/{total} cells "
                  f"({fmt(higher)}), lost every round in {len(lower)}/{total} ({fmt(lower)}), "
                  f"and had mixed or tied rounds in {total-len(higher)-len(lower)}/{total}.")
    for group, phase in [('standard', 'three-way'), ('threshold', 'threshold')]:
        for row in report[group]:
            for name in BACKENDS:
                if group == 'threshold' and name != 'kd' and row['threshold'] != 3:
                    continue
                cell = row[name]
                if cell['spread_pct'] >= SPREAD_PCT:
                    variation.append((phase, row['workers'], row['lines'], name, row.get('threshold', 3),
                                      f"{cell['spread_pct']:.2f}%"))
    table(['Phase', 'Workers', 'Lines', 'Backend', 'Threshold', 'Flagged spread'], variation)
    if not variation:
        paragraph('No cell reached the spread flag.')
    paragraph('## Learning and functional checks')
    table(['Phase', 'Family', 'Backend', 'Workers', 'Round', 'Operations', 'KD delegated / handback',
           'Compact offered / completed'], [
              (r['phase'], r['family'], r['backend'], r['workers'], r['round'], f"{r['ops']:,}",
               counts(r, 'kd_delta', ('delegated', 'handback')), counts(r, 'kd_delta', ('cl_offered', 'cl_done')))
              for r in report['functional']])
    if report['reference_kd_activity']:
        paragraph('Global KD counter activity during Native or TCLock points '
                  + json.dumps(report['reference_kd_activity'], sort_keys=True))
    return '\n'.join(out).rstrip('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path, help='collected directory containing points.jsonl and identity.json')
    parser.add_argument('--format', choices=('md', 'json'), default='md')
    args = parser.parse_args()
    report = analyze(args.evidence)
    print(json.dumps(report, indent=2, sort_keys=True) if args.format == 'json' else markdown(report))
    return int(bool(report['errors']))


if __name__ == '__main__':
    sys.exit(main())
