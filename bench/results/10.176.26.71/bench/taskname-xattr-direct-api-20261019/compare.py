#!/usr/bin/env python3
"""Create tables from two completed evidence replays; run only in the idle VM.

Usage: compare.py OLD_REPLAY.json NEW_REPLAY.json NEW_OUTPUT_DIRECTORY

This reads JSON only: it never imports archived code, runs workloads or modifies
the report README. Run the separate raw-evidence replay first. The adjacent
comparison-policy.json pins the old receipt and the two intended source trees.
It separately pins both replay implementations: the new one also validates
loaded generated images. The four measurement validators must remain identical.
The output directory must not exist. An incomplete policy fails before reading
either replay. No partial-run or identity override exists.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import statistics


GRID = [*range(1, 9), *range(12, 61, 4)]
ARMS = ('native', 'tclock', 'kdlock')
CASES = ('taskname', 'xattr-tail-n16-v64', 'xattr-tail-n128-v64')
METRICS = ('whole_ops_s', 'peak_ops_s', 'worker_cpu_ns_per_op',
           'jit_complete_share')
COUNTERS = ('jit_entries', 'jit_completions', 'address_guard_exits')
COMMON = ('cpus', 'cpu_nodes', 'collector_cpu', 'duration_ms',
          'peak_window_ms', 'peak_settle_ms', 'sample_ms')
CONTROL_FIELDS = {
    'taskname': COMMON + ('post_work_rounds', 'warmup_iterations_per_worker',
                         'mix_policy'),
    'xattr': COMMON + ('warmup', 'warmup_ms', 'helper_waves', 'helper_cpus',
                      'file_descriptions', 'source_identity', 'kernel_identity',
                      'topology_identity'),
}
LABELS = {'taskname': 'Taskname, read-only',
          'xattr-tail-n16-v64': 'Xattr tail, n16/v64',
          'xattr-tail-n128-v64': 'Xattr tail, n128/v64'}
MISSING = {'missing': True}
BASELINE_COMMIT = '88bb5a4d9b52eec8ed52982ea4039b981d0e5814'
BASELINE_REPLAY = 'ca29dc4dc8595c051d13fcaf68860927e92730239dbc1c6724764aef231d5af9'
DIRECT_DEPENDENCIES = {'bench/spin_cacheline/native_image.py',
                       'bench/spin_cacheline/bench_runtime.py',
                       'bench/spin_cacheline/summarize.py',
                       'tests/protocols/native_only_protocol.py',
                       'tests/protocols/cpu_placement.py',
                       'disassem/device_session.py'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    blob = path.read_bytes()
    return json.loads(blob), sha(blob)


def validate_policy(policy):
    """Refuse draft policies and any unreviewed comparison/analysis exception."""
    require(policy.get('schema') == 2 and policy.get('ready') is True and
            policy.get('pending') == [], 'comparison policy is incomplete; freeze its source/replay identities first')
    require(policy['old_commit'] == BASELINE_COMMIT and
            policy['old_replay_sha256'] == BASELINE_REPLAY,
            'comparison must use the completed original-API 88 baseline')
    require(isinstance(policy['new_commit'], str) and
            re.fullmatch(r'[0-9a-f]{40}', policy['new_commit']) and
            policy['new_commit'] != policy['old_commit'], 'missing/distinct current commit required')
    require(policy['identity_allowed_differences'] ==
            {'taskname': [], 'xattr': ['source_identity']},
            'only the exact source revision may differ in historical group identities')
    require(isinstance(policy['new_round_symbols_sha256'], str) and
            re.fullmatch(r'[0-9a-f]{64}', policy['new_round_symbols_sha256']),
            'exact current round-symbol receipt hash required')
    shared = policy['analysis_dependencies']
    require(set(shared) == {'bench/spin_cacheline/peak.py', 'bench/rwlock_compare/oracle.py',
                           'bench/real_api/report.py', 'bench/real_api/evidence.py'},
            'measurement validator dependency set changed')
    for label in ('old', 'new'):
        program = policy['replay_programs'][label]
        require(isinstance(program['script_sha256'], str) and
                re.fullmatch(r'[0-9a-f]{64}', program['script_sha256']),
                label + ': exact replay program hash required')
        additions = program['additional_dependency_sha256']
        require(isinstance(additions, dict) and not (set(additions) & set(shared)),
                label + ': replay additions cannot override measurement validators')
        require(label != 'old' or not additions, 'baseline replay had no added image validators')
        require(label != 'new' or set(additions) == DIRECT_DEPENDENCIES,
                'new loaded-image replay dependency set differs')
        require(all(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value)
                    for value in {**shared, **additions}.values()),
                label + ': exact dependency hashes required')
    require(set(policy['sources']) == {'taskname', 'xattr'}, 'missing source-manifest policy')
    for run_kind, known in policy['sources'].items():
        require(all(type(known[key]) is int and known[key] > 0 for key in ('old_files', 'new_files')) and
                all(isinstance(known[key], str) and re.fullmatch(r'[0-9a-f]{64}', known[key])
                    for key in ('old_source_id', 'new_source_id')) and isinstance(known['changes'], dict),
                run_kind + ': exact source manifests/change list required')
        for path, change in known['changes'].items():
            require(not Path(path).is_absolute() and '..' not in Path(path).parts and
                    path not in ('', '.') and change['old'] != change['new'] and
                    all(value is None or (isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value))
                        for value in (change['old'], change['new'])) and change.get('reason'),
                    'invalid explicit source change: ' + path)


def kind(case):
    return 'taskname' if case == 'taskname' else 'xattr'


def finite(value, *, positive=False):
    return (type(value) in (int, float) and math.isfinite(value) and
            (value > 0 if positive else value >= 0))


def equal_number(left, right):
    if left is None or right is None:
        return left is right
    return (finite(left) and finite(right) and
            math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-9))


def cohort_key(row):
    return (row['case'], row['threads'], row['arm'], row['jit_status'],
            canonical(row['identity']))


def validate_image_evidence(row, run, symbols):
    """Validate receipt linkage separately from throughput/cohort identity."""
    image = row['measured_image']
    if row['arm'] != 'kdlock':
        require(image is None, 'control incorrectly carries a KD loaded-image witness')
        return
    requirement = 24 if row['run'] == 'taskname' else 20
    require(image['requirements'] == requirement and image['entry'] > 0 and
            image['base'] > 0 and image['generation'] > 0,
            'new: wrong direct-image identity/requirements')
    path = f"loaded-images/{image['entry']:016x}-g{image['generation']}.bin"
    require(image['path'] == path, 'new: loaded-image path differs from generation')
    hashes = run['input_sha256']
    loaded_path = row['name'] + '/' + path
    receipt_path = str(Path(loaded_path).with_suffix('.json'))
    require(hashes.get(loaded_path) == image['loaded_sha256'] and
            isinstance(hashes.get(receipt_path), str) and
            re.fullmatch(r'[0-9a-f]{64}', hashes[receipt_path]),
            'new: loaded binary or receipt absent from raw replay inputs')
    require(any(path.startswith(row['name'] + '/publications/') and path.endswith('/jit.bin')
                and value == image['uploaded_sha256'] for path, value in hashes.items()),
            'new: uploaded generated image absent from raw replay inputs')
    required_service, symbol = (5, 'strscpy_pad') if row['run'] == 'taskname' else (4, 'strcmp')
    require(1 <= len(image['relocations']) <= 64, 'new: missing generated CALL relocation witnesses')
    occupied = set()
    for item in image['relocations']:
        require(item['service'] == required_service and item['symbol'] == symbol and
                item['target'] == symbols[symbol] and item['continuation'] > 0 and
                48 <= item['offset'] < 640 * 1024 - 5 and
                item['displacement'] == item['target'] - (image['base'] + item['offset'] + 5) and
                -(1 << 31) <= item['displacement'] < (1 << 31),
                'new: inconsistent generated CALL relocation receipt')
        span = set(range(item['offset'], item['offset'] + 5))
        require(not occupied & span, 'new: overlapping generated CALL slots')
        occupied.update(span)


def validate_replay(replay, label):
    """Check receipt coverage and recompute medians, without rerunning raw replay."""
    schema = 1 if label == 'old' else 2
    require(replay.get('schema') == schema and replay.get('complete') is True,
            label + ': requires a successful schema-' + str(schema) + ' raw replay')
    require(set(replay['runs']) == {'taskname', 'xattr'}, label + ': missing run')
    all_groups, summary = {}, {}
    for run_kind, run in replay['runs'].items():
        cases = CASES[:1] if run_kind == 'taskname' else CASES[1:]
        expected = {(case, n, arm, repeat) for case in cases for n in GRID
                    for arm in ARMS for repeat in range(3)}
        require(run['complete'] is True and run['all_sessions_drained'] is True,
                label + '/' + run_kind + ': incomplete or undrained replay')
        require(all(run[field] == len(expected) for field in
                    ('expected_sessions', 'planned_sessions', 'valid_sessions')),
                label + '/' + run_kind + ': wrong session coverage')
        require(run['missing_configurations'] == [], label + ': missing configurations')
        require(run['source_id'] == sha(canonical(run['source_sha256']).encode()),
                label + ': inconsistent source manifest identity')
        sessions = run['sessions']
        actual = {(row['case'], row['threads'], row['arm'], row['repeat'])
                  for row in sessions}
        require(len(sessions) == len(actual) and actual == expected,
                label + '/' + run_kind + ': duplicate, missing or unexpected sample')
        require(len({row['name'] for row in sessions}) == len(sessions),
                label + ': duplicate session name')
        cohorts = defaultdict(list)
        for row in sessions:
            require(row['valid'] is True and row['drained'] is True and
                    row['execution_status'] == 'OK' and row['run'] == run_kind,
                    label + ': failed, unvalidated or undrained sample')
            require(row['source_id'] == run['source_id'] and
                    isinstance(row['identity'], dict), label + ': mixed source identity')
            if label == 'new':
                validate_image_evidence(row, run, replay['round_symbols']['symbols'])
            if run_kind == 'xattr':
                require(row['identity']['source_identity'] == sha(
                    json.dumps(run['source_sha256'], sort_keys=True).encode()),
                    label + ': xattr source identity is not its captured manifest')
                for field, filename in (('kernel_identity', 'kernel-identity.json'),
                                        ('topology_identity', 'topology.txt')):
                    require(row['identity'][field] == run['input_sha256'][filename],
                            label + ': xattr ' + field + ' differs from capture receipt')
            require(all(finite(row[field], positive=True) for field in METRICS[:3]),
                    label + ': invalid measured rate or CPU cost')
            require(type(row['completed']) is int and row['completed'] > 0 and
                    type(row['min_worker_completed']) is int and
                    0 < row['min_worker_completed'] <= row['completed'],
                    label + ': invalid progress receipt')
            entries, completions = row['jit_entries'], row['jit_completions']
            require(type(entries) is int and type(completions) is int and
                    0 <= completions <= entries and completions <= row['completed'],
                    label + ': inconsistent JIT counters')
            require(equal_number(row['jit_complete_share'], completions / row['completed']),
                    label + ': inconsistent returned-body share')
            expected_status = ('PASS' if completions else 'PARTIAL_JIT' if entries else 'NO_JIT')
            if row['arm'] != 'kdlock':
                expected_status = 'NATIVE' if run_kind == 'taskname' else 'NOT_APPLICABLE'
                require(entries == completions == 0 and row['address_guard_exits'] is None,
                        label + ': KD counters applied to a control')
            else:
                require(type(row['address_guard_exits']) is int and
                        row['address_guard_exits'] >= 0, label + ': missing guard count')
            require(row['jit_status'] == expected_status, label + ': inconsistent execution status')
            require(row['tclock_delegation'] ==
                    ('UNMEASURED' if row['arm'] == 'tclock' else 'NOT_APPLICABLE'),
                    label + ': unexpected TCLock evidence')
            cohorts[cohort_key(row)].append(row)
        saved = {cohort_key(row): row for row in run['groups']}
        require(len(saved) == len(run['groups']) and saved.keys() == cohorts.keys(),
                label + ': summary groups differ from session receipts')
        for key, samples in cohorts.items():
            group = saved[key]
            require(group['run'] == run_kind and group['source_id'] == run['source_id'] and
                    group['valid_rounds'] == len(samples) and
                    group['complete'] is (len(samples) == 3) and
                    sorted(group['samples']) == sorted(row['name'] for row in samples),
                    label + ': wrong cohort membership or repetition count')
            calculated = dict(group)
            for metric in METRICS:
                values = [row[metric] for row in samples]
                for suffix, value in (('min', min(values)),
                                      ('median', statistics.median(values)),
                                      ('max', max(values))):
                    field = metric + '_' + suffix
                    require(equal_number(group[field], value), label + ': changed ' + field)
                    calculated[field] = value
            for metric in COUNTERS:
                values = [row[metric] for row in samples]
                value = sum(values) if all(v is not None for v in values) else None
                require(group[metric + '_total'] == value, label + ': changed ' + metric)
            all_groups[key] = calculated
        counts = dict(Counter(row['jit_status'] for row in sessions if row['arm'] == 'kdlock'))
        require(run['kd_status_counts'] == counts, label + ': wrong status totals')
        summary[run_kind] = dict(sessions=len(sessions), groups=len(cohorts),
                                 kd_status_counts=counts, source_id=run['source_id'])
        if label == 'new':
            summary[run_kind]['measured_direct_images'] = sum(row['arm'] == 'kdlock' for row in sessions)
            summary[run_kind]['required_image_bits'] = 24 if run_kind == 'taskname' else 20
    return all_groups, summary


def differences(left, right):
    return {key: dict(old=left.get(key, MISSING), new=right.get(key, MISSING))
            for key in sorted(left.keys() | right.keys())
            if left.get(key, MISSING) != right.get(key, MISSING)}


def source_audit(old, new, policy):
    audits = {}
    for run_kind in ('taskname', 'xattr'):
        before, after = (r['runs'][run_kind]['source_sha256'] for r in (old, new))
        known = policy['sources'][run_kind]
        require(len(before) == known['old_files'] and
                sha(canonical(before).encode()) == known['old_source_id'],
                run_kind + ': wrong baseline source manifest')
        expected = dict(before)
        for path, change in known['changes'].items():
            require(expected.get(path) == change['old'], 'policy old hash mismatch: ' + path)
            if change['new'] is None:
                expected.pop(path)
            else:
                expected[path] = change['new']
        require(len(expected) == known['new_files'] and
                sha(canonical(expected).encode()) == known['new_source_id'],
                run_kind + ': internally inconsistent source policy')
        mismatch = differences(expected, after)
        audits[run_kind] = dict(matches_pinned_revision=not mismatch,
            expected_new_source_id=known['new_source_id'], unexpected=mismatch,
            intentional_changes=known['changes'])
    return audits


def environment_audit(before, after, run_kind):
    """Only output locations, interpreter location and recovery tags may differ."""
    left, right = json.loads(canonical(before)), json.loads(canonical(after))
    allowed = {}
    if run_kind == 'taskname':
        for value in (left, right):
            argv = value.get('argv', [])
            require(argv.count('--output') == 1 and argv.index('--output') + 1 < len(argv),
                    'taskname: missing or ambiguous runner output argument')
        index_old, index_new = left['argv'].index('--output') + 1, right['argv'].index('--output') + 1
        output_old, output_new = left['argv'][index_old], right['argv'][index_new]
        if output_old != output_new:
            allowed['argv.--output'] = dict(old=output_old, new=output_new)
        left['argv'][index_old] = right['argv'][index_new] = '<output-directory>'
        fields = ('python', 'snapshot_tag')
    else:
        old_args, new_args = left.get('arguments', {}), right.get('arguments', {})
        require('output' in old_args and 'output' in new_args, 'xattr: missing output path')
        if old_args['output'] != new_args['output']:
            allowed['arguments.output'] = dict(old=old_args['output'], new=new_args['output'])
        old_args['output'] = new_args['output'] = '<output-directory>'
        fields = ('snapshot',)
    for field in fields:
        require(field in left and field in right and left[field] and right[field],
                run_kind + ': missing environment field ' + field)
        if left[field] != right[field]:
            allowed[field] = dict(old=left[field], new=right[field])
        left.pop(field)
        right.pop(field)
    unexpected = differences(left, right)
    return dict(compatible=not unexpected, allowed_differences=allowed,
                incompatible_differences=unexpected)


def select(groups, case, workers, arm):
    found = [row for key, row in groups.items() if key[:3] == (case, workers, arm)]
    selected = found[0] if len(found) == 1 and found[0]['complete'] else None
    statuses = [dict(status=row['jit_status'], valid_rounds=row['valid_rounds'])
                for row in sorted(found, key=lambda row: (row['jit_status'], canonical(row['identity'])))]
    return selected, statuses


def current_rows(groups):
    rows = []
    for case in CASES:
        for workers in GRID:
            row, selected = dict(case=case, threads=workers), {}
            for arm in ARMS:
                group, statuses = select(groups, case, workers, arm)
                selected[arm] = group
                row[arm + '_groups'] = statuses
                for metric in METRICS:
                    for suffix in ('min', 'median', 'max'):
                        field = metric + '_' + suffix
                        row[arm + '_' + field] = group[field] if group else None
                row[arm + '_address_guard_exits_total'] = (
                    group['address_guard_exits_total'] if group else None)
            for arm in ('native', 'tclock'):
                kd, control = selected['kdlock'], selected[arm]
                mismatch = ({field: dict(kd=kd['identity'].get(field, MISSING),
                                         control=control['identity'].get(field, MISSING))
                             for field in CONTROL_FIELDS[kind(case)]
                             if kd['identity'].get(field, MISSING) !=
                             control['identity'].get(field, MISSING)} if kd and control else {})
                reason = ('requires one complete three-repetition cohort per backend'
                          if not kd or not control else 'different comparison settings'
                          if mismatch else '')
                row['kd_' + arm + '_exclusion'] = reason
                row['kd_' + arm + '_identity_differences'] = mismatch
                for metric in ('whole', 'peak'):
                    field = metric + '_ops_s_median'
                    row['kd_' + arm + '_' + metric + '_ratio'] = (
                        kd[field] / control[field] if not reason else None)
            rows.append(row)
    return rows


def historical_rows(old_groups, new_groups, source_checks, environment_checks, policy):
    rows = []
    for case in CASES:
        for workers in GRID:
            row = dict(case=case, threads=workers, old_commit=policy['old_commit'],
                       new_commit=policy['new_commit'])
            old, old_statuses = select(old_groups, case, workers, 'kdlock')
            new, new_statuses = select(new_groups, case, workers, 'kdlock')
            row.update(old_groups=old_statuses, new_groups=new_statuses)
            reasons, mismatch, intentional = [], {}, {}
            if not old or not new:
                reasons.append('requires one complete three-repetition KD cohort per version')
            else:
                if old['jit_status'] != new['jit_status']:
                    reasons.append('execution statuses differ')
                mismatch = differences(old['identity'], new['identity'])
                for field in policy['identity_allowed_differences'][kind(case)]:
                    if field in mismatch:
                        intentional[field] = mismatch.pop(field)
                if mismatch:
                    reasons.append('group identity differs beyond the source revision')
            if not source_checks[kind(case)]['matches_pinned_revision']:
                reasons.append('new source snapshot differs from pinned revision')
            if not environment_checks[kind(case)]['compatible']:
                reasons.append('recorded environment differs beyond allowed capture locations')
            row.update(eligible=not reasons, exclusion_reasons=reasons,
                       incompatible_identity_differences=mismatch,
                       intentional_identity_differences=intentional)
            for prefix, group in (('old', old), ('new', new)):
                groups = old_groups if prefix == 'old' else new_groups
                row[prefix + '_source_id'] = next(
                    value['source_id'] for key, value in groups.items() if key[0] == case)
                for metric in METRICS:
                    for suffix in ('min', 'median', 'max'):
                        field = metric + '_' + suffix
                        row[prefix + '_' + field] = group[field] if group else None
                row[prefix + '_address_guard_exits_total'] = (
                    group['address_guard_exits_total'] if group else None)
            for metric in ('whole', 'peak'):
                field = metric + '_ops_s_median'
                row['new_old_' + metric + '_ratio'] = new[field] / old[field] if not reasons else None
            rows.append(row)
    return rows


def status_text(groups):
    return ', '.join(str(group['status']) + ' ' + str(group['valid_rounds']) + '/3'
                     for group in groups) or 'Missing'


def display(value, divisor=1, suffix='', digits=3):
    return '—' if value is None else f'{value / divisor:.{digits}f}' + suffix


def current_table(rows, metric, *, summary=False):
    first = 'Workload' if summary else 'Workers'
    lines = [f'| {first} | Native | TCLock | KD | KD / Native | KD / TCLock | KD status | KD returned share |',
             '| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |']
    for row in rows:
        first_value = LABELS[row['case']] if summary else str(row['threads'])
        cells = [first_value]
        cells += [display(row[arm + '_' + metric + '_ops_s_median'], 1e6) for arm in ARMS]
        cells += [display(row['kd_' + arm + '_' + metric + '_ratio'], suffix='×')
                  for arm in ('native', 'tclock')]
        cells += [status_text(row['kdlock_groups']),
                  display(row['kdlock_jit_complete_share_median'], .01, '%', 2)]
        lines.append('| ' + ' | '.join(cells) + ' |')
    return lines


def historical_table(rows, metric, policy, *, summary=False):
    first = 'Workload' if summary else 'Workers'
    lines = [f'| {first} | {policy["old_commit"][:7]} KD | {policy["new_commit"][:7]} KD | New / old | Old status | New status | Old returned share | New returned share | Eligible |',
             '| --- | ---: | ---: | ---: | --- | --- | ---: | ---: | --- |']
    for row in rows:
        first_value = LABELS[row['case']] if summary else str(row['threads'])
        cells = [first_value]
        cells += [display(row[prefix + '_' + metric + '_ops_s_median'], 1e6)
                  for prefix in ('old', 'new')]
        cells += [display(row['new_old_' + metric + '_ratio'], suffix='×')]
        cells += [status_text(row[prefix + '_groups']) for prefix in ('old', 'new')]
        cells += [display(row[prefix + '_jit_complete_share_median'], .01, '%', 2)
                  for prefix in ('old', 'new')]
        cells += ['Yes' if row['eligible'] else 'No']
        lines.append('| ' + ' | '.join(cells) + ' |')
    return lines


def tables(current, history, policy, *, pinned_revision):
    lines = ['# Replayed taskname and xattr tables', '',
        'Expected current source: `' + policy['new_commit'] + '`. Historical source: `' + policy['old_commit'] + '`.', '',
        ('Both source manifests match their pinned revisions.' if pinned_revision else
         '**Source verification failed. These current results cannot be attributed to the pinned revision; '
         'historical ratios for the affected run are suppressed. Read comparison-audit.json.**'), '',
        'All rates are three-repetition medians in millions of operations per second (Mops/s). '
        'Ratios use unrounded medians. Whole-run and peak rates are separate. Returned share '
        'is the median fraction of measured operations completed by generated bodies.', '',
        '`PASS` records at least one completed generated body; it does not imply high delegation '
        'coverage. `NO_JIT` records no generated entry. `PARTIAL_JIT` records entries without '
        'completed bodies. A published `NORMAL` image is not completion evidence. '
        'These counters do not classify TCLock delegation.', '',
        'A dash means there is no compatible, complete three-repetition comparison. Mixed statuses '
        'remain separate. Historical ratios require matching statuses and settings; matching '
        '`NO_JIT` rows describe local locking, while `PARTIAL_JIT` is not returned-body acceptance. '
        'See historical-kd-full-grid.csv and comparison-audit.json for every exclusion.', '',
        'Fresh Native and TCLock measurements are the only denominators in current comparisons. '
        'Historical samples are never pooled into current groups. Source and environment '
        'differences remain recorded; these tables compare the full source revisions and do not '
        'isolate the cost of an individual helper dispatch or counter update. Neither revision '
        'performs the removed helper-specific code or argument checks.', '']
    for metric, label in (('whole', 'Whole-run'), ('peak', 'Peak')):
        lines += ['## ' + label + ' throughput at 60 workers', '']
        lines += current_table([row for row in current if row['threads'] == 60], metric, summary=True) + ['']
        for case in CASES:
            lines += ['## ' + LABELS[case] + ': ' + label.lower() + ' full grid', '']
            lines += current_table([row for row in current if row['case'] == case], metric) + ['']
        lines += ['## Historical KD comparison: ' + label.lower() + ', 60 workers', '']
        lines += historical_table([row for row in history if row['threads'] == 60], metric, policy, summary=True) + ['']
        for case in CASES:
            lines += ['## Historical KD: ' + LABELS[case] + ', ' + label.lower() + ' full grid', '']
            lines += historical_table([row for row in history if row['case'] == case], metric, policy) + ['']
    return '\n'.join(lines)


def write_csv(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows({key: canonical(value) if isinstance(value, (dict, list)) else value
                         for key, value in row.items()} for row in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('old_replay', type=Path)
    parser.add_argument('new_replay', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    require(not args.output.exists(), 'use a new output directory')
    policy, policy_hash = read_json(Path(__file__).with_name('comparison-policy.json'))
    validate_policy(policy)
    old, old_hash = read_json(args.old_replay)
    new, new_hash = read_json(args.new_replay)
    require(old_hash == policy['old_replay_sha256'],
            'baseline replay differs from the pinned original-API 88 receipt')
    require(old_hash != new_hash, 'the two inputs are the same replay')
    symbol_record = new['round_symbols']
    require(symbol_record['sha256'] == policy['new_round_symbols_sha256'] and
            symbol_record['receipt']['schema'] == 1 and
            symbol_record['receipt']['symbols'] == symbol_record['symbols'] and
            set(symbol_record['symbols']) == {'strcmp', 'strscpy_pad'} and
            symbol_record['receipt']['kallsyms_sha256'] == symbol_record['kallsyms_sha256'] and
            symbol_record['receipt']['kallsyms_path'] == symbol_record['kallsyms_path'],
            'new replay round-symbol capture differs from the pinned receipt')
    for label, replay in (('old', old), ('new', new)):
        program = policy['replay_programs'][label]
        require(replay['script_sha256'] == program['script_sha256'],
                label + ': raw-evidence replay program differs from its pinned version')
        require(replay['dependency_sha256'] == {**policy['analysis_dependencies'],
                                               **program['additional_dependency_sha256']},
                label + ': evidence analysis dependency versions differ')
    old_groups, old_summary = validate_replay(old, 'old')
    new_groups, new_summary = validate_replay(new, 'new')
    source_checks = source_audit(old, new, policy)
    environment_checks = {run_kind: environment_audit(old['runs'][run_kind]['environment'],
        new['runs'][run_kind]['environment'], run_kind) for run_kind in ('taskname', 'xattr')}
    current = current_rows(new_groups)
    history = historical_rows(old_groups, new_groups, source_checks, environment_checks, policy)
    pinned_revision = all(check['matches_pinned_revision'] for check in source_checks.values())
    environment_match = all(check['compatible'] for check in environment_checks.values())
    # Version 2 records two replay programs and loaded-image/symbol evidence;
    # the old schema used one shared raw_replay_script_sha256 string.
    audit = dict(schema=2, old_commit=policy['old_commit'], new_commit=policy['new_commit'],
        scope='Postprocessing of completed raw-evidence replays; not a new correctness test.',
        old_replay=dict(path=str(args.old_replay.resolve()), sha256=old_hash, summary=old_summary),
        new_replay=dict(path=str(args.new_replay.resolve()), sha256=new_hash, summary=new_summary),
        script_sha256=sha(Path(__file__).read_bytes()), policy_sha256=policy_hash,
        raw_replay_script_sha256={label: replay['script_sha256']
                                  for label, replay in (('old', old), ('new', new))},
        replay_programs=policy['replay_programs'],
        new_round_symbols=symbol_record,
        source_checks=source_checks, environment_checks=environment_checks,
        pinned_revision_matches=pinned_revision, historical_environment_compatible=environment_match,
        historical_eligible_points=sum(row['eligible'] for row in history),
        historical_excluded_points=sum(not row['eligible'] for row in history),
        current_points=len(current), analysis_dependencies=policy['analysis_dependencies'],
        limits=['No historical/control pooling; ratios are ratios of medians.',
                'Loaded-image requirements, relocation addresses and hashes are evidence, not timing identity exceptions.',
                'New schema-2 and old schema-1 replay programs are separately pinned; the four measurement validators are identical.',
                'TCLock delegation is unmeasured by these KD counters.',
                'Matching frequency policy does not establish matching effective frequency or host load.',
                'Host-placement/frequency and final kernel-log/drain audits remain separate receipts.',
                'Unexpected source/environment differences suppress historical ratios; inspect their details.',
                'Input raw replay validates recorded evidence; this script verifies receipt consistency only.'])
    args.output.mkdir(parents=True)
    for stem, rows in (('current', current), ('historical-kd', history)):
        write_csv(args.output / (stem + '-full-grid.csv'), rows)
        write_csv(args.output / (stem + '-60-workers.csv'), [row for row in rows if row['threads'] == 60])
    (args.output / 'tables.md').write_text(
        tables(current, history, policy, pinned_revision=pinned_revision) + '\n')
    (args.output / 'comparison-audit.json').write_text(
        json.dumps(audit, sort_keys=True, indent=2, allow_nan=False) + '\n')
    print(json.dumps({key: audit[key] for key in ('pinned_revision_matches',
        'historical_environment_compatible', 'current_points', 'historical_eligible_points',
        'historical_excluded_points')}, indent=2))
    return 0 if pinned_revision and environment_match else 1


if __name__ == '__main__':
    raise SystemExit(main())
