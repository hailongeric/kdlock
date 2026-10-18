#!/usr/bin/env python3
"""Offline, read-only analysis of rwsem optimization evidence.

Usage: python3 report.py RUN_MAP.json NEW_OUTPUT_DIRECTORY
Map keys: baseline-grid, baseline-screen, poll-screen, split-screen, final-grid,
final-reference; optional long-screen, xlong-screen, grant-screen,
grants128-screen, baseline-repeat-screen,
baseline-profile and final-profile. Values are evidence
directories, or tar.gz archives containing one runner's top-level JSON receipts.
Relative paths resolve against the map. Missing runs are reported, never inferred.
No benchmarks, imports from runner source, builds or dependency installs occur.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import tarfile


THREADS = [*range(1, 9), *range(12, 61, 4)]
CASES = [('cacheline', 1, 'c01'), ('cacheline', 8, 'c08'), ('rcuht', 0, 'RCUHT')]
LABELS = {(workload, lines): label for workload, lines, label in CASES}
MIXES = (1, 20)
OPTIONAL_SCREENS = ('long-screen', 'grant-screen', 'grants128-screen',
                    'xlong-screen', 'baseline-repeat-screen')
RUNS = ('baseline-grid', 'baseline-screen', 'poll-screen', 'split-screen',
        *OPTIONAL_SCREENS, 'final-grid', 'final-reference')
RATE_FIELDS = ('whole_min_ops_s', 'whole_median_ops_s', 'whole_max_ops_s',
               'best_peak_ops_s', 'peak_min_ops_s', 'peak_median_ops_s', 'peak_max_ops_s')
FILES = ('plan.json', 'records.json', 'summary.json', 'parity.json',
         'source-sha256.json', 'binary-sha256.json', 'environment.json')
IDENTITY = ('lock_kind', 'duration_ms', 'peak_window_ms', 'peak_settle_ms', 'sample_ms',
            'post_work_rounds', 'collector_cpu', 'provider_ubsan', 'warmup_iterations_per_worker',
            'mix_policy', 'cpus', 'cpu_nodes', 'caller_abi', 'entry_abi', 'delegate',
            'rwsem_writer_shell', 'numa_policy', 'delegation_batch_limit', 'spin_entry_ratio_limit')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


def csv_file(path, rows, fields=None):
    fields = fields or list(dict.fromkeys(key for row in rows for key in row)) or ['no_rows']
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows({key: canonical(value) if isinstance(value, (dict, list)) else value
                         for key, value in row.items()} for row in rows)


def evidence(path, names=FILES):
    """Read only named JSON receipts; archive member paths are never extracted."""
    blobs = {}
    if path.is_dir():
        for name in names:
            item = path / name
            if item.is_file():
                blobs[name] = item.read_bytes()
    elif path.is_file() and tarfile.is_tarfile(path):
        with tarfile.open(path) as archive:
            candidates = defaultdict(list)
            for member in archive:
                if member.isfile() and Path(member.name).name in names:
                    candidates[Path(member.name).name].append(member)
            # The shortest paths identify top-level receipts rather than any
            # source copy containing the same filename. Ambiguity fails closed.
            for name, members in candidates.items():
                depth = min(len(Path(member.name).parts) for member in members)
                chosen = [member for member in members if len(Path(member.name).parts) == depth]
                require(len(chosen) == 1, f'ambiguous archive receipt {name}: {path}')
                blobs[name] = archive.extractfile(chosen[0]).read()
    return ({name: json.loads(blob) for name, blob in blobs.items()},
            {name: digest(blob) for name, blob in blobs.items()})


def valid(row):
    measured = row.get('measurement', {})
    return (row.get('execution_status') == 'OK' and row.get('drained') is True and
            measured.get('data_ok') is True and measured.get('complete') is True and
            row.get('functional') is False and not row.get('diagnostic') and
            row.get('score_eligible') is not False)


def point_key(row):
    return row['workload'], row['cachelines'], row['write_percent'], row['threads']


def group_key(row):
    return row['variant'], row['write_percent'], row['threads'], row['jit_status']


def close(left, right):
    return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-7)


def schema_for(name):
    cases = CASES if name.endswith('grid') or name == 'final-reference' else CASES[:1]
    workers = THREADS if name.endswith('grid') else [1, 8, 32, 36, 60] if name == 'final-reference' else [1, 8, 32, 60]
    arms = ('native', 'tclock', 'kdlock') if name == 'final-reference' else ('native', 'kdlock')
    return cases, workers, arms


def read_run(name, path):
    data, hashes = evidence(path)
    missing = [filename for filename in ('plan.json', 'records.json', 'summary.json',
               'source-sha256.json', 'environment.json') if filename not in data]
    if missing:
        return dict(name=name, path=str(path), status='MISSING_EVIDENCE', missing=missing,
                    input_sha256=hashes, groups=[], sessions=[], points=[])
    plan, records, summaries = (data[filename] for filename in FILES[:3])
    require(not any(row.get('diagnostic') or row.get('score_eligible') is False for row in plan + records),
            name + ': profiled/diagnostic rows cannot enter performance analysis')
    planned, recorded = ({row['name']: row for row in values} for values in (plan, records))
    require(len(planned) == len(plan) and len(recorded) == len(records), name + ': duplicate names')
    require(recorded.keys() <= planned.keys(), name + ': foreign session records')
    cases, workers, arms = schema_for(name)
    expected = {(workload, lines, percent, count, arm, repeat)
                for workload, lines, _ in cases for percent in MIXES for count in workers
                for arm in arms for repeat in range(3)}
    actual = {(*point_key(row), row['arm'], row['repeat']) for row in plan}
    require(len(actual) == len(plan), name + ': duplicate configuration/repetition')
    require(actual <= expected, name + ': unexpected workload/mix/workers/backend')
    kind = 'rwlock' if name == 'final-reference' else 'rwsem'
    for spec in plan:
        require(spec['lock_kind'] == kind and not spec['functional'] and spec['duration_ms'] == 2000 and
                spec['cpus'] == list(range(spec['threads'])) and spec['collector_cpu'] == 63 and
                spec['peak_window_ms'] == spec['peak_settle_ms'] == 300 and spec['sample_ms'] == 10 and
                spec['post_work_rounds'] == 4 and spec['warmup_iterations_per_worker'] == 48000 and
                spec['provider_ubsan'] == 'off' and spec['mix_policy'] == 'evenly_spaced_worker_phase17',
                name + ': measurement identity differs')
        if kind == 'rwsem':
            kd = spec['arm'] == 'kdlock'
            require(spec['delegate'] == kd and spec['entry_abi'] == (2 if kd else None) and
                    spec['caller_abi'] == ('clobber' if kd else 'c') and
                    spec['rwsem_writer_shell'] == ('delegated-epoch-abi2' if kd else 'ordinary-local'),
                    name + ': incompatible rwsem writer shell')
        if spec['name'] in recorded:
            require(all(recorded[spec['name']].get(key) == value for key, value in spec.items()),
                    name + ': record differs from frozen plan: ' + spec['name'])
    sessions, members = [], defaultdict(list)
    for spec in plan:
        row = recorded.get(spec['name'], dict(spec, execution_status='NOT_RUN', drained=False))
        receipt = {key: row.get(key) for key in ('name', 'arm', 'variant', 'workload', 'cachelines',
            'write_percent', 'threads', 'repeat', 'execution_status', 'drained', 'jit_status',
            'jit_bodies', 'jit_completions', 'jit_complete_share', 'tclock_delegation_status', 'error')}
        receipt.update(run=name, valid=valid(row), completed=None, whole_ops_s=None,
                       peak_ops_s=None, worker_cpu_ns_per_op=None)
        sessions.append(receipt)
        if not valid(row):
            continue
        measured = row['measurement']
        whole = measured['completed'] * 1e9 / measured['wall_ns']
        peak = measured['peak']['throughput_ops_s']
        require(all(math.isfinite(value) and value > 0 for value in (whole, peak)), name + ': invalid rate')
        entries, completions, writes = row['jit_bodies'], row['jit_completions'], measured['writes']
        require(0 <= completions <= entries <= writes and writes > 0 and
                row['jit_after'] - row['jit_before'] == entries and
                row['jit_complete_after'] - row['jit_complete_before'] == completions and
                close(row['jit_complete_share'], completions / writes), name + ': invalid JIT counts')
        expected_status = ('PASS' if completions else 'PARTIAL_JIT' if entries else 'NO_JIT') \
            if row['arm'] == 'kdlock' else 'NATIVE'
        require(row['jit_status'] == expected_status and (row['arm'] == 'kdlock' or entries == completions == 0),
                name + ': JIT disposition differs from completed bodies')
        if row['arm'] == 'tclock':
            require(row.get('tclock_delegation_status') == 'UNMEASURED',
                    name + ': TCLock delegation observation is missing or unexpectedly changed')
        if row['arm'] == 'kdlock':
            publication = row.get('published_before')
            require(publication is not None and publication == row.get('published_after') and
                    publication['source']['writers'] == publication['source']['frames'] == 0 and
                    publication['source']['state'] == 0 and
                    publication['entry']['entry_abi'] == row['entry_abi'] and
                    publication['entry']['entry'] == row['layout']['entry'],
                    name + ': publication fence absent or changed')
            def parameter(key):
                value = row['parameters'][key]
                return {'Y': 1, 'N': 0}[value] if value in ('Y', 'N') else int(value, 0)
            require(parameter('bench_complete_probe') == parameter('bench_quiet') == parameter('hotlock_stats') == 1
                    and parameter('jit_timing') == 0, name + ': observation settings changed')
        workers_data = measured.get('workers', [])
        cpu_time = None
        if len(workers_data) == row['threads'] and all(isinstance(worker.get('cpu_ns'), (int, float))
                                                      and worker['cpu_ns'] > 0 for worker in workers_data):
            cpu_time = sum(worker['cpu_ns'] for worker in workers_data) / measured['completed']
        receipt.update(completed=measured['completed'], whole_ops_s=whole, peak_ops_s=peak,
                       worker_cpu_ns_per_op=cpu_time)
        members[group_key(row)].append((row, receipt))
    summary_map = {group_key(row): row for row in summaries}
    require(len(summary_map) == len(summaries) and summary_map.keys() == members.keys(),
            name + ': summary groups differ from valid records')
    groups = []
    for key, cohort in sorted(members.items()):
        rows, receipts = zip(*cohort)
        first, saved = rows[0], summary_map[key]
        require(len({canonical({key: row.get(key) for key in IDENTITY}) for row in rows}) == 1,
                name + ': mixed shell/placement/settings inside group')
        whole, peaks = ([receipt[field] for receipt in receipts] for field in ('whole_ops_s', 'peak_ops_s'))
        rates = dict(zip(RATE_FIELDS, (min(whole), statistics.median(whole), max(whole), max(peaks),
                                       min(peaks), statistics.median(peaks), max(peaks))))
        require(saved['valid_rounds'] == len(rows) and saved['expected_rounds'] == 3 and
                saved['complete'] == (len(rows) == 3) and
                set(saved['samples']) == {row['name'] for row in rows} and
                all(close(saved[field], value) for field, value in rates.items()),
                name + ': saved group rates or membership disagree')
        cpu = [receipt['worker_cpu_ns_per_op'] for receipt in receipts]
        groups.append(dict(run=name, source_id=digest(canonical(data['source-sha256.json']).encode()),
            workload=first['workload'], cachelines=first['cachelines'],
            label=LABELS[(first['workload'], first['cachelines'])],
            write_percent=first['write_percent'], threads=first['threads'], arm=first['arm'],
            variant=first['variant'], lock_kind=kind, jit_status=first['jit_status'],
            tclock_delegation_status=first.get('tclock_delegation_status', 'NOT_APPLICABLE'),
            valid_rounds=len(rows), complete=len(rows) == 3, **rates,
            worker_cpu_ns_per_op_median=statistics.median(cpu) if all(value is not None for value in cpu) else None,
            worker_cpu_ns_per_op_min=min(cpu) if all(value is not None for value in cpu) else None,
            worker_cpu_ns_per_op_max=max(cpu) if all(value is not None for value in cpu) else None,
            jit_entries_min=min(row['jit_bodies'] for row in rows),
            jit_entries_max=max(row['jit_bodies'] for row in rows),
            jit_completions_min=min(row['jit_completions'] for row in rows),
            jit_completions_max=max(row['jit_completions'] for row in rows),
            jit_complete_share_min=min(row['jit_complete_share'] for row in rows),
            jit_complete_share_max=max(row['jit_complete_share'] for row in rows),
            identity={key: first.get(key) for key in IDENTITY}, samples=[row['name'] for row in rows]))
    missing_points = sorted(expected - actual)
    environment = data['environment.json']
    return dict(name=name, path=str(path), status='COMPLETE' if not missing_points and
                all(row['valid'] for row in sessions) else 'INCOMPLETE',
        input_sha256=hashes, source_sha256=data['source-sha256.json'],
        source_id=digest(canonical(data['source-sha256.json']).encode()), environment=environment,
        planned_sessions=len(plan), expected_sessions=len(expected), valid_sessions=sum(row['valid'] for row in sessions),
        missing_configurations=missing_points, session_status_counts=dict(Counter(row['execution_status'] for row in sessions)),
        kd_jit_status_counts=dict(Counter(row['jit_status'] for row in sessions if row['valid'] and row['arm'] == 'kdlock')),
        all_sessions_drained=all(row['drained'] for row in sessions), groups=groups, sessions=sessions)


def select(run, key, arm):
    groups = [row for row in run.get('groups', []) if point_key(row) == key and row['arm'] == arm]
    label = ';'.join(f"{row['jit_status']}:{row['valid_rounds']}" for row in groups)
    if len(groups) == 1 and groups[0]['complete']:
        return groups[0], label, ''
    reason = 'SPLIT_EXECUTION_STATUSES' if sum(row['valid_rounds'] for row in groups) == 3 else 'MISSING_VALID_REPETITIONS'
    return None, label or 'NONE', reason


def compatible(left_run, right_run, left, right):
    if left is None or right is None:
        return False, 'MISSING_HOMOGENEOUS_GROUP'
    if left['identity'] != right['identity']:
        return False, 'DIFFERENT_CALL_SHELL_OR_MEASUREMENT_IDENTITY'
    left_env, right_env = left_run['environment'], right_run['environment']
    for key in ('running_build_id', 'config'):
        if left_env['kernel_identity'].get(key) != right_env['kernel_identity'].get(key):
            return False, 'DIFFERENT_KERNEL_' + key.upper()
    for key in ('cmdline', 'preemption'):
        if left_env.get(key) != right_env.get(key):
            return False, 'DIFFERENT_RUNTIME_' + key.upper()
    for key in ('online_cpus', 'allowed_cpus'):
        if left_env['topology'].get(key) != right_env['topology'].get(key):
            return False, 'DIFFERENT_TOPOLOGY_' + key.upper()
    # Full-grid and focused runs have different role lists, so compare the
    # recorded NUMA placement of only this point's worker and collector CPUs.
    mappings = [dict(zip(env['topology']['role_cpus'], env['topology']['role_nodes']))
                for env in (left_env, right_env)]
    for cpu in [*left['identity']['cpus'], left['identity']['collector_cpu']]:
        if cpu not in mappings[0] or cpu not in mappings[1] or mappings[0][cpu] != mappings[1][cpu]:
            return False, 'DIFFERENT_TOPOLOGY_ROLE_NODE'
    return True, ''


def add_group(point, prefix, group, label, reason):
    point[prefix + '_groups'] = label
    point[prefix + '_missing_reason'] = reason
    for field in (*RATE_FIELDS, 'worker_cpu_ns_per_op_median', 'jit_completions_min', 'jit_completions_max'):
        point[prefix + '_' + field] = group[field] if group else None
    point[prefix + '_jit_status'] = group['jit_status'] if group else ''


def pair_ratio(point, prefix, left, right, allowed=True, reason=''):
    point[prefix + '_whole_ratio'] = left['whole_median_ops_s'] / right['whole_median_ops_s'] \
        if allowed and left and right else None
    point[prefix + '_peak_ratio'] = left['best_peak_ops_s'] / right['best_peak_ops_s'] \
        if allowed and left and right else None
    ratios = (point[prefix + '_whole_ratio'], point[prefix + '_peak_ratio'])
    point[prefix + '_status'] = ('PASS' if min(ratios) >= 1 else 'FAIL') if None not in ratios else 'INCOMPLETE'
    point[prefix + '_reason'] = (reason or 'MISSING_HOMOGENEOUS_GROUP') if point[prefix + '_status'] == 'INCOMPLETE' else ''


def comparisons(runs):
    points, screens, references = [], [], []
    before, after = runs['baseline-grid'], runs['final-grid']
    for workload, lines, label in CASES:
        for percent in MIXES:
            for workers in THREADS:
                key = workload, lines, percent, workers
                point = dict(workload=label, write_percent=percent, threads=workers)
                selected = {}
                for phase, run in (('before', before), ('after', after)):
                    for arm in ('native', 'kdlock'):
                        selected[phase, arm], group_label, reason = select(run, key, arm)
                        add_group(point, phase + '_' + arm, selected[phase, arm], group_label, reason)
                allowed, reason = compatible(after, before, selected['after', 'kdlock'], selected['before', 'kdlock'])
                pair_ratio(point, 'kd_after_before', selected['after', 'kdlock'], selected['before', 'kdlock'], allowed, reason)
                allowed, reason = compatible(after, before, selected['after', 'native'], selected['before', 'native'])
                pair_ratio(point, 'native_after_before', selected['after', 'native'], selected['before', 'native'], allowed, reason)
                pair_ratio(point, 'after_kd_native', selected['after', 'kdlock'], selected['after', 'native'])
                pair_ratio(point, 'before_kd_native', selected['before', 'kdlock'], selected['before', 'native'])
                points.append(point)
    for name in (name for name in runs if name.endswith('-screen')):
        run = runs[name]
        for percent in MIXES:
            for workers in (1, 8, 32, 60):
                key = 'cacheline', 1, percent, workers
                row = dict(run=name, workload='c01', write_percent=percent, threads=workers)
                kd, kd_label, kd_reason = select(run, key, 'kdlock')
                native, native_label, native_reason = select(run, key, 'native')
                add_group(row, 'kdlock', kd, kd_label, kd_reason)
                add_group(row, 'native', native, native_label, native_reason)
                pair_ratio(row, 'kd_native', kd, native)
                baseline_names = ['baseline-grid', 'baseline-screen']
                if 'baseline-repeat-screen' in runs:
                    baseline_names.append('baseline-repeat-screen')
                for baseline_name in baseline_names:
                    for arm, group in (('kdlock', kd), ('native', native)):
                        previous, previous_label, _ = select(runs[baseline_name], key, arm)
                        allowed, reason = compatible(run, runs[baseline_name], group, previous)
                        pair_ratio(row, arm + '_vs_' + baseline_name.replace('-', '_'), group, previous, allowed, reason)
                        row[arm + '_vs_' + baseline_name.replace('-', '_') + '_jit_groups'] = (
                            kd_label if arm == 'kdlock' else native_label) + ' / ' + previous_label
                screens.append(row)
    run = runs['final-reference']
    for workload, lines, label in CASES:
        for percent in MIXES:
            for workers in (1, 8, 32, 36, 60):
                key = workload, lines, percent, workers
                row = dict(workload=label, write_percent=percent, threads=workers, lock_kind='rwlock')
                selected = {}
                for arm in ('native', 'tclock', 'kdlock'):
                    selected[arm], group_label, reason = select(run, key, arm)
                    add_group(row, arm, selected[arm], group_label, reason)
                pair_ratio(row, 'tclock_native', selected['tclock'], selected['native'])
                pair_ratio(row, 'kd_native', selected['kdlock'], selected['native'])
                row['tclock_delegation_status'] = selected['tclock']['tclock_delegation_status'] \
                    if selected['tclock'] else 'MISSING_HOMOGENEOUS_GROUP'
                references.append(row)
    return points, screens, references


def geometric(points):
    groups = defaultdict(list)
    for row in points:
        for prefix, statuses in (
                ('kd_after_before', ('before_kdlock_jit_status', 'after_kdlock_jit_status')),
                ('after_kd_native', ('after_kdlock_jit_status',))):
            if row[prefix + '_whole_ratio'] is not None:
                key = prefix, row['workload'], row['write_percent'], *(row[field] for field in statuses)
                groups[key].append(row)
    return [dict(comparison=key[0], workload=key[1], write_percent=key[2], jit_statuses=list(key[3:]),
                 points=len(rows), workers=[row['threads'] for row in rows],
                 whole_ratio=math.exp(statistics.mean(math.log(row[key[0] + '_whole_ratio']) for row in rows)),
                 peak_ratio=math.exp(statistics.mean(math.log(row[key[0] + '_peak_ratio']) for row in rows)))
            for key, rows in sorted(groups.items())]


def figures(out, points, references):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.lines import Line2D
    except ImportError as error:
        return dict(status='UNAVAILABLE', reason=str(error), files=[])
    matplotlib.rcParams.update({'svg.fonttype': 'none', 'font.size': 9, 'svg.hashsalt': 'kd-rwsem-opt-20261018'})
    markers = {'NO_JIT': 's', 'PARTIAL_JIT': '^', 'PASS': 'o', 'NATIVE': 'x'}
    outputs = []
    specifications = (
        ('rwsem-throughput', points, THREADS,
         [('before_kdlock', '#c28d4f', 'Before KD rwsem', '--'),
          ('after_kdlock', '#b43b2c', 'Final KD rwsem', '-'),
          ('before_native', '#9ba8b5', 'Before Native rwsem', '--'),
          ('after_native', '#245b87', 'Final Native rwsem', '-')],
         'Sleeping rwsem: whole-run median; shaded observed repetition range'),
        ('rwlock-reference', references, [1, 8, 32, 36, 60],
         [('native', '#245b87', 'Native rwlock', '-'),
          ('tclock', '#467943', 'TCLock rwlock', '-'),
          ('kdlock', '#b43b2c', 'KD rwlock', '-')],
         'Separate spinning-rwlock reference: these APIs are not sleeping rwsems'))
    for filename, source, worker_grid, series, title in specifications:
        fig, axes = plt.subplots(3, 2, figsize=(12, 10), sharex=True, constrained_layout=True)
        for row_index, (_, _, label) in enumerate(CASES):
            for column, percent in enumerate(MIXES):
                ax = axes[row_index, column]
                rows = {row['threads']: row for row in source if row['workload'] == label and row['write_percent'] == percent}
                for prefix, color, legend, style in series:
                    values = [[rows[count].get(prefix + '_' + field) for count in worker_grid]
                              for field in RATE_FIELDS[:3]]
                    low, median, high = [[value / 1e6 if value is not None else math.nan for value in group] for group in values]
                    ax.plot(worker_grid, median, color=color, linestyle=style, linewidth=1.5, label=legend)
                    ax.fill_between(worker_grid, low, high, color=color, alpha=.10)
                    if 'kdlock' in prefix:
                        for status, marker in markers.items():
                            cohort = [row for row in rows.values() if row.get(prefix + '_jit_status') == status and
                                      row.get(prefix + '_whole_median_ops_s') is not None]
                            ax.scatter([row['threads'] for row in cohort],
                                       [row[prefix + '_whole_median_ops_s'] / 1e6 for row in cohort],
                                       color=color, marker=marker, s=20)
                ax.set_title(f'{label}, {percent}% writes')
                ax.set_ylabel('Mops/s')
                ax.set_ylim(bottom=0)
                ax.set_xlim(.5, 60.5)
                ax.set_xticks((1, 8, 16, 24, 32, 36, 48, 60))
                ax.grid(alpha=.2)
                if row_index == 2:
                    ax.set_xlabel('Workers')
        handles, labels = axes[0, 0].get_legend_handles_labels()
        present = {row.get(prefix + '_jit_status') for row in source for prefix, _, _, _ in series if 'kdlock' in prefix}
        for status in ('NO_JIT', 'PARTIAL_JIT', 'PASS', 'NATIVE'):
            if status in present:
                handles.append(Line2D([], [], marker=markers[status], color='#333333', linestyle='None'))
                labels.append('no KD JIT witness' if status == 'NATIVE' else 'KD ' +
                              {'NO_JIT': 'no JIT body', 'PARTIAL_JIT': 'entry only',
                               'PASS': 'completed JIT body'}[status])
        fig.legend(handles, labels, loc='outside lower center', ncol=4, fontsize=8)
        fig.suptitle(title + '\nGaps mean split execution statuses or missing valid repetitions; no mixed groups are pooled', fontsize=11)
        for suffix in ('svg', 'png'):
            path = out / (filename + '.' + suffix)
            fig.savefig(path, dpi=150, metadata={'Date': None} if suffix == 'svg' else None)
            if suffix == 'svg':
                path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines()) + '\n')
            outputs.append(path.name)
        plt.close(fig)
    return dict(status='GENERATED', matplotlib_version=matplotlib.__version__, files=outputs)


def format_rate(value):
    return '—' if value is None else f'{value / 1e6:.3f}'


def format_ratio(value):
    return '—' if value is None else f'{value:.3f}×'


def format_range(row, prefix):
    if row[prefix + '_whole_median_ops_s'] is None:
        return '—'
    return (format_rate(row[prefix + '_whole_median_ops_s']) + ' [' +
            format_rate(row[prefix + '_whole_min_ops_s']) + ', ' +
            format_rate(row[prefix + '_whole_max_ops_s']) + ']')


def table(headers, rows):
    return ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join('---' for _ in headers) + ' |',
            *('| ' + ' | '.join(map(str, row)) + ' |' for row in rows)]


def markdown(result):
    runs, points = result['runs'], result['points']
    text = ['# KD rwsem optimization evidence', '',
        'Rates are recomputed from raw valid records and checked against the saved runner summary. '
        'Every source version, call shell and JIT execution status remains a separate group. '
        'A three-run point is blank when statuses split, even if all sessions succeeded. '
        'PASS in a JIT field means a completed delegated body; PASS in a comparison field means '
        'both observed median-whole and best-peak ratios are at least one. These are descriptive '
        'measurements, not significance tests.', '',
        'The full matrices use c01, c08 and RCUHT; 1% and 20% writes; workers 1–8 and 12–60 by four; '
        'three repetitions and two seconds per session. Fresh c01 screens use 1, 8, 32 and 60 workers. '
        'Worker CPU ns/op is the sum of measured worker thread CPU time divided by completed operations; '
        'it excludes other threads and is not elapsed lock latency.', '', '## Run coverage', '']
    text += table(['Run', 'Status', 'Valid / expected sessions', 'KD JIT sessions', 'Source content ID'],
        [(name, runs[name]['status'], f"{runs[name].get('valid_sessions', 0)}/{runs[name].get('expected_sessions', 'unknown')}",
          canonical(runs[name].get('kd_jit_status_counts', {})), runs[name].get('source_id', '—')[:16]) for name in runs])
    text += ['', 'The displayed source content ID is the first 16 hexadecimal characters of SHA256 over '
        'canonical JSON content (sorted keys and compact separators) of the source manifest. It is not '
        'the raw manifest-file hash. Full canonical IDs and raw `source-sha256.json` file hashes are '
        'retained separately in `analysis.json` (`source_id` and `input_sha256`). KD JIT counts in the '
        'coverage table count sessions, not status groups.', '']
    for name in runs:
        if runs[name].get('missing'):
            text += ['', f"Missing evidence for `{name}`: {', '.join(runs[name]['missing'])}."]
    text += ['', '## Sixty workers: sleeping rwsem', '',
             'Median whole-run Mops/s. Both Native control versions are shown separately; their drift is not normalized away.', '']
    text += table(['Workload', 'Writes', 'Before KD', 'Final KD', 'Before Native', 'Final Native',
                   'KD final / before', 'KD final / Native', 'KD JIT before → final'],
        [(row['workload'], f"{row['write_percent']}%", *(format_rate(row[prefix + '_whole_median_ops_s'])
          for prefix in ('before_kdlock', 'after_kdlock', 'before_native', 'after_native')),
          format_ratio(row['kd_after_before_whole_ratio']), format_ratio(row['after_kd_native_whole_ratio']),
          row['before_kdlock_groups'] + ' → ' + row['after_kdlock_groups']) for row in points if row['threads'] == 60])
    text += ['', '## Full-grid outcomes', '']
    text += table(['Comparison', 'PASS', 'FAIL', 'INCOMPLETE'],
        [(label, *(Counter(row[prefix + '_status'] for row in points)[status] for status in ('PASS', 'FAIL', 'INCOMPLETE')))
         for prefix, label in (('kd_after_before', 'Final KD / before KD'), ('after_kd_native', 'Final KD / final Native'),
                               ('native_after_before', 'Final Native / before Native'))])
    text += ['', 'All 126 point values, whole-run ranges, warmed peaks, JIT completion ranges and CPU costs are in '
        '`points.csv`. `regressions.csv` lists every final/before KD or final/Native point below one on either '
        'throughput metric. `groups.csv` retains incomplete status-specific groups; `sessions.csv` retains '
        'individual raw rates and failures. `screen-points.csv` compares each c01 candidate separately with '
        'the original grid and fresh baseline screen, including Native drift. No candidate screen is merged '
        'with a full grid.', '', '## Split or missing comparison points', '']
    incomplete = [row for row in points if row['kd_after_before_status'] == 'INCOMPLETE' or row['after_kd_native_status'] == 'INCOMPLETE']
    text += table(['Workload', 'Writes', 'Workers', 'Before KD groups', 'Final KD groups', 'Final Native groups', 'Reason'],
        [(row['workload'], row['write_percent'], row['threads'], row['before_kdlock_groups'], row['after_kdlock_groups'],
          row['after_native_groups'], row['kd_after_before_reason'] or row['after_kdlock_missing_reason'] or
          row['after_native_missing_reason']) for row in incomplete]) if incomplete else ['No incomplete comparison points.']
    text += ['', '## Focused screens and baseline controls', '',
        'Each candidate is compared with the fresh baseline screen. A candidate with lower rates remains '
        'in these receipts; its presence does not mean it was selected. These are the 60-worker c01 rows; '
        'the CSV also retains 1, 8 and 32 workers and comparisons with the earlier full baseline. '
        'Rates are medians with observed [min, max] ranges, not confidence intervals. '
        'The historical full baseline and fresh baseline are distinct runs even when source hashes match. '
        'Separate Native controls expose run variability; candidate/baseline ratios are not normalized '
        'by Native drift or interpreted as statistical significance. Optional experimental screen groups '
        'appear only when provided in the input map. An optional `baseline-repeat-screen` is a separate '
        'later baseline control, not a candidate or a pooled baseline. When supplied, the CSV also '
        'compares every screen with this later control to expose drift across the experiment.', '']
    text += table(['Run', 'Writes', 'KD Mops/s [range]', 'Native Mops/s [range]', 'KD / fresh baseline',
                   'Native / fresh baseline', 'KD execution groups'],
        [(row['run'], row['write_percent'], format_range(row, 'kdlock'), format_range(row, 'native'),
          format_ratio(row['kdlock_vs_baseline_screen_whole_ratio']),
          format_ratio(row['native_vs_baseline_screen_whole_ratio']), row['kdlock_groups'])
         for row in result['screens'] if row['threads'] == 60])
    text += ['', '## Spinning-rwlock reference', '',
        'TCLock implements a spinning rwlock in this port, not a sleeping rwsem. The separate reference '
        'uses Native/TCLock/KD rwlocks at 1, 8, 32, 36 and 60 workers for the same three non-sleeping payloads '
        'and two mixes. Its rates are not scored as rwsem parity and are not pooled with rwsem runs. '
        '`rwlock-reference.csv` retains all 30 reference points. The runner labels TCLock `jit_status=NATIVE` '
        'because KD JIT witnesses do not apply to that backend; this does not establish local TCLock '
        'execution. Its delegation observation remains `UNMEASURED`. Mixed KD JIT statuses suppress '
        'only the affected KD comparison; a complete Native/TCLock comparison remains available.', '']
    text += table(['Workload', 'Writes', 'Workers', 'Native rwlock', 'TCLock rwlock', 'KD rwlock'],
        [(row['workload'], row['write_percent'], row['threads'], *(format_rate(row[prefix + '_whole_median_ops_s'])
          for prefix in ('native', 'tclock', 'kdlock'))) for row in result['references'] if row['threads'] == 60])
    text += ['', '## Diagnostic profiles', '',
        'Optional function-profile counts are saved separately in `diagnostics.json`. Profiling changes execution '
        'cost and includes background activity. Profiled rates never enter these performance groups or plots. '
        'Per-function calls/op may help identify an exercised path; they do not establish exclusive CPU cost. '
        'Nested function times must not be summed.', '', '## Figures and identity', '',
        'SVG lines have trailing whitespace removed; CSV records use LF. Shading is the observed three-repetition '
        'range, not a confidence interval. Connected points retain their separate status markers. '
        'Kernel identity, topology, source manifests and input hashes are retained in `analysis.json`. '
        'Cross-version ratios require equal call-shell/placement/measurement identity and kernel/config/runtime '
        'identity. Source differences are listed in `source-differences.json`; measurements are never pooled '
        'across those versions.', '']
    if result['figures']['status'] == 'GENERATED':
        text += ['![Sleeping rwsem throughput](rwsem-throughput.svg)', '',
                 '![Separate spinning-rwlock reference](rwlock-reference.svg)', '']
    else:
        text += ['Figures unavailable: ' + result['figures']['reason'], '']
    return '\n'.join(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_map', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    mapping = json.loads(args.run_map.read_text())
    require(isinstance(mapping, dict) and set(mapping) <= {*RUNS, 'baseline-profile', 'final-profile'},
            'map contains unknown run names')
    paths = {name: (args.run_map.resolve().parent / value).resolve() for name, value in mapping.items()}
    out = args.output.resolve()
    require(not out.exists() and all(not path.is_dir() or not out.is_relative_to(path) for path in paths.values()),
            'use a new output directory outside all evidence directories')
    runs = {name: read_run(name, paths[name]) if name in paths else
            dict(name=name, status='MISSING_EVIDENCE', missing=['run not provided'], groups=[], sessions=[])
            for name in RUNS if name not in OPTIONAL_SCREENS or name in mapping}
    points, screens, references = comparisons(runs)
    diagnostics = {}
    for name in ('baseline-profile', 'final-profile'):
        if name in paths:
            rows, hashes = evidence(paths[name], names=('function-count-summary.json', 'diagnostic.json', 'result.json'))
            diagnostics[name] = dict(path=str(paths[name]), input_sha256=hashes, diagnostic=True,
                                     score_eligible=False, data=rows,
                                     status='AVAILABLE' if 'function-count-summary.json' in rows else 'MISSING_EVIDENCE')
    source_differences = []
    baseline_names = ['baseline-grid', 'baseline-screen']
    if 'baseline-repeat-screen' in runs:
        baseline_names.append('baseline-repeat-screen')
    for baseline_name in baseline_names:
        baseline = runs[baseline_name].get('source_sha256', {})
        for name, run in runs.items():
            current = run.get('source_sha256', {})
            if name != baseline_name and baseline and current:
                source_differences.append(dict(before=baseline_name, after=name,
                    changed=[dict(path=path, before=baseline.get(path), after=current.get(path))
                             for path in sorted(baseline.keys() | current.keys()) if baseline.get(path) != current.get(path)]))
    groups = [row for run in runs.values() for row in run['groups']]
    sessions = [row for run in runs.values() for row in run['sessions']]
    result = dict(schema=1, runs=runs, points=points, screens=screens, references=references,
                  geometric_ratios=geometric(points), analysis_script_sha256=digest(Path(__file__).read_bytes()),
                  run_map_sha256=digest(args.run_map.read_bytes()))
    out.mkdir(parents=True)
    csv_file(out / 'points.csv', points)
    csv_file(out / 'sixty-workers.csv', [row for row in points if row['threads'] == 60])
    csv_file(out / 'groups.csv', groups)
    csv_file(out / 'sessions.csv', sessions)
    csv_file(out / 'screen-points.csv', screens)
    csv_file(out / 'rwlock-reference.csv', references)
    csv_file(out / 'geometric-ratios.csv', result['geometric_ratios'])
    csv_file(out / 'regressions.csv', [row for row in points if row['kd_after_before_status'] == 'FAIL' or
                                     row['after_kd_native_status'] == 'FAIL'], list(points[0]))
    save(out / 'diagnostics.json', diagnostics)
    save(out / 'source-differences.json', source_differences)
    result['figures'] = figures(out, points, references)
    # Re-read receipt hashes to catch evidence changing during this offline pass.
    for name, path in paths.items():
        if name in RUNS and runs[name].get('input_sha256'):
            require(evidence(path)[1] == runs[name]['input_sha256'], name + ': evidence changed during analysis')
    save(out / 'analysis.json', result)
    (out / 'README.md').write_text(markdown(result))
    print(json.dumps(dict(output=str(out), runs={name: run['status'] for name, run in runs.items()},
                          figures=result['figures']), indent=2))


if __name__ == '__main__':
    main()
