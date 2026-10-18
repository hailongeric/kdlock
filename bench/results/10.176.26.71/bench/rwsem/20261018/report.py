#!/usr/bin/env python3
"""Read-only analysis of one frozen 756-session rwsem comparison.

Usage: python3 report.py EVIDENCE_DIRECTORY NEW_OUTPUT_DIRECTORY
Writes compact CSV/JSON/Markdown and optional matplotlib SVG/PNG figures.
Never rebuilds, loads modules, changes evidence, or merges separate runs.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics


THREADS = [*range(1, 9), *range(12, 61, 4)]
CASES = [('cacheline', 1, 'c01'), ('cacheline', 8, 'c08'), ('rcuht', 0, 'RCUHT')]
MIXES = (1, 20)
ARMS = ('native', 'kdlock')
STATUS = ('NATIVE', 'NO_JIT', 'PARTIAL_JIT', 'PASS')
RATE_FIELDS = ('whole_min_ops_s', 'whole_median_ops_s', 'whole_max_ops_s',
               'best_peak_ops_s', 'peak_min_ops_s', 'peak_median_ops_s', 'peak_max_ops_s')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


def write_csv(path, rows, fields=None):
    fields = fields or list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list))
                             else value for key, value in row.items()})


def valid(row):
    return (row.get('execution_status') == 'OK' and row.get('drained') is True and
            row.get('measurement', {}).get('data_ok') is True and
            row.get('measurement', {}).get('complete') is True and
            row.get('functional') is False)


def point_key(row):
    return row['workload'], row['cachelines'], row['write_percent'], row['threads']


def group_key(row):
    return row['variant'], row['write_percent'], row['threads'], row['jit_status']


def equal_rate(left, right):
    return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-7)


def analyze(evidence):
    names = ('plan.json', 'records.json', 'summary.json', 'parity.json',
             'source-sha256.json', 'binary-sha256.json', 'environment.json')
    inputs = {name: sha256(evidence / name) for name in names}
    plan, records, summaries, parity = (read_json(evidence / name) for name in names[:4])
    environment = read_json(evidence / 'environment.json')
    require(len(plan) == len(records) == 756, 'expected 756 planned and recorded rows')
    planned = {row['name']: row for row in plan}
    recorded = {row['name']: row for row in records}
    require(len(planned) == len(recorded) == 756 and planned.keys() == recorded.keys(),
            'missing, duplicate or foreign session names')
    expected = {(workload, lines, percent, workers, arm, repeat)
                for workload, lines, _ in CASES for percent in MIXES
                for workers in THREADS for arm in ARMS for repeat in range(3)}
    actual = {(*point_key(row), row['arm'], row['repeat']) for row in plan}
    require(actual == expected, 'plan is not the requested c01/c08/RCUHT standard matrix')
    common = ('lock_kind', 'duration_ms', 'peak_window_ms', 'peak_settle_ms',
              'sample_ms', 'post_work_rounds', 'collector_cpu', 'provider_ubsan',
              'warmup_iterations_per_worker', 'mix_policy')
    identities = {key: {json.dumps(row.get(key), sort_keys=True) for row in plan}
                  for key in common}
    require(all(len(values) == 1 for values in identities.values()),
            'mixed measurement/caller identities in one frozen plan')
    identity = {key: json.loads(next(iter(values))) for key, values in identities.items()}
    require(identity == dict(lock_kind='rwsem', duration_ms=2000, peak_window_ms=300,
                             peak_settle_ms=300, sample_ms=10, post_work_rounds=4,
                             collector_cpu=63, provider_ubsan='off',
                             warmup_iterations_per_worker=48000,
                             mix_policy='evenly_spaced_worker_phase17'),
            'measurement identity differs from the documented comparison')
    require(all(row['lock_kind'] == 'rwsem' and not row['functional'] and
                row['duration_ms'] == 2000 and row['cpus'] == list(range(row['threads'])) and
                row['collector_cpu'] == 63 for row in plan), 'unsupported matrix identity')
    for row in plan:
        kd = row['arm'] == 'kdlock'
        require(row['delegate'] == kd and row['entry_abi'] == (2 if kd else None) and
                row['caller_abi'] == ('clobber' if kd else 'c') and
                row['rwsem_writer_shell'] == ('delegated-epoch-abi2' if kd else 'ordinary-local'),
                'mixed delegated/local writer shells')
        require(all(recorded[row['name']].get(key) == value for key, value in row.items()),
                'record identity differs from its frozen plan: ' + row['name'])

    by_group = defaultdict(list)
    by_point = defaultdict(list)
    failed = []
    sessions = []
    for row in records:
        receipt = dict(name=row['name'], workload=row['workload'], cachelines=row['cachelines'],
            write_percent=row['write_percent'], threads=row['threads'], arm=row['arm'], repeat=row['repeat'],
            execution_status=row.get('execution_status'), valid=valid(row), drained=row.get('drained'),
            jit_status=row.get('jit_status'), jit_entries=row.get('jit_bodies'),
            jit_completions=row.get('jit_completions'), jit_complete_share=row.get('jit_complete_share'),
            completed=None, reads=None, writes=None, wall_ns=None, whole_ops_s=None, peak_ops_s=None,
            error=row.get('error'))
        sessions.append(receipt)
        if not valid(row):
            failed.append(dict(name=row['name'], execution_status=row.get('execution_status'),
                               drained=row.get('drained'), error=row.get('error')))
            continue
        measurement = row['measurement']
        whole = measurement['completed'] * 1e9 / measurement['wall_ns']
        peak = measurement['peak']['throughput_ops_s']
        require(math.isfinite(whole) and math.isfinite(peak) and whole > 0 and peak > 0,
                'invalid throughput: ' + row['name'])
        entries, completions, writes = row['jit_bodies'], row['jit_completions'], measurement['writes']
        receipt.update(completed=measurement['completed'], reads=measurement['reads'], writes=writes,
                       wall_ns=measurement['wall_ns'], whole_ops_s=whole, peak_ops_s=peak)
        require(0 <= completions <= entries <= writes and row['jit_status'] in STATUS,
                'invalid JIT count/status: ' + row['name'])
        require(row['jit_after'] - row['jit_before'] == entries and
                row['jit_complete_after'] - row['jit_complete_before'] == completions and
                writes > 0 and equal_rate(row['jit_complete_share'], completions / writes),
                'JIT totals differ from measured counter deltas or writer denominator')
        require(row['arm'] == 'kdlock' or (entries == completions == 0),
                'Native session recorded delegated bodies')
        expected_jit = ('PASS' if completions else 'PARTIAL_JIT' if entries else 'NO_JIT') \
            if row['arm'] == 'kdlock' else 'NATIVE'
        require(row['jit_status'] == expected_jit, 'JIT disposition disagrees with completion evidence')
        if row['arm'] == 'kdlock':
            before, after = row.get('published_before'), row.get('published_after')
            require(before is not None and before == after and before['entry']['entry_abi'] == 2 and
                    before['entry']['lock_kind'] == 2 and before['source']['writers'] == 0 and
                    before['source']['frames'] == 0 and before['source']['state'] == 0 and
                    before['entry']['entry'] == row['layout']['entry'],
                    'publication fence missing/changed: ' + row['name'])
            def parameter(name):
                value = row['parameters'][name]
                return {'Y': 1, 'N': 0}[value] if value in ('Y', 'N') else int(value, 0)
            require(parameter('bench_lock_addr') == row['layout']['gate_addr'] and
                    parameter('bench_complete_probe') == 1 and parameter('jit_timing') == 0 and
                    parameter('bench_quiet') == 1 and parameter('hotlock_stats') == 1,
                    'completion observer or diagnostic instrumentation differs')
        by_group[group_key(row)].append((row, whole, peak))
        by_point[point_key(row)].append(row)

    summary_map = {group_key(row): row for row in summaries}
    require(len(summary_map) == len(summaries) and summary_map.keys() == by_group.keys(),
            'saved summary does not match valid execution-status groups')
    group_rows = []
    for key, members in sorted(by_group.items()):
        saved = summary_map[key]
        rows, whole, peaks = zip(*members)
        computed = dict(whole_min_ops_s=min(whole), whole_median_ops_s=statistics.median(whole),
                        whole_max_ops_s=max(whole), best_peak_ops_s=max(peaks),
                        peak_min_ops_s=min(peaks), peak_median_ops_s=statistics.median(peaks),
                        peak_max_ops_s=max(peaks))
        require(saved['valid_rounds'] == len(rows) and saved['expected_rounds'] == 3 and
                saved['complete'] == (len(rows) == 3) and
                set(saved['samples']) == {row['name'] for row in rows}, 'saved group membership differs')
        require(all(equal_rate(saved[name], value) for name, value in computed.items()),
                'saved rates differ from raw measurements')
        first = rows[0]
        group_rows.append(dict(workload=first['workload'], cachelines=first['cachelines'],
            write_percent=first['write_percent'], threads=first['threads'], arm=first['arm'],
            variant=first['variant'], jit_status=first['jit_status'], valid_rounds=len(rows),
            complete=len(rows) == 3, **computed,
            jit_entries_min=min(row['jit_bodies'] for row in rows),
            jit_entries_max=max(row['jit_bodies'] for row in rows),
            jit_completions_min=min(row['jit_completions'] for row in rows),
            jit_completions_max=max(row['jit_completions'] for row in rows),
            jit_complete_share_min=min(row['jit_complete_share'] for row in rows),
            jit_complete_share_max=max(row['jit_complete_share'] for row in rows),
            samples=[row['name'] for row in rows]))

    saved_points = {point_key(row): row for row in parity['points']}
    require(len(saved_points) == len(parity['points']) == 126, 'expected 126 saved parity points')
    points = []
    geometric = []
    for workload, lines, label in CASES:
        for percent in MIXES:
            for workers in THREADS:
                key = workload, lines, percent, workers
                saved = saved_points[key]
                point = dict(workload=label, write_percent=percent, threads=workers,
                             status='INCOMPLETE', kd_jit_status='', reason_code='', reason='')
                selected = {}
                for arm in ARMS:
                    groups = [row for row in group_rows if point_key(row) == key and row['arm'] == arm]
                    point[arm + '_valid_rounds'] = sum(row['valid_rounds'] for row in groups)
                    point[arm + '_jit_groups'] = ';'.join(
                        row['jit_status'] + ':' + str(row['valid_rounds']) for row in groups)
                    eligible = len(groups) == 1 and groups[0]['complete'] and groups[0]['valid_rounds'] == 3
                    if eligible:
                        selected[arm] = groups[0]
                    for field in RATE_FIELDS:
                        point[arm + '_' + field] = groups[0][field] if eligible else None
                kd_rows = [row for row in by_point[key] if row['arm'] == 'kdlock']
                for field in ('jit_bodies', 'jit_completions', 'jit_complete_share'):
                    values = [row[field] for row in kd_rows]
                    point['kd_' + field + '_min'] = min(values) if values else None
                    point['kd_' + field + '_max'] = max(values) if values else None
                point.update(kd_native_whole_ratio=None, kd_native_peak_ratio=None)
                if set(selected) == set(ARMS):
                    kd, native = selected['kdlock'], selected['native']
                    point['kd_jit_status'] = kd['jit_status']
                    point['kd_native_whole_ratio'] = kd['whole_median_ops_s'] / native['whole_median_ops_s']
                    point['kd_native_peak_ratio'] = kd['best_peak_ops_s'] / native['best_peak_ops_s']
                    point['status'] = 'PASS' if min(point['kd_native_whole_ratio'],
                                                   point['kd_native_peak_ratio']) >= 1 else 'FAIL'
                    for field, saved_field in (('kd_native_whole_ratio', 'median_whole'),
                                               ('kd_native_peak_ratio', 'best_peak')):
                        require(equal_rate(point[field], saved['ratios']['native'][saved_field]),
                                'saved parity ratio differs')
                else:
                    if all(point[arm + '_valid_rounds'] == 3 for arm in ARMS):
                        point['reason_code'] = 'SPLIT_EXECUTION_STATUSES'
                        point['reason'] = ('All six sessions are valid; execution statuses split at least one '
                                           'backend across groups, so no homogeneous three-round comparison exists')
                    else:
                        point['reason_code'] = 'MISSING_VALID_REPETITIONS'
                        point['reason'] = ('At least one backend lacks three valid repetitions; '
                                           'execution-status groups remain separate')
                require(point['status'] == saved['status'], 'saved parity disposition differs')
                points.append(point)
            for status in STATUS:
                cohort = [point for point in points if point['workload'] == label and
                          point['write_percent'] == percent and point['kd_jit_status'] == status and
                          point['status'] != 'INCOMPLETE']
                if len(cohort) >= 2:
                    geometric.append(dict(workload=label, write_percent=percent, kd_jit_status=status,
                        accepted_points=len(cohort), total_grid_points=21,
                        workers=[point['threads'] for point in cohort],
                        whole_ratio=math.exp(statistics.mean(math.log(point['kd_native_whole_ratio'])
                                                            for point in cohort)),
                        peak_ratio=math.exp(statistics.mean(math.log(point['kd_native_peak_ratio'])
                                                           for point in cohort))))
    computed_parity = ('PASS' if all(point['status'] == 'PASS' for point in points) else
                       'FAIL' if any(point['status'] == 'FAIL' for point in points) else 'INCOMPLETE')
    require(parity['status'] == computed_parity, 'saved overall parity disposition differs')
    require(inputs == {name: sha256(evidence / name) for name in names}, 'evidence changed during analysis')
    result = dict(schema=1, evidence=str(evidence), input_sha256=inputs,
        plan_identity=identity,
        topology=environment.get('topology'), kernel_identity=environment.get('kernel_identity'),
        planned_sessions=756, valid_sessions=sum(valid(row) for row in records),
        session_status_counts=dict(Counter(row.get('execution_status', 'UNKNOWN') for row in records)),
        kd_jit_status_counts=dict(Counter(row['jit_status'] for row in records
                                         if valid(row) and row['arm'] == 'kdlock')),
        all_sessions_drained=all(row.get('drained') is True for row in records),
        planned_points=126, point_status_counts=dict(Counter(point['status'] for point in points)),
        incomplete_reason_counts=dict(Counter(point['reason_code'] for point in points
                                               if point['status'] == 'INCOMPLETE')),
        saved_parity_status=parity['status'], failed_sessions=failed,
        geometric_ratios=geometric, points=points, groups=group_rows, sessions=sessions)
    return result


def figures(out, points):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.lines import Line2D
    except ImportError as error:
        return dict(status='UNAVAILABLE', reason=str(error), files=[])
    matplotlib.rcParams.update({'svg.fonttype': 'none', 'font.size': 10})
    colors = {'native': '#415d7a', 'kdlock': '#bc482e'}
    markers = {'NATIVE': 'x', 'NO_JIT': 's', 'PARTIAL_JIT': '^', 'PASS': 'o'}
    status_labels = {'NATIVE': 'KD local', 'NO_JIT': 'KD no entry',
                     'PARTIAL_JIT': 'KD entry only', 'PASS': 'KD completed writers'}
    # Use every panel to decide the common legend. A status absent from c01 at
    # 1% writes must still be explained when it appears elsewhere in the grid.
    present = {point['kd_jit_status'] for point in points if point['kd_jit_status']}
    throughput_legend = [Line2D([], [], color=colors[arm], linewidth=1.6,
                               label='Linux Native' if arm == 'native' else 'KD rwsem')
                         for arm in ARMS]
    throughput_legend.extend(Line2D([], [], color=colors['kdlock'], marker=markers[status],
                                    linestyle='None', markersize=5, label=status_labels[status])
                             for status in STATUS if status in present)
    figure, axes = plt.subplots(3, 2, figsize=(12, 11), sharex=True, constrained_layout=True)
    ratio_figure, ratio_axes = plt.subplots(3, 2, figsize=(12, 11), sharex=True, constrained_layout=True)
    for row_index, (_, _, label) in enumerate(CASES):
        for column, percent in enumerate(MIXES):
            selected = [point for point in points if point['workload'] == label and
                        point['write_percent'] == percent]
            ax, ratio_ax = axes[row_index, column], ratio_axes[row_index, column]
            title = f'{label}, {percent}% writes'
            ax.set_title(title)
            ratio_ax.set_title(title)
            for arm in ARMS:
                def rates(field):
                    return [point[arm + '_' + field] / 1e6 if point[arm + '_' + field] is not None
                            else math.nan for point in selected]
                low, median, high = (rates(field) for field in RATE_FIELDS[:3])
                ax.plot(THREADS, median, label='Linux Native' if arm == 'native' else 'KD rwsem',
                        color=colors[arm], linewidth=1.6)
                ax.fill_between(THREADS, low, high, color=colors[arm], alpha=.15)
            for status, marker in markers.items():
                cohort = [point for point in selected if point['kd_jit_status'] == status and
                          point['kdlock_whole_median_ops_s'] is not None]
                ax.scatter([point['threads'] for point in cohort],
                           [point['kdlock_whole_median_ops_s'] / 1e6 for point in cohort],
                           marker=marker, color=colors['kdlock'], s=22)
            for field, color, marker, label_text in (
                    ('kd_native_whole_ratio', '#bc482e', 'o', 'Median whole-run'),
                    ('kd_native_peak_ratio', '#415d7a', 'D', 'Best warmed peak')):
                values = [point[field] if point[field] is not None else math.nan for point in selected]
                ratio_ax.plot(THREADS, values, color=color, marker=marker, markersize=3,
                              label=label_text, linewidth=1.4)
            ratio_ax.axhline(1, color='#555555', linestyle='--', linewidth=1)
            for axis in (ax, ratio_ax):
                axis.grid(alpha=.25)
                axis.set_xlim(.5, 60.5)
                axis.set_xticks((1, 8, 16, 24, 32, 40, 48, 56, 60))
                if row_index == 2:
                    axis.set_xlabel('Workers')
            ax.set_ylim(bottom=0)
            ax.set_ylabel('Whole-run throughput (Mops/s)')
            ratio_ax.set_ylabel('KD / Linux Native')
            if row_index == column == 0:
                ax.legend(handles=throughput_legend, fontsize=8, ncol=2)
                ratio_ax.legend(fontsize=8)
    figure.suptitle('Rwsem: median whole-run throughput; shading is the observed three-run range\n'
                    'One homogeneous group per backend; gaps can represent split statuses despite valid runs', fontsize=12)
    ratio_figure.suptitle('Rwsem: KD / Linux Native throughput ratios\n'
                          'Ratios use complete three-run groups; the dashed line is parity', fontsize=12)
    files = []
    for base, fig in (('throughput', figure), ('ratios', ratio_figure)):
        for suffix in ('svg', 'png'):
            name = base + '.' + suffix
            fig.savefig(out / name, dpi=160)
            files.append(name)
        plt.close(fig)
    return dict(status='GENERATED', matplotlib_version=matplotlib.__version__, files=files)


def rate(value):
    return '—' if value is None else f'{value / 1e6:.3f}'


def ratio(value):
    return '—' if value is None else f'{value:.3f}×'


def md_table(headers, rows):
    return ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join('---' for _ in headers) + ' |',
            *('| ' + ' | '.join(str(cell) for cell in row) + ' |' for row in rows)]


def markdown(result):
    points = result['points']
    counts = result['point_status_counts']
    incomplete_counts = result['incomplete_reason_counts']
    text = ['# KD rwsem writer delegation compared with Linux Native', '',
        f"The frozen matrix contains {result['valid_sessions']}/756 valid sessions and 126 comparison points. "
        f"Observed peak-and-whole parity passes at {counts.get('PASS', 0)} points, is slower on at least "
        f"one metric at {counts.get('FAIL', 0)}, and has no homogeneous three-round comparison at "
        f"{counts.get('INCOMPLETE', 0)}.", '',
        f"The runner's `INCOMPLETE` parity status does not mean tests were skipped. "
        f"{incomplete_counts.get('SPLIT_EXECUTION_STATUSES', 0)} points have all six valid executions "
        f"but split execution statuses; {incomplete_counts.get('MISSING_VALID_REPETITIONS', 0)} points "
        f"lack three valid repetitions for at least one backend.", '',
        'c01, c08 and RCUHT use 1% and 20% writes, workers 1–8 then 12–60 by four, '
        'three repetitions per backend and two-second timed intervals. Workers occupy CPU prefixes '
        '0..N−1; collector CPU 63 is separate. Whole-run throughput includes the complete joined '
        'measurement interval. Warmed peak is the best valid 300 ms window after 300 ms settling.', '',
        'Each point is comparable only when each backend has exactly one complete three-repetition '
        'execution-status group. Mixed PASS/NO_JIT/PARTIAL_JIT repetitions remain separate in '
        '`groups.csv`; their point rates/ratios are blank rather than pooled. PASS in a KD JIT field '
        'means completed delegated writer bodies, while PASS in the parity field means both observed '
        'throughput ratios are at least one. Neither outcome is a statistical significance claim.', '',
        '## Coverage', '']
    rows = []
    for _, _, label in CASES:
        for percent in MIXES:
            cohort = [point for point in points if point['workload'] == label and point['write_percent'] == percent]
            c = Counter(point['status'] for point in cohort)
            reasons = Counter(point['reason_code'] for point in cohort if point['status'] == 'INCOMPLETE')
            rows.append((label, f'{percent}%', c['PASS'], c['FAIL'],
                         reasons['SPLIT_EXECUTION_STATUSES'], reasons['MISSING_VALID_REPETITIONS']))
    text += md_table(['Workload', 'Writes', 'Parity pass', 'Slower', 'Split statuses', 'Missing valid repeats'], rows)
    text += ['', f"Session dispositions: `{json.dumps(result['session_status_counts'], sort_keys=True)}`. "
             f"All sessions drained: **{result['all_sessions_drained']}**.", '',
             f"KD execution dispositions: `{json.dumps(result['kd_jit_status_counts'], sort_keys=True)}`.", '',
             '## Sixty workers', '', 'Throughput is Mops/s. Parentheses give the observed minimum–maximum '
             'whole-run rate across the same three repetitions.', '']
    rows = []
    for point in points:
        if point['threads'] != 60:
            continue
        rates = []
        for arm in ARMS:
            rates.append(f"{rate(point[arm + '_whole_median_ops_s'])} "
                         f"({rate(point[arm + '_whole_min_ops_s'])}–{rate(point[arm + '_whole_max_ops_s'])})")
        rows.append((point['workload'], f"{point['write_percent']}%", *rates,
                     ratio(point['kd_native_whole_ratio']), ratio(point['kd_native_peak_ratio']),
                     point['kd_jit_status'] or point['kdlock_jit_groups'], point['status']))
    text += md_table(['Workload', 'Writes', 'Native whole', 'KD whole', 'Whole ratio',
                      'Peak ratio', 'KD JIT', 'Parity'], rows)
    text += ['', '## Geometric ratios within execution-status groups', '',
             'These unweighted summaries cover only the listed accepted worker counts within one '
             'workload, mix and KD execution status. They are descriptive ratios, not aggregate '
             'throughput and not a substitute for the complete grid. Single-point groups are omitted.', '']
    text += md_table(['Workload', 'Writes', 'KD JIT', 'Points / 21', 'Whole ratio', 'Peak ratio', 'Workers'],
        [(row['workload'], f"{row['write_percent']}%", row['kd_jit_status'], row['accepted_points'],
          ratio(row['whole_ratio']), ratio(row['peak_ratio']), ', '.join(map(str, row['workers'])))
         for row in result['geometric_ratios']])
    text += ['', '## Every observed regression', '',
             'A point appears below when KD is slower on median whole-run throughput or best warmed '
             'peak. No tolerance is applied. All 126 points, both backends’ ranges and JIT completion '
             'ranges are retained in `points.csv`; this table is also `regressions.csv`.', '']
    regressions = [point for point in points if point['status'] == 'FAIL']
    if regressions:
        text += md_table(['Workload', 'Writes', 'Workers', 'Whole ratio', 'Peak ratio', 'KD JIT'],
            [(point['workload'], f"{point['write_percent']}%", point['threads'],
              ratio(point['kd_native_whole_ratio']), ratio(point['kd_native_peak_ratio']), point['kd_jit_status'])
             for point in regressions])
    else:
        text.append('No complete comparison point has an observed ratio below one.')
    incomplete = [point for point in points if point['status'] == 'INCOMPLETE']
    if incomplete:
        text += ['', '## Points without a homogeneous three-repetition comparison', '',
                 'Group labels include the execution status and its number of valid repetitions. '
                 'A `NO_JIT:2;PASS:1` KD point has three successful runs, but pooling them would erase '
                 'a material execution difference. Such points retain the runner’s `INCOMPLETE` parity '
                 'status and blank combined ratios.', '']
        text += md_table(['Workload', 'Writes', 'Workers', 'Native groups', 'KD groups', 'Reason'],
            [(point['workload'], f"{point['write_percent']}%", point['threads'],
              point['native_jit_groups'], point['kdlock_jit_groups'],
              'Split statuses; all six runs valid' if point['reason_code'] == 'SPLIT_EXECUTION_STATUSES'
              else 'Missing valid repetitions') for point in incomplete])
        split_keys = {(point['workload'], point['write_percent'], point['threads']) for point in incomplete
                      if point['reason_code'] == 'SPLIT_EXECUTION_STATUSES'}
        if split_keys:
            labels = {(workload, lines): label for workload, lines, label in CASES}
            text += ['', 'These status-specific rates remain descriptive partial groups; they do not '
                     'supply an accepted three-repetition KD/Native ratio. Throughput is Mops/s.', '']
            text += md_table(['Workload', 'Writes', 'Workers', 'Backend', 'JIT status', 'Repetitions',
                              'Whole median', 'Whole min–max', 'Best peak', 'Completed bodies min–max'],
                [(labels[(row['workload'], row['cachelines'])], f"{row['write_percent']}%", row['threads'],
                  row['arm'], row['jit_status'], row['valid_rounds'], rate(row['whole_median_ops_s']),
                  f"{rate(row['whole_min_ops_s'])}–{rate(row['whole_max_ops_s'])}", rate(row['best_peak_ops_s']),
                  f"{row['jit_completions_min']}–{row['jit_completions_max']}")
                 for row in result['groups'] if
                 (labels[(row['workload'], row['cachelines'])], row['write_percent'], row['threads']) in split_keys])
    text += ['', '## Artifacts and checks', '',
             '`analysis.json` preserves input hashes, topology, kernel identity, all computed groups, '
             'point dispositions and failed sessions. This analysis recomputed rates/group membership '
             'from valid raw records and checked them against the runner’s saved summary and parity. '
             'It also required stable ABI2 mutex publication and zero translator writers/frames at '
             'the measured boundaries. It does not rerun workload oracles or kernel checks.', '']
    plot = result['figures']
    if plot['status'] == 'GENERATED':
        text += ['![Whole-run throughput](throughput.svg)', '', '![Throughput ratios](ratios.svg)', '',
                 'SVG and PNG versions are available. Whole-run shading is the observed repetition '
                 'range, not a confidence interval. A gap can represent three successful KD runs '
                 'split across execution statuses; it does not by itself mean a skipped or failed test. '
                 'Connected points describe the same frozen source and settings; markers retain '
                 'their separate KD execution statuses, and no repetitions are pooled across them.', '']
    else:
        text += ['Figures were not generated: ' + plot['reason'] + '. No packages were installed.', '']
    return '\n'.join(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    evidence, out = args.evidence.resolve(), args.output.resolve()
    require(evidence.is_dir(), 'missing frozen evidence directory')
    require(not out.exists() and not out.is_relative_to(evidence),
            'use a new output directory outside frozen evidence')
    result = analyze(evidence)
    out.mkdir(parents=True)
    write_csv(out / 'points.csv', result['points'])
    write_csv(out / 'groups.csv', result['groups'])
    write_csv(out / 'sessions.csv', result['sessions'])
    write_csv(out / 'regressions.csv', [point for point in result['points'] if point['status'] == 'FAIL'],
              list(result['points'][0]))
    write_csv(out / 'sixty-workers.csv', [point for point in result['points'] if point['threads'] == 60])
    result['figures'] = figures(out, result['points'])
    result['analysis_script_sha256'] = sha256(Path(__file__))
    write_json(out / 'analysis.json', result)
    (out / 'README.md').write_text(markdown(result))
    print(json.dumps(dict(output=str(out), valid_sessions=result['valid_sessions'],
                          points=result['point_status_counts'], figures=result['figures']), indent=2))


if __name__ == '__main__':
    main()
