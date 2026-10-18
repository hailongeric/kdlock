#!/usr/bin/env python3
"""Independent offline arithmetic/record replay; imports no project programs.

Usage: independent-replay.py RUN_MAP.json NEW_OUTPUT.json
       [--compare path/to/analysis.json] [--require-final]
Reads raw plans/records/source/environment only. Saved runner summaries and the
main analyzer are never used to compute rates, progress, JIT groups or ratios.
--compare checks the separately computed results after replay. No figures,
tests, benchmarks, VM commands or source execution occur.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import tarfile


COUNTS = [*range(1, 9), *range(12, 61, 4)]
CASES = [('cacheline', 1, 'c01'), ('cacheline', 8, 'c08'), ('rcuht', 0, 'RCUHT')]
LABELS = {(workload, lines): label for workload, lines, label in CASES}
INPUTS = ('plan.json', 'records.json', 'source-sha256.json', 'environment.json')
IDENTITY = ('lock_kind', 'duration_ms', 'peak_window_ms', 'peak_settle_ms', 'sample_ms',
            'post_work_rounds', 'collector_cpu', 'provider_ubsan', 'warmup_iterations_per_worker',
            'mix_policy', 'cpus', 'cpu_nodes', 'caller_abi', 'entry_abi', 'delegate',
            'rwsem_writer_shell', 'numa_policy', 'delegation_batch_limit', 'spin_entry_ratio_limit')


def hashed(data):
    return hashlib.sha256(data).hexdigest()


def read_inputs(path):
    blobs = {}
    if path.is_dir():
        for name in INPUTS:
            item = path / name
            if item.is_file():
                blobs[name] = item.read_bytes()
    elif path.is_file():
        candidates = defaultdict(list)
        with tarfile.open(path, 'r|gz') as archive:
            for member in archive:
                name = PurePosixPath(member.name)
                if name.is_absolute() or '..' in name.parts:
                    raise ValueError('unsafe archive member: ' + member.name)
                if member.isfile() and name.name in INPUTS:
                    if member.size > 128 << 20:
                        raise ValueError('oversized receipt: ' + member.name)
                    candidates[name.name].append((len(name.parts), archive.extractfile(member).read()))
        for name, values in candidates.items():
            minimum = min(depth for depth, _ in values)
            selected = [value for depth, value in values if depth == minimum]
            if len(selected) != 1:
                raise ValueError('ambiguous archive receipt: ' + name)
            blobs[name] = selected[0]
    return ({name: json.loads(value) for name, value in blobs.items()},
            {name: hashed(value) for name, value in blobs.items()})


def median(values):
    values = sorted(values)
    length = len(values)
    return values[length // 2] if length % 2 else (values[length // 2 - 1] + values[length // 2]) / 2


class Audit:
    def __init__(self):
        self.counts = Counter()
        self.failures = []

    def check(self, condition, label, context=''):
        self.counts[label] += 1
        if not condition:
            self.failures.append(dict(check=label, context=context))
        return bool(condition)

    def equal(self, actual, expected, label, context=''):
        okay = (math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-7)
                if isinstance(actual, (int, float)) and isinstance(expected, (int, float)) and
                   (isinstance(actual, float) or isinstance(expected, float))
                else actual == expected)
        return self.check(okay, label, context)


def checksum(completed, rounds):
    # Independent affine-power recurrence for the fixed post-work checksum.
    state, steps, factor, offset, mask = 1, completed * rounds, 1664525, 1013904223, (1 << 64) - 1
    while steps:
        if steps % 2:
            state = (factor * state + offset) & mask
        offset = (factor * offset + offset) & mask
        factor = (factor * factor) & mask
        steps //= 2
    return state


def replay_peak(measured, spec, audit, context):
    earliest = max(worker['active_started_ns'] for worker in measured['workers']) + measured['peak_settle_ns']
    latest = min(measured['deadline_ns'], *(worker['kernel_finished_ns'] for worker in measured['workers']))
    eligible = [(index, sample) for index, sample in enumerate(measured['samples'])
                if sample['started_ns'] >= earliest and sample['finished_ns'] <= latest]
    best, windows = None, 0
    # Find the first sufficiently long endpoint for each eligible start. This
    # independent scan reconstructs the conservative timestamp-bracket peak.
    for position, (start_index, start) in enumerate(eligible):
        endpoint = next(((index, sample) for index, sample in eligible[position + 1:]
                         if sample['finished_ns'] - start['started_ns'] >= measured['peak_window_ns']), None)
        if endpoint is None:
            continue
        end_index, end = endpoint
        windows += 1
        changes = [last - first for first, last in zip(start['completed'], end['completed'])]
        if len(changes) != spec['threads'] or min(changes) <= 0:
            continue
        operations, elapsed = sum(changes), end['finished_ns'] - start['started_ns']
        if best is None or operations * best['elapsed_ns'] > best['completed'] * elapsed:
            writes = sum((((17 * worker) % 100 + last * spec['write_percent']) // 100 -
                          ((17 * worker) % 100 + first * spec['write_percent']) // 100)
                         for worker, (first, last) in enumerate(zip(start['completed'], end['completed'])))
            best = dict(start_sample_index=start_index, end_sample_index=end_index, elapsed_ns=elapsed,
                        completed=operations, worker_completed=changes, writes=writes, reads=operations - writes)
    if not audit.check(best is not None, 'eligible full-cohort peak', context):
        return None
    best.update(candidate_windows=windows, eligible_samples=len(eligible))
    for key, value in best.items():
        audit.equal(measured['peak'][key], value, 'raw peak ' + key, context)
    rate = best['completed'] * 1e9 / best['elapsed_ns']
    audit.equal(measured['peak']['throughput_ops_s'], rate, 'raw peak throughput', context)
    return rate


def expected_configuration(name):
    cases = CASES if name.endswith('-grid') or name == 'final-reference' else CASES[:1]
    counts = COUNTS if name.endswith('-grid') else [1, 8, 32, 36, 60] if name == 'final-reference' else [1, 8, 32, 60]
    arms = ('native', 'tclock', 'kdlock') if name == 'final-reference' else ('native', 'kdlock')
    return {(workload, lines, percent, workers, arm, repeat) for workload, lines, _ in cases
            for percent in (1, 20) for workers in counts for arm in arms for repeat in range(3)}


def replay_run(name, path, audit):
    first_failure = len(audit.failures)
    objects, hashes = read_inputs(path)
    missing = [filename for filename in INPUTS if filename not in objects]
    if missing:
        audit.check(False, 'required input receipts', name + ': ' + ', '.join(missing))
        return dict(status='MISSING_EVIDENCE', path=str(path), missing=missing, input_sha256=hashes, groups=[])
    plan, records = objects['plan.json'], objects['records.json']
    wanted = expected_configuration(name)
    actual = {(row['workload'], row['cachelines'], row['write_percent'], row['threads'], row['arm'], row['repeat'])
              for row in plan}
    audit.check(actual == wanted and len(plan) == len(wanted), 'exact requested matrix', name)
    planned = {row['name']: row for row in plan}
    recorded = {row['name']: row for row in records}
    audit.check(len(planned) == len(plan) and len(recorded) == len(records), 'unique session identities', name)
    audit.equal(list(recorded), list(planned), 'plan and record order', name)
    totals, per_arm, jit_sessions, dispositions = Counter(), Counter(), Counter(), Counter()
    group_members, observed_sessions = defaultdict(list), []
    valid_count = 0
    for spec in plan:
        row = recorded.get(spec['name'], {})
        context = name + '/' + spec['name']
        dispositions[row.get('execution_status', 'NOT_RUN')] += 1
        audit.check(all(row.get(key) == value for key, value in spec.items()), 'record matches frozen plan', context)
        measured = row.get('measurement', {})
        complete = (row.get('execution_status') == 'OK' and row.get('drained') is True and
                    measured.get('complete') is True and measured.get('data_ok') is True and
                    row.get('functional') is False and not row.get('diagnostic') and
                    row.get('score_eligible') is not False)
        audit.check(complete, 'successful unprofiled drained session', context)
        if not complete:
            continue
        valid_count += 1
        per_arm[row['arm']] += 1
        jit_sessions[row['arm'] + ':' + row['jit_status']] += 1
        workers = measured['workers']
        audit.equal(len(workers), row['threads'], 'worker cohort count', context)
        audit.equal(measured['wall_ns'], measured['finished_ns'] - measured['started_ns'], 'whole interval', context)
        audit.check(measured['wall_ns'] > 0, 'positive interval', context)
        for index, worker in enumerate(workers):
            audit.check(worker['completed'] > 0 and worker['completed'] % 256 == 0 and
                        not worker.get('error') and worker['read_errors'] == 0 and worker['cpu_ns'] > 0,
                        'worker progress/errors/cpu time', context)
            audit.equal(worker['completed'], worker['reads'] + worker['writes'], 'worker total', context)
            audit.equal(worker['writes'], ((17 * index) % 100 + worker['completed'] * row['write_percent']) // 100,
                        'deterministic operation mix', context)
            audit.check(worker['cpu'] == worker['observed_cpu'] == row['cpus'][index], 'worker CPU affinity', context)
            audit.equal(worker['checksum'], checksum(worker['completed'], row['post_work_rounds']), 'post-work checksum', context)
            audit.check(measured['started_ns'] <= worker['active_started_ns'] <= worker['kernel_finished_ns'] <=
                        worker['finished_ns'] <= measured['finished_ns'], 'worker time ordering', context)
        for key in ('completed', 'reads', 'writes'):
            audit.equal(measured[key], sum(worker[key] for worker in workers), 'aggregate ' + key, context)
            totals[key] += measured[key]
        previous = [0] * row['threads']
        for sample in measured['samples']:
            audit.check(len(sample['completed']) == row['threads'] and
                        all(old <= current <= worker['completed'] for old, current, worker in
                            zip(previous, sample['completed'], workers)) and
                        sample['started_ns'] <= sample['finished_ns'],
                        'monotonic recorded sample progress', context)
            previous = sample['completed']
        before, after = measured['before'], measured['after']
        for state in (before, after):
            audit.check(all(state[key] == 0 for key in ('active', 'cnts', 'gate')), 'payload drain', context)
        audit.check(all(before[key] == after[key] for key in before if key != 'values'), 'payload identity stable', context)
        delta = [last - first for first, last in zip(before['values'], after['values'])]
        if row['workload'] == 'cacheline':
            audit.equal(delta, [measured['writes']] * row['cachelines'] + [0] * (16 - row['cachelines']),
                        'cacheline protected effects', context)
            audit.check(all(worker['read_hits'] == 0 for worker in workers), 'cacheline read result', context)
        else:
            audit.check(delta[0] == measured['writes'] == sum(delta[1:4]) and all(value >= 0 for value in delta[:4])
                        and before['values'][4:] == after['values'][4:] == [0] * 12,
                        'RCUHT protected effects', context)
        entries, completions = row['jit_bodies'], row['jit_completions']
        audit.equal(entries, row['jit_after'] - row['jit_before'], 'JIT entry delta', context)
        audit.equal(completions, row['jit_complete_after'] - row['jit_complete_before'], 'JIT completion delta', context)
        audit.check(0 <= completions <= entries <= measured['writes'], 'JIT bounds', context)
        disposition = ('PASS' if completions else 'PARTIAL_JIT' if entries else 'NO_JIT') if row['arm'] == 'kdlock' else 'NATIVE'
        audit.equal(row['jit_status'], disposition, 'JIT status from returned-body evidence', context)
        if row['arm'] != 'kdlock':
            audit.check(entries == completions == 0, 'no JIT in comparison control', context)
            if row['arm'] == 'tclock':
                audit.equal(row.get('tclock_delegation_status'), 'UNMEASURED', 'TCLock delegation remains unmeasured', context)
        else:
            published = row.get('published_before')
            audit.check(published is not None and published == row.get('published_after') and
                        published['source']['writers'] == published['source']['frames'] == published['source']['state'] == 0,
                        'stable unleased publication boundary', context)
        totals['jit_entries'] += entries
        totals['jit_completions'] += completions
        whole = measured['completed'] * 1e9 / measured['wall_ns']
        peak = replay_peak(measured, row, audit, context)
        if peak is None:
            continue
        cpu = sum(worker['cpu_ns'] for worker in workers) / measured['completed']
        member = dict(name=row['name'], whole=whole, peak=peak, cpu=cpu, entries=entries, completions=completions,
                      tclock_delegation_status=row.get('tclock_delegation_status', 'NOT_APPLICABLE'),
                      identity={key: row.get(key) for key in IDENTITY})
        key = (row['workload'], row['cachelines'], row['write_percent'], row['threads'],
               row['arm'], row['variant'], row['jit_status'])
        group_members[key].append(member)
        observed_sessions.append(dict(name=row['name'], arm=row['arm'], jit_status=row['jit_status'],
            tclock_delegation_status=row.get('tclock_delegation_status', 'NOT_APPLICABLE'),
            completed=measured['completed'], min_worker_completed=min(worker['completed'] for worker in workers),
            jit_entries=entries, jit_completions=completions, whole_ops_s=whole, peak_ops_s=peak,
            worker_cpu_ns_per_op=cpu))
    groups = []
    for key, members in sorted(group_members.items()):
        whole, peaks, cpu = ([member[field] for member in members] for field in ('whole', 'peak', 'cpu'))
        audit.check(all(member['identity'] == members[0]['identity'] for member in members), 'homogeneous group identity', name)
        groups.append(dict(workload=key[0], cachelines=key[1], write_percent=key[2], threads=key[3],
            arm=key[4], variant=key[5], jit_status=key[6], valid_rounds=len(members), complete=len(members) == 3,
            tclock_delegation_status=members[0]['tclock_delegation_status'],
            whole_min_ops_s=min(whole), whole_median_ops_s=median(whole), whole_max_ops_s=max(whole),
            best_peak_ops_s=max(peaks), peak_min_ops_s=min(peaks), peak_median_ops_s=median(peaks), peak_max_ops_s=max(peaks),
            worker_cpu_ns_per_op_min=min(cpu), worker_cpu_ns_per_op_median=median(cpu), worker_cpu_ns_per_op_max=max(cpu),
            jit_entries_min=min(member['entries'] for member in members), jit_entries_max=max(member['entries'] for member in members),
            jit_completions_min=min(member['completions'] for member in members),
            jit_completions_max=max(member['completions'] for member in members),
            samples=[member['name'] for member in members], identity=members[0]['identity']))
    canonical = json.dumps(objects['source-sha256.json'], sort_keys=True, separators=(',', ':'), allow_nan=False)
    return dict(status='COMPLETE' if len(audit.failures) == first_failure and valid_count == len(wanted) else 'FAILED_REPLAY',
        path=str(path), input_sha256=hashes, source_id=hashed(canonical.encode()),
        planned_sessions=len(plan), recorded_sessions=len(records), valid_sessions=valid_count, expected_sessions=len(wanted),
        per_arm=dict(per_arm), kd_jit_status_counts={key.partition(':')[2]: value for key, value in jit_sessions.items() if key.startswith('kdlock:')},
        jit_session_counts=dict(jit_sessions), execution_status_counts=dict(dispositions), totals=dict(totals),
        all_sessions_drained=all(row.get('drained') is True for row in records),
        environment=objects['environment.json'], groups=groups, sessions=observed_sessions)


def selected(run, key, arm):
    values = [group for group in run.get('groups', []) if
              (group['workload'], group['cachelines'], group['write_percent'], group['threads']) == key and group['arm'] == arm]
    return (values[0] if len(values) == 1 and values[0]['valid_rounds'] == 3 else None), values


def compatible(left_run, right_run, left, right):
    if left is None or right is None or left['identity'] != right['identity']:
        return False
    a, b = left_run['environment'], right_run['environment']
    if any(a.get(key) != b.get(key) for key in ('cmdline', 'preemption')):
        return False
    if any(a['kernel_identity'].get(key) != b['kernel_identity'].get(key) for key in ('running_build_id', 'config')):
        return False
    if any(a['topology'].get(key) != b['topology'].get(key) for key in ('online_cpus', 'allowed_cpus')):
        return False
    nodes_a = dict(zip(a['topology']['role_cpus'], a['topology']['role_nodes']))
    nodes_b = dict(zip(b['topology']['role_cpus'], b['topology']['role_nodes']))
    return all(cpu in nodes_a and cpu in nodes_b and nodes_a[cpu] == nodes_b[cpu]
               for cpu in [*left['identity']['cpus'], left['identity']['collector_cpu']])


def points_for(run):
    names = {(group['workload'], group['cachelines'], group['write_percent'], group['threads']) for group in run.get('groups', [])}
    points = []
    for key in sorted(names):
        native, ngroups = selected(run, key, 'native')
        kd, kgroups = selected(run, key, 'kdlock')
        tc, tgroups = selected(run, key, 'tclock')
        point = dict(workload=LABELS[key[:2]], write_percent=key[2], threads=key[3],
            native_groups=[dict(jit_status=row['jit_status'], valid_rounds=row['valid_rounds'],
                                whole_median_ops_s=row['whole_median_ops_s']) for row in ngroups],
            kd_groups=[dict(jit_status=row['jit_status'], valid_rounds=row['valid_rounds'],
                            whole_median_ops_s=row['whole_median_ops_s']) for row in kgroups],
            tclock_groups=[dict(jit_status=row['jit_status'], valid_rounds=row['valid_rounds'],
                                whole_median_ops_s=row['whole_median_ops_s']) for row in tgroups],
            native_whole_ops_s=native['whole_median_ops_s'] if native else None,
            kd_whole_ops_s=kd['whole_median_ops_s'] if kd else None,
            tclock_whole_ops_s=tc['whole_median_ops_s'] if tc else None,
            tclock_native_whole_ratio=tc['whole_median_ops_s'] / native['whole_median_ops_s'] if tc and native else None,
            tclock_native_peak_ratio=tc['best_peak_ops_s'] / native['best_peak_ops_s'] if tc and native else None,
            whole_ratio=kd['whole_median_ops_s'] / native['whole_median_ops_s'] if kd and native else None,
            peak_ratio=kd['best_peak_ops_s'] / native['best_peak_ops_s'] if kd and native else None)
        point['status'] = ('PASS' if min(point['whole_ratio'], point['peak_ratio']) >= 1 else 'FAIL') if kd and native else 'INCOMPLETE'
        point['reason'] = ('SPLIT_EXECUTION_STATUSES' if sum(row['valid_rounds'] for row in kgroups) == 3 and
                           sum(row['valid_rounds'] for row in ngroups) == 3 else 'MISSING_VALID_REPETITIONS') \
            if point['status'] == 'INCOMPLETE' else ''
        points.append(point)
    return points


def sixty_before_after(runs):
    before, after = runs.get('baseline-grid', {}), runs.get('final-grid', {})
    output = []
    for workload, lines, label in CASES:
        for percent in (1, 20):
            key = workload, lines, percent, 60
            item = dict(workload=label, write_percent=percent, threads=60)
            values = {}
            for phase, run in (('before', before), ('after', after)):
                for arm in ('native', 'kdlock'):
                    group, groups = selected(run, key, arm)
                    values[phase, arm] = group
                    item[phase + '_' + arm + '_groups'] = [dict(jit_status=row['jit_status'], valid_rounds=row['valid_rounds'])
                                                          for row in groups]
                    for field in ('whole_min_ops_s', 'whole_median_ops_s', 'whole_max_ops_s', 'best_peak_ops_s',
                                  'worker_cpu_ns_per_op_median', 'jit_completions_min', 'jit_completions_max'):
                        item[phase + '_' + arm + '_' + field] = group[field] if group else None
            for prefix, numerator, denominator, allowed in (
                    ('kd_after_before', values['after', 'kdlock'], values['before', 'kdlock'],
                     compatible(after, before, values['after', 'kdlock'], values['before', 'kdlock'])),
                    ('native_after_before', values['after', 'native'], values['before', 'native'],
                     compatible(after, before, values['after', 'native'], values['before', 'native'])),
                    ('after_kd_native', values['after', 'kdlock'], values['after', 'native'], True)):
                for metric, field in (('whole', 'whole_median_ops_s'), ('peak', 'best_peak_ops_s')):
                    item[prefix + '_' + metric + '_ratio'] = numerator[field] / denominator[field] \
                        if numerator and denominator and allowed else None
            output.append(item)
    return output


def compare_analysis(analysis, runs, audit):
    for name, run in runs.items():
        saved = analysis['runs'].get(name, {})
        for key in ('valid_sessions', 'planned_sessions', 'expected_sessions', 'kd_jit_status_counts',
                    'all_sessions_drained', 'source_id'):
            audit.equal(saved.get(key), run.get(key), 'analysis coverage ' + key, name)
        recorded = {(row['variant'], row['write_percent'], row['threads'], row['jit_status']): row for row in saved.get('groups', [])}
        audit.equal(len(recorded), len(run['groups']), 'analysis group count', name)
        for group in run['groups']:
            key = group['variant'], group['write_percent'], group['threads'], group['jit_status']
            other = recorded.get(key, {})
            for field in ('valid_rounds', 'complete', 'whole_min_ops_s', 'whole_median_ops_s', 'whole_max_ops_s',
                          'best_peak_ops_s', 'peak_min_ops_s', 'peak_median_ops_s', 'peak_max_ops_s',
                          'worker_cpu_ns_per_op_median', 'jit_entries_min', 'jit_entries_max',
                          'jit_completions_min', 'jit_completions_max'):
                audit.equal(other.get(field), group[field], 'analysis group ' + field, name + '/' + repr(key))
            audit.equal(set(other.get('samples', [])), set(group['samples']), 'analysis group membership', name + '/' + repr(key))
            if group['arm'] == 'tclock':
                audit.equal(other.get('tclock_delegation_status'), group['tclock_delegation_status'],
                            'analysis TCLock delegation observation', name + '/' + repr(key))
    before, after = runs.get('baseline-grid', {}), runs.get('final-grid', {})
    for row in analysis['points']:
        payload = next((workload, lines) for workload, lines, label in CASES if label == row['workload'])
        key = *payload, row['write_percent'], row['threads']
        selected_groups = {}
        for phase, run in (('before', before), ('after', after)):
            for arm in ('native', 'kdlock'):
                group, _ = selected(run, key, arm)
                selected_groups[phase, arm] = group
                for field in ('whole_min_ops_s', 'whole_median_ops_s', 'whole_max_ops_s', 'best_peak_ops_s',
                              'worker_cpu_ns_per_op_median', 'jit_completions_min', 'jit_completions_max'):
                    audit.equal(row[phase + '_' + arm + '_' + field], group[field] if group else None,
                                'analysis point ' + field, repr(key) + '/' + phase + '/' + arm)
        comparisons = (
            ('kd_after_before', selected_groups['after', 'kdlock'], selected_groups['before', 'kdlock'],
             compatible(after, before, selected_groups['after', 'kdlock'], selected_groups['before', 'kdlock'])),
            ('native_after_before', selected_groups['after', 'native'], selected_groups['before', 'native'],
             compatible(after, before, selected_groups['after', 'native'], selected_groups['before', 'native'])),
            ('after_kd_native', selected_groups['after', 'kdlock'], selected_groups['after', 'native'], True),
            ('before_kd_native', selected_groups['before', 'kdlock'], selected_groups['before', 'native'], True))
        for prefix, numerator, denominator, allowed in comparisons:
            values = []
            for metric, field in (('whole', 'whole_median_ops_s'), ('peak', 'best_peak_ops_s')):
                value = numerator[field] / denominator[field] if numerator and denominator and allowed else None
                values.append(value)
                audit.equal(row[prefix + '_' + metric + '_ratio'], value, 'analysis point ' + prefix + ' ' + metric, repr(key))
            status = ('PASS' if min(values) >= 1 else 'FAIL') if None not in values else 'INCOMPLETE'
            audit.equal(row[prefix + '_status'], status, 'analysis point ' + prefix + ' status', repr(key))
    reference = runs.get('final-reference', {})
    for row in analysis.get('references', []):
        payload = next((workload, lines) for workload, lines, label in CASES if label == row['workload'])
        key = *payload, row['write_percent'], row['threads']
        cohort = {arm: selected(reference, key, arm)[0] for arm in ('native', 'tclock', 'kdlock')}
        for arm, group in cohort.items():
            for field in ('whole_min_ops_s', 'whole_median_ops_s', 'whole_max_ops_s', 'best_peak_ops_s'):
                audit.equal(row[arm + '_' + field], group[field] if group else None,
                            'rwlock reference ' + arm + ' ' + field, repr(key))
        for prefix, arm in (('tclock_native', 'tclock'), ('kd_native', 'kdlock')):
            values = []
            for metric, field in (('whole', 'whole_median_ops_s'), ('peak', 'best_peak_ops_s')):
                value = cohort[arm][field] / cohort['native'][field] if cohort[arm] and cohort['native'] else None
                values.append(value)
                audit.equal(row[prefix + '_' + metric + '_ratio'], value, 'rwlock reference ' + prefix + ' ' + metric, repr(key))
            status = ('PASS' if min(values) >= 1 else 'FAIL') if None not in values else 'INCOMPLETE'
            audit.equal(row[prefix + '_status'], status, 'rwlock reference ' + prefix + ' status', repr(key))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_map', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--compare', type=Path)
    parser.add_argument('--require-final', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('use a new output receipt')
    mapping = json.loads(args.run_map.read_text())
    paths = {name: (args.run_map.resolve().parent / path).resolve() for name, path in mapping.items()
             if not name.endswith('-profile')}
    audit = Audit()
    if args.require_final:
        audit.check({'baseline-grid', 'final-grid', 'final-reference'} <= paths.keys(), 'required final comparison runs')
    runs = {name: replay_run(name, path, audit) for name, path in paths.items()}
    for name, run in runs.items():
        run['points'] = points_for(run)
        run['point_status_counts'] = dict(Counter(row['status'] for row in run['points']))
        run['point_status_scope'] = 'KD/Native comparison; TCLock/Native ratios are separate in the spinning-rwlock reference'
        run['split_points'] = [row for row in run['points'] if row['reason'] == 'SPLIT_EXECUTION_STATUSES']
        run['sixty_workers'] = [row for row in run['points'] if row['threads'] == 60]
    if args.compare:
        compare_analysis(json.loads(args.compare.read_text()), runs, audit)
    for name, path in paths.items():
        audit.equal(read_inputs(path)[1], runs[name]['input_sha256'], 'frozen input receipts unchanged', name)
    output = dict(schema=1, passed=not audit.failures, checks=dict(audit.counts), failures=audit.failures,
        runs=runs, sixty_worker_before_after=sixty_before_after(runs),
        run_map_sha256=hashed(args.run_map.read_bytes()), replay_script_sha256=hashed(Path(__file__).read_bytes()),
        compared_analysis_sha256=hashed(args.compare.read_bytes()) if args.compare else None,
        source='Independent raw plan/record/sample arithmetic; no repository imports, tests, VM access or figure generation',
        limits=['Historical and fresh baseline runs are independent evidence, never pooled.',
                'Mixed JIT statuses remain separate; no homogeneous three-run median is created from a split point.',
                'Recorded payload effects, checksums and progress are replayed; this is not a fresh lock-correctness test.',
                'Separate spinning-rwlock Native/TCLock/KD groups are never treated as sleeping-rwsem parity.',
                'TCLock jit_status=NATIVE means KD witnesses do not apply; TCLock delegation remains UNMEASURED, not proven local.'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        stream.write(json.dumps(output, indent=2, sort_keys=True, allow_nan=False) + '\n')
    print(json.dumps(dict(passed=output['passed'], failure_count=len(audit.failures),
        runs={name: dict(valid_sessions=run.get('valid_sessions'), totals=run.get('totals'),
                        point_status_counts=run['point_status_counts']) for name, run in runs.items()}), indent=2))
    return 0 if output['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
