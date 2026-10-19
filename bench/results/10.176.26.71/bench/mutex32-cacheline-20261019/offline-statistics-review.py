#!/usr/bin/env python3
"""Independent, read-only arithmetic audit of retained pipe-only packed-round archives.

Run on the source host after collection and archiving finish. Only this newly
authored script executes: retained Python, binaries and modules are data. The
separate archive/source audit checks the broader artifact inventory. This audit
reconstructs all timed windows, phase fractions, whole-session counters, group
statistics and whole-session admission diagnostics without importing either report helper.
"""
import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import tarfile


ARMS = ('packed32', 'candidate', 'old256')
TRIAL_ARMS = ('prefetch',)
FOCUS = {
    'gate_helpers': r'^kd_mutex_gate_(?:read|set|trylock)$',
    'waiter_bookkeeping': r'^kd_mutex_(?:state_waiter_(?:count|enter|exit)|waiter_(?:enter|exit)|count_(?:enter|exit|transition))$',
    'combiner_active': r'^kd_mutex_combiner_active$',
    'outer_retry': r'^kd_mutex_outer_retry$',
    'hint_retry_helpers': r'^kd_mutex_(?:combiner_active|outer_retry)$',
    'mutex_slowpath': r'^__kd_mutex_lock_slowpath$',
    'entry_gate_scope': r'^(?:_kd_mutex_lock_abi|kd_mutex_lock_slowpath|__kd_mutex_lock_slowpath)$',
    'claim_release_scope': r'^(?:_kd_mutex_unlock_checked|kd_mutex_claim_origin|kd_mutex_wait_and_lock|kd_mutex_set_locked)$',
    'combiner_scope': r'^kd_mutex_(?:run_combiner|execute_cs)$',
    'mutex_execute_cs': r'^kd_mutex_execute_cs$',
    'outer_admission': r'^kd_mutex_contended_acquire$',
    'task_reference_scope': r'^kd_mutex_task_(?:get|put|active|reroute)$',
    'physical_lock_unlock': r'^kd_(?:origin_mutex|mutex_local)_(?:lock|unlock)',
}
OFFSET_NAMES = ('gate_helpers', 'waiter_bookkeeping', 'hint_retry_helpers',
                'entry_gate_scope', 'claim_release_scope', 'combiner_scope', 'outer_admission')
FAULT = re.compile(r'BUG:|\bWARNING:|kernel panic|double fault|soft lockup|hard LOCKUP|'
                   r'unable to handle|general protection fault|Oops:|\[ERROR\]|'
                   r'invariant_failures=[1-9]|runtime error:|KASAN:|UBSAN:', re.I)
WANTED = {'records.json', 'session.json', 'source-sha256.json', 'plan.json', 'matrix.json',
          'warmup.json', 'measure.json', 'check-before.json', 'check-after.json',
          'kernel.log', 'comparison.json', 'profile-analysis.json', 'placement-analysis.json',
          'perf-samples.txt', 'perf-report.txt', 'kallsyms', 'tool-sha256.json'}


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def file_hash(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            value.update(block)
    return value.hexdigest()


def unsigned(value):
    return type(value) is int and value >= 0


def same(left, right):
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(same(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right))
    if type(left) in (int, float) and type(right) in (int, float):
        return (left == right if type(left) is type(right) is int else
                math.isfinite(left) and math.isfinite(right) and
                math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-15))
    return type(left) is type(right) and left == right


def stats(values):
    values = sorted(values)
    n = len(values)
    return dict(n=n, min=values[0] if n else None, max=values[-1] if n else None,
                median=(values[(n - 1) // 2] + values[n // 2]) / 2 if n else None)


def symbol_base(symbol):
    return re.sub(r'\.(?:constprop|isra|part)\.\d+$', '', symbol.split('+0x', 1)[0])


def fields(line):
    return {key: int(value) for key, value in re.findall(r'(\w+)=(-?\d+)\b', line)}


class Audit:
    def __init__(self):
        self.checks, self.issues = Counter(), []
        self.raw, self.hashes, self.archives = {}, {}, {}
        self.sessions, self.windows, self.pipe, self.profiles = {}, [], [], []

    def check(self, kind, condition, detail):
        self.checks[kind] += 1
        if not condition:
            self.issues.append(dict(check=kind, detail=detail))
        return bool(condition)

    def equal(self, kind, actual, expected, detail):
        return self.check(kind, same(actual, expected), detail if same(actual, expected) else
                          dict(item=detail, actual=actual, expected=expected))

    def json(self, name):
        return json.loads(self.raw[name])

    def load(self, raw):
        manifest = json.loads((raw / 'archives.json').read_bytes())
        self.equal('archives_complete', manifest.get('completed'), True, 'archives.json')
        prefix = manifest['archive_prefix'] + '/'
        for entry in manifest['groups']:
            relative = PurePosixPath(entry['file'])
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('unsafe archive filename')
            path = raw / entry['file']
            digest, size = file_hash(path), path.stat().st_size
            self.equal('archive_sha256', digest, entry['sha256'], entry['file'])
            self.equal('archive_size', size, entry['bytes'], entry['file'])
            self.archives[entry['file']] = dict(sha256=digest, bytes=size)
            with tarfile.open(path, mode='r|gz') as archive:
                for member in archive:
                    if not member.isfile():
                        continue
                    if not self.check('archive_prefix', member.name.startswith(prefix), member.name):
                        continue
                    name = member.name[len(prefix):]
                    parts = PurePosixPath(name)
                    if not self.check('safe_member', not parts.is_absolute() and '..' not in parts.parts, name):
                        continue
                    if not self.check('unique_member', name not in self.hashes, name):
                        continue
                    keep = ('source' not in parts.parts and 'build' not in parts.parts and
                            (parts.name in WANTED or parts.name.endswith('-command.json')))
                    value, chunks = hashlib.sha256(), []
                    with archive.extractfile(member) as stream:
                        for block in iter(lambda: stream.read(1048576), b''):
                            value.update(block)
                            if keep:
                                chunks.append(block)
                    self.hashes[name] = value.hexdigest()
                    if keep:
                        self.raw[name] = b''.join(chunks)

    def peak(self, record, name):
        m = record['measurement']
        count, wall = m['completed'], m['wall_ns']
        self.check('whole_positive', unsigned(count) and count > 0 and unsigned(wall) and wall > 0, name)
        self.equal('whole_wall', wall, m['finished_ns'] - m['started_ns'], name)
        for field, setting in (('duration_ns', 'duration_ms'), ('peak_window_ns', 'peak_window_ms'),
                               ('peak_settle_ns', 'peak_settle_ms'), ('sample_period_ns', 'sample_ms')):
            self.equal('measurement_setting', m[field], record[setting] * 1000000, [name, field])
        self.check('window_settings', 0 < m['sample_period_ns'] <= m['peak_window_ns'] and
                   m['peak_settle_ns'] + m['peak_window_ns'] < m['duration_ns'], name)
        self.equal('measurement_deadline', m['deadline_ns'], m['started_ns'] + m['duration_ns'], name)
        self.equal('progress_batch', m['progress_batch'], 256, name)
        self.equal('collector_identity', [m['collector_cpu'], m['collector_observed_cpu'], m['collector_error'],
                                         m.get('collector_shared', False)],
                   [record['collector_cpu'], record['collector_cpu'], 0, record.get('collector_shared', False)], name)
        self.check('collector_separate', record['collector_cpu'] not in record['cpus'] and
                   record.get('collector_shared', False) is False, name)
        workers, samples = m['workers'], m['samples']
        self.equal('worker_count', len(workers), record['threads'], name)
        self.equal('worker_cpu_order', [worker['cpu'] for worker in workers], record['cpus'], name)
        self.equal('worker_operation_sum', sum(worker['completed'] for worker in workers), count, name)
        for worker in workers:
            self.check('worker_interval', all(unsigned(worker[key]) for key in
                       ('active_started_ns', 'kernel_finished_ns', 'finished_ns', 'completed')) and
                       m['started_ns'] <= worker['active_started_ns'] < m['deadline_ns'] <=
                       worker['kernel_finished_ns'] <= worker['finished_ns'] <= m['finished_ns'], [name, worker['cpu']])
            self.check('worker_oracle', worker['completed'] > 0 and worker['error'] == 0 and
                       worker['observed_cpu'] == worker['cpu'], [name, worker['cpu']])
        active_start = max(worker['active_started_ns'] for worker in workers)
        active_end = min([m['deadline_ns']] + [worker['kernel_finished_ns'] for worker in workers])
        eligible_start = active_start + m['peak_settle_ns']
        self.check('eligible_interval', active_end - eligible_start >= m['peak_window_ns'], name)
        self.check('sample_count', isinstance(samples, list) and len(samples) >= 2, name)
        previous_end, previous, eligible = m['started_ns'], [0] * len(workers), []
        for index, sample in enumerate(samples):
            begin, end, counts = sample['started_ns'], sample['finished_ns'], sample['completed']
            self.check('sample_time_order', unsigned(begin) and unsigned(end) and previous_end <= begin <= end,
                       [name, index])
            self.check('sample_count_order', len(counts) == len(workers) and all(unsigned(value) and
                       old <= value <= worker['completed'] for value, old, worker in zip(counts, previous, workers)), [name, index])
            self.check('sample_worker_lifetime', all((end >= worker['active_started_ns'] or value == 0) and
                       (begin < worker['kernel_finished_ns'] or value == worker['completed'])
                       for value, worker in zip(counts, workers)), [name, index])
            if begin >= eligible_start and end <= active_end:
                eligible.append(index)
            previous_end, previous = end, counts
        ends = [samples[index]['finished_ns'] for index in eligible]
        best, candidates = None, 0
        # Binary search independently implements the earliest endpoint rule.
        # Fraction comparison preserves exact ratios and first-observed ties.
        for position, first in enumerate(eligible):
            endpoint = bisect_left(ends, samples[first]['started_ns'] + m['peak_window_ns'], lo=position + 1)
            if endpoint == len(eligible):
                continue
            last = eligible[endpoint]
            deltas = [b - a for a, b in zip(samples[first]['completed'], samples[last]['completed'])]
            elapsed = samples[last]['finished_ns'] - samples[first]['started_ns']
            rate = Fraction(sum(deltas), elapsed)
            candidates += 1
            if all(value > 0 for value in deltas) and (best is None or rate > best[0]):
                best = (rate, first, last, deltas, elapsed)
        if not self.check('positive_peak_exists', best is not None, name):
            raise ValueError('no positive full-cohort peak: ' + name)
        rate, first, last, deltas, elapsed = best
        start, end = samples[first], samples[last]
        reconstructed = dict(start_sample_index=first, end_sample_index=last,
            started_ns=start['started_ns'], finished_ns=end['finished_ns'],
            start_snapshot_span_ns=start['finished_ns'] - start['started_ns'],
            end_snapshot_span_ns=end['finished_ns'] - end['started_ns'],
            elapsed_ns=elapsed, completed=sum(deltas), worker_completed=deltas,
            throughput_ops_s=float(rate * 1000000000), amortized_ns_op=float(1 / rate),
            policy='observed_full_cohort_earliest_endpoint', requested_window_ns=m['peak_window_ns'],
            settle_ns=m['peak_settle_ns'], active_started_ns=active_start, active_finished_ns=active_end,
            eligible_started_ns=eligible_start, eligible_samples=len(eligible), candidate_windows=candidates,
            progress_batch=256, progress_count_error_bound=256 * len(workers),
            max_snapshot_span_ns=max(sample['finished_ns'] - sample['started_ns'] for sample in samples),
            sample_period_ns=m['sample_period_ns'], collector_cpu=m['collector_cpu'],
            collector_shared=record.get('collector_shared', False))
        self.equal('all_reconstructed_peak_fields', m['peak'], reconstructed, name)
        if 'peak_throughput_ops_s' in record:
            self.equal('record_peak_rate', record['peak_throughput_ops_s'], float(rate * 1000000000), name)
        whole = float(Fraction(count * 1000, wall))
        self.equal('record_whole_rate', record['whole_throughput_ops_s'], whole * 1e6, name)
        self.windows.append(dict(session_path=name, whole_mops=whole, peak_mops=float(rate * 1000),
                                 start_sample_index=first, end_sample_index=last, candidate_windows=candidates))
        return whole, reconstructed

    def diagnostics(self, record, row, name):
        log = self.raw[name + '/kernel.log'].decode(errors='replace')
        lines = log.splitlines()
        captured = row['whole_session_diagnostics']
        self.equal('kernel_log_hash', captured.get('sha256'), self.hashes[name + '/kernel.log'], name)
        faults = [line for line in lines if FAULT.search(line)]
        self.equal('kernel_log_fault_count', captured['fault_count'], len(faults), name)
        self.equal('kernel_log_fault_examples', captured['fault_examples'], faults[:5], name)
        self.check('kernel_log_clean', not faults, name)
        parsed = {}
        for field, marker in (('mutex_stats', 'kd_mutex stats:'), ('mutex_tasks', 'kd_mutex tasks:'),
                              ('mutex_aux', 'kd_mutex aux:')):
            selected = [line for line in lines if marker in line]
            self.check('unique_diagnostic_row', len(selected) == 1 or (field == 'mutex_aux' and not selected), [name, field])
            parsed[field] = fields(selected[0]) if len(selected) == 1 else None
            self.equal('whole_session_counter', captured[field], parsed[field], [name, field])
        self.equal('no_indexed_auxiliary_diagnostic', parsed['mutex_aux'], None, name)
        physical, tasks = parsed['mutex_stats'], parsed['mutex_tasks']
        self.check('whole_session_drain', physical['active_waiters'] == physical['reserved_nodes'] ==
                   physical['frame_failure'] == tasks['active_tasks'] == 0, name)
        self.equal('exact_physical_balance', physical['origin_acquires'], physical['origin_releases'], name)
        batch = physical['jit_success'] / physical['combiner'] if physical['combiner'] else None
        self.equal('whole_session_batch_ratio', captured['bodies_per_combiner'], batch, name)
        if record.get('kind') == 'pipebytes':
            ratios = [fields(line) for line in lines if 'kd_hotlock mutex ratio:' in line]
            cpus = [item['cpu'] for item in ratios]
            self.equal('ratio_cpu_unique', len(set(cpus)), len(cpus), name)
            self.check('ratio_cpu_expected', set(cpus) <= set(record['cpus']) | {record['collector_cpu']}, name)
            missing = sorted(set(record['cpus']) - set(cpus))
            observed = sum(item['checks'] * 1024 + item['contentions'] for item in ratios)
            warm, measured = self.json(name + '/warmup.json'), self.json(name + '/measure.json')
            self.check('raw_measured_phase_binding', all(record['measurement'].get(key) == value
                       for key, value in measured.items()), name)
            self.equal('pipe_learning_waves', record['learning_waves'], [], name)
            self.check('warmup_complete', warm['ok'] is True and len(warm['workers']) == record['threads'] and
                       warm['completed'] == sum(worker['completed'] for worker in warm['workers']) and
                       all(worker['completed'] >= record['warmup'] for worker in warm['workers']), name)
            for endpoint in ('check-before', 'check-after'):
                self.equal('redirected_check', self.json(name + '/' + endpoint + '.json')['check'], True, [name, endpoint])
            # The retained runner invokes one redirected pipe check on either
            # side of the single warmup/measure pair. No helper learning waves.
            total = warm['completed'] + measured['completed'] + 2
            contentions = None if missing else observed
            fast = None if missing else total - observed
            other = None if missing else observed - physical['jit_success'] - physical['origin_acquires']
            self.check('admission_reconstruction_nonnegative', missing or (fast >= 0 and other >= 0), name)
            auxiliary = parsed['mutex_aux']
            finals = [fields(line) for line in lines if 'kd_hotlock final:' in line and 'type=mutex' in line]
            self.pipe.append(dict(arm=row['arm'], collection=row['collection'], threads=row['threads'], repeat=row['repeat'],
                session_path=name, measured_operations=measured['completed'], warmup_operations=warm['completed'],
                whole_operations_including_checks=total, measured_returned_jit_share=row['measured_returned_jit_share'],
                whole_jit_success=physical['jit_success'], whole_origin_acquires=physical['origin_acquires'],
                whole_combiner_starts=physical['combiner'], whole_bodies_per_combiner=batch,
                missing_ratio_cpus=missing, observed_ratio_cpus=sorted(cpus),
                reconstructed_contentions=contentions, incomplete_observed_contention_sum=observed if missing else None,
                reconstructed_native_fast=fast, native_fast_whole_fraction=fast / total if fast is not None else None,
                reconstructed_other_contended=other,
                residual_after_2047_per_worker=None if other is None else other - 2047 * record['threads'],
                final_mutex_heat_rows=len(finals), all_reported_final_mutex_heat_hot=
                    all(item['cpu_hot'] and item['lock_hot'] for item in finals) if finals else None,
                auxiliary_counts=auxiliary,
                failure_counters={key: physical[key] for key in
                    ('handoff', 'jit_not_ready', 'jit_failure', 'context_busy', 'node_overflow', 'frame_failure')}))
        return batch

    def session(self, record, row, collection):
        group, name = row['collection'], row['session_path']
        workload = '%s-%s-n%d' % (
            record['kind'], record['query'], record['entries'])
        self.equal('raw_summary_identity', [row['name'], row['arm'], row['collection'], row['threads'], row['repeat'], row['workload']],
                   [record['name'], collection['arm'], collection['collection'], record['threads'], record['repeat'], workload], name)
        saved = self.json(name + '/session.json')
        self.equal('saved_session_hash', row['session_sha256'], self.hashes[name + '/session.json'], name)
        self.check('saved_session_key_presence', set(saved) <= set(record), name)
        self.equal('saved_session_fields', {key: record.get(key) for key in saved}, saved, name)
        self.equal('aggregate_only_fields', sorted(set(record) - set(saved)), [], name)
        self.check('session_oracle', record['execution_status'] == 'OK' and record['drained'] is True and
                   not record.get('error') and not record.get('cleanup_error'), name)
        self.equal('source_retirement', record['retired'], dict(state=2, modules=0, frames=0, writers=0), name)
        self.check('summary_valid', row['valid'] is True and row['issues'] == [], name)
        whole, peak = self.peak(record, name)
        for field, value in (('completed', record['measurement']['completed']), ('wall_ns', record['measurement']['wall_ns']),
                             ('jit_bodies', record['jit_bodies']), ('observed_whole_mops', whole),
                             ('source_identity', collection['source_identity']), ('source_commit', collection['source_commit']),
                             ('execution_status', 'OK'), ('drained', True)):
            self.equal('summary_session_value', row[field], value, [name, field])
        self.equal('summary_identity', row['identity'], {key: record.get(key) for key in row['identity']}, name)
        self.equal('summary_cohort_role', row['cohort_role'],
                   'trial' if row['arm'] in TRIAL_ARMS else 'original_comparison', name)
        count, bodies = record['measurement']['completed'], record['jit_bodies']
        returned = record['jit_completions']
        self.check('body_bounds', unsigned(bodies) and bodies <= count, name)
        self.equal('body_share', row['measured_body_entry_share'], bodies / count, name)
        self.equal('returned_count', row['jit_completions'], returned, name)
        self.equal('returned_share', row['measured_returned_jit_share'], returned / count if returned is not None else None, name)
        self.check('api_oracle', record['measurement']['ok'] is True and record['measurement']['phase'] == 'measure' and
                   record['redirected_calls'] == count == record['jit_eligible_operations'], name)
        self.check('returned_bounds', unsigned(returned) and returned <= bodies, name)
        self.check('returned_probe_identity', record['jit_completion_probe'] is True and
                   record['jit_evidence_version'] == record['entry_abi'] == 2, name)
        execution = 'RETURNED_JIT' if returned else 'PARTIAL_JIT' if bodies else 'NO_JIT'
        self.equal('api_status', record['jit_status'], 'PASS' if returned else execution, name)
        self.equal('execution_class', row['jit_class'], execution, name)
        self.equal('summary_score_eligibility', row['score_eligible'], True, name)
        self.check('instrumentation_class', not any(record.get(key, False) for key in ('diagnostic', 'perf_record', 'pmu')), name)
        self.equal('ordinary_mutex_placement', record.get('mutex_lock_offset'), None, name)
        batch = self.diagnostics(record, row, name)
        self.sessions[name] = dict(record=record, summary=row, whole=whole, peak=peak['throughput_ops_s'] / 1e6,
                                   count=count, bodies=bodies, returned=returned, execution=execution, batch=batch)

    def collections(self, comparison, arms):
        rows = comparison['sessions']
        self.equal('session_count', len(rows), 6 * len(arms), 'complete matrix')
        self.equal('unique_session_paths', len({row['session_path'] for row in rows}), len(rows), 'complete matrix')
        lookup = {row['session_path']: row for row in rows}
        collections = comparison['collections']
        self.equal('collection_keys', sorted((row['arm'], row['collection']) for row in collections),
                   sorted((arm, group) for arm in arms for group in ('pipe',)), 'matrix')
        for collection in collections:
            arm, group = collection['arm'], collection['collection']
            prefix = arm + '/' + group
            self.equal('collection_clean', collection['issues'], [], prefix)
            for field, relative in (('records_sha256', prefix + '/records.json'),
                                    ('source_manifest_sha256', prefix + '/source-sha256.json'),
                                    ('command_sha256', arm + '/' + group + '-command.json')):
                self.equal('collection_input_hash', collection[field], self.hashes[relative], relative)
            source = self.json(prefix + '/source-sha256.json')
            self.equal('collection_source_identity', collection['source_identity'], sha(json.dumps(source, sort_keys=True).encode()), prefix)
            command = self.json(arm + '/' + group + '-command.json')
            self.check('collection_command', command['exit_code'] == 0 and command['version'] == arm and
                       command['source_commit'] == collection['source_commit'], prefix)
            records, plan = self.json(prefix + '/records.json'), self.json(prefix + '/plan.json')
            self.equal('plan_name_order', [row['name'] for row in records], [row['name'] for row in plan], prefix)
            self.equal('collection_count', len(records), 6, prefix)
            self.equal('collection_summary_count', collection['sessions'], len(records), prefix)
            for record, spec in zip(records, plan):
                name = prefix + '/' + record['name']
                self.equal('plan_identity', {key: record.get(key) for key in spec}, spec, name)
                if not self.check('raw_session_in_summary', name in lookup, name):
                    continue
                try:
                    self.session(record, lookup[name], collection)
                except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
                    self.check('session_data_exception', False, dict(session_path=name, error=str(error)))
        self.equal('audited_session_count', len(self.sessions), len(rows), 'all raw sessions audited')

    def groups(self, comparison, arms):
        grouped = defaultdict(list)
        for value in self.sessions.values():
            row = value['summary']
            grouped[row['arm'], row['workload'], row['threads']].append(value)
        expected = sorted((arm, workload, workers) for arm in arms
                          for workload in ('pipebytes-query-n16',) for workers in (8, 60))
        self.equal('group_keys', sorted(grouped), expected, 'plain cohort identities')
        cross_arm = []
        for workers in (8, 60):
            rows = [value['summary'] for value in self.sessions.values() if value['summary']['threads'] == workers]
            identities = {json.dumps({key: item for key, item in row['identity'].items()
                                      if key != 'mutex_implementation'}, sort_keys=True) for row in rows}
            comparable = len(identities) == 1 and {row['arm'] for row in rows} == set(arms)
            self.check('cross_arm_compatible', comparable, workers)
            cross_arm.append(dict(threads=workers, comparable=comparable,
                                  allowed_identity_differences=['mutex_implementation']))
        self.equal('cross_arm_identity_receipt', comparison['cross_arm_identity'], cross_arm, 'plain cohorts')
        exported = comparison['groups']
        self.equal('exported_group_keys', sorted((row['arm'], row['workload'], row['threads']) for row in exported), expected, 'plain groups')
        for group in exported:
            key = group['arm'], group['workload'], group['threads']
            values = grouped[key]
            if not self.check('group_has_raw_sessions', bool(values), list(key)):
                continue
            self.equal('group_repeat_order', [value['summary']['repeat'] for value in values], group['repeats'], list(key))
            self.equal('group_repeat_set', sorted(value['summary']['repeat'] for value in values), [0, 1, 2], list(key))
            classes = {value['execution'] for value in values}
            identities = {json.dumps(value['summary']['identity'], sort_keys=True) for value in values}
            self.check('group_identity_cohort', len(classes) == len(identities) == 1, list(key))
            self.equal('group_complete', [group['planned'], group['valid'], group['status']], [3, 3, 'COMPLETE'], list(key))
            self.equal('group_cohort_role', group['cohort_role'],
                       'trial' if group['arm'] in TRIAL_ARMS else 'original_comparison', list(key))
            self.equal('group_whole_statistics', group['whole_mops'], stats([value['whole'] for value in values]), list(key))
            self.equal('group_batch_statistics', group['whole_session_bodies_per_combiner'],
                       stats([value['batch'] for value in values if value['batch'] is not None]), list(key))
            operations = sum(value['count'] for value in values)
            self.equal('group_body_share', group['measured_body_entry_share'],
                       sum(value['bodies'] for value in values) / operations, list(key))
            returns = sum(value['returned'] for value in values)
            self.equal('group_return_share', group['measured_returned_jit_share'], returns / operations if returns is not None else None, list(key))
            self.equal('group_execution_class', group['jit_class'], values[0]['execution'], list(key))
            self.check('group_source_cohort', all(value['summary']['source_commit'] == group['source_commit'] and
                       value['summary']['source_identity'] == group['source_identity'] for value in values), list(key))

    def placement(self, analysis):
        self.equal('placement_analysis_complete', [analysis['complete'], analysis['issues']], [True, []], 'placement')
        self.equal('placement_source_labels', [analysis['source_revision'], analysis['baseline_revision']],
                   ['09ebd8f', '0987358'], 'placement')
        self.equal('placement_unscored', [analysis['diagnostic'], analysis['score_eligible']], [True, False], 'placement')
        for name, expected in analysis['input_sha256'].items():
            self.equal('placement_input_binding', self.hashes[name], expected, name)
        self.equal('placement_helper_binding', self.hashes['placement-analysis.py'], analysis['script_sha256'], 'helper')
        rows = analysis['sessions']
        expected = sorted((offset, workers, repeat) for offset in (32, 40) for workers in (8, 60) for repeat in range(3))
        self.equal('placement_inventory', sorted((row['offset'], row['threads'], row['repeat']) for row in rows), expected, 'placement')
        grouped = defaultdict(list)
        for row in rows:
            name, offset, workers = row['session_path'], row['offset'], row['threads']
            record = self.json(name + '/session.json')
            collection = 'placement/offset' + str(offset)
            self.check('placement_raw_aggregate', record in self.json(collection + '/records.json'), name)
            self.equal('placement_session_hash', row['session_sha256'], self.hashes[name + '/session.json'], name)
            self.equal('placement_kernel_log_hash', row['kernel_log_sha256'], self.hashes[name + '/kernel.log'], name)
            self.equal('placement_actual_identity', [record['threads'], record['repeat'], record['mutex_lock_offset'],
                       record['diagnostic'], record['lock_addr'] % 64, record['execution_status'], record['drained']],
                       [workers, row['repeat'], offset, True, offset, 'OK', True], name)
            self.equal('placement_layout_receipt', record['mutex_lock_placement'],
                       dict(offset=offset, cache_line_bytes=64, storage_bytes=128), name)
            self.equal('placement_summary_valid', [row['valid'], row['diagnostic'], row['score_eligible']],
                       [True, True, False], name)
            source = self.json(collection + '/source-sha256.json')
            self.equal('placement_source_identity', record['source_identity'],
                       sha(json.dumps(source, sort_keys=True).encode()), name)
            whole, _ = self.peak(record, name)
            count, wall = record['measurement']['completed'], record['measurement']['wall_ns']
            bodies, returned, address = record['jit_bodies'], record['jit_completions'], record['lock_addr']
            self.check('placement_returned_body', 0 < bodies == returned <= count, name)
            self.equal('placement_summary_counts', [row['completed'], row['wall_ns'], row['jit_bodies'], row['jit_completions']],
                       [count, wall, bodies, returned], name)
            self.equal('placement_summary_rate', row['whole_mops'], whole, name)
            self.equal('placement_summary_share', row['measured_returned_jit_share'], returned / count, name)
            self.equal('placement_summary_address', row['lock_addr'], address, name)
            fields = {field: dict(address=address + delta, line=(address + delta) // 64, offset=(address + delta) % 64)
                      for field, delta in (('owner', 0), ('gate', 24), ('tail', 28))}
            self.equal('placement_field_lines', row['field_lines'], fields, name)
            self.equal('placement_retirement', record['retired'], dict(state=2, modules=0, frames=0, writers=0), name)
            log = self.raw[name + '/kernel.log'].decode(errors='replace')
            self.check('placement_no_kernel_fault', not FAULT.search(log), name)
            for endpoint in ('check-before', 'check-after'):
                self.equal('placement_business_oracle', self.json(name + '/' + endpoint + '.json')['check'], True, name)
            grouped[(offset, workers)].append(dict(repeat=row['repeat'], whole=whole, completed=count, returned=returned))
        groups = []
        for (offset, workers), values in sorted(grouped.items()):
            groups.append(dict(offset=offset, threads=workers, repeats=[value['repeat'] for value in values],
                               whole_mops=stats([value['whole'] for value in values]),
                               measured_returned_jit_share=sum(value['returned'] for value in values) /
                                   sum(value['completed'] for value in values)))
        self.equal('placement_group_arithmetic', analysis['groups'], groups, 'placement')
        mapping = {(group['offset'], group['threads']): group['whole_mops']['median'] for group in groups}
        effects = []
        for workers in (8, 60):
            left, right = mapping[(32, workers)], mapping[(40, workers)]
            effects.append(dict(threads=workers, offset32_mops=left, offset40_mops=right,
                                split_over_shared=right / left, change_percent=100 * (right / left - 1)))
        self.equal('placement_effect_arithmetic', analysis['effects'], effects, 'placement')
        self.equal('placement_kernel_inventory', analysis['kernel_logs'], [row['session_path'] + '/kernel.log' for row in rows], 'placement')
        return dict(sessions=len(rows), groups=groups, effects=effects)

    def profile_records(self, profiles, arms):
        inputs = profiles['inputs']
        self.equal('profile_input_arm_set', sorted(row['arm'] for row in inputs), sorted(arms), 'profile collections')
        for source in inputs:
            arm = source['arm']; folder = arm + '/profile/pipe'
            manifest = self.json(folder + '/source-sha256.json')
            identity = sha(json.dumps(manifest, sort_keys=True).encode())
            self.equal('profile_source_identity', source['source_identity'], identity, folder)
            for field, name in (('records_sha256', folder + '/records.json'),
                                ('source_manifest_sha256', folder + '/source-sha256.json'),
                                ('command_sha256', arm + '/profile-command.json')):
                self.equal('profile_collection_hash', source[field], self.hashes[name], name)
            command = self.json(arm + '/profile-command.json')
            self.check('profile_collection_exit', command['exit_code'] == 0 and command['version'] == arm and
                       command['source_commit'] == source['source_commit'], folder)
            records, plan = self.json(folder + '/records.json'), self.json(folder + '/plan.json')
            self.equal('profile_record_count', len(records), 2, folder)
            self.equal('profile_record_keys', sorted((row['threads'], row['repeat']) for row in records), [(8, 0), (60, 0)], folder)
            self.equal('profile_plan_names', [row['name'] for row in records], [row['name'] for row in plan], folder)
            for record, spec in zip(records, plan):
                name = folder + '/' + record['name']
                self.equal('profile_plan_fields', {key: record.get(key) for key in spec}, spec, name)
                self.equal('profile_saved_record', self.json(name + '/session.json'), record, name)
                self.equal('profile_record_source', record['source_identity'], identity, name)
                self.check('profile_oracle', record['execution_status'] == 'OK' and record['drained'] is True and
                           record.get('diagnostic') is True and record.get('score_eligible') is False and
                           record.get('retired') == dict(state=2, modules=0, frames=0, writers=0), name)
                count = record['measurement']['completed']; bodies = record['jit_bodies']; returned = record['jit_completions']
                self.check('profile_api_bounds', unsigned(count) and unsigned(bodies) and unsigned(returned) and
                           0 < returned <= bodies <= count and record['measurement']['ok'] is True and
                           record['redirected_calls'] == record['jit_eligible_operations'] == count and
                           record['jit_completion_probe'] is True and record['jit_evidence_version'] == record['entry_abi'] == 2, name)
                whole, peak = self.peak(record, name)
                summary = dict(arm=arm, source_commit=source['source_commit'], source_identity=identity,
                               collection='profile', workload='pipebytes-query-n16', threads=record['threads'], repeat=record['repeat'])
                self.sessions[name] = dict(record=record, summary=summary, whole=whole, peak=peak,
                                           count=count, bodies=bodies, returned=returned, execution='RETURNED_JIT')

    def profile(self, profile, top):
        name = profile['profile_path']
        audited = self.sessions[name]
        record, summary = audited['record'], audited['summary']
        self.check('profile_complete', profile['complete'] is True and not profile['issues'], name)
        self.equal('profile_score', profile['score_eligible'], False, name)
        for field in ('arm', 'source_commit', 'source_identity', 'threads', 'repeat'):
            self.equal('profile_identity', profile[field], summary[field], [name, field])
        self.equal('profile_workload', summary['workload'], 'pipebytes-query-n16', name)
        self.equal('profile_event', [profile['event'], profile['sampling_frequency_hz']], ['cycles:k', 199], name)
        self.equal('profile_record_control', [record['perf_exit_code'], record['perf_control_acks']],
                   [0, ['enable', 'disable', 'stop']], name)
        for relative, digest in profile['input_sha256'].items():
            self.equal('profile_input_hash', digest, self.hashes[name + '/' + relative], [name, relative])
        self.equal('profile_perf_hash', profile['perf_binary_sha256'], self.hashes[profile['arm'] + '/profile/tools/perf'], name)
        kernel = self.raw[name + '/kernel.log'].decode(errors='replace')
        self.check('profile_kernel_clean', not FAULT.search(kernel) and 'kd_mutex aux:' not in kernel, name)
        for field, marker in (('physical', 'kd_mutex stats:'), ('tasks', 'kd_mutex tasks:')):
            lines = [line for line in kernel.splitlines() if marker in line]
            self.equal('profile_diagnostic_rows', len(lines), 1, [name, field])
            actual = fields(lines[0]) if len(lines) == 1 else {}
            self.equal('profile_diagnostic_counters', profile['whole_session_diagnostics'][field], actual, [name, field])
            self.check('profile_exact_drain', all(actual.get(key) == 0 for key in
                       (('active_waiters', 'reserved_nodes', 'frame_failure') if field == 'physical' else ('active_tasks',))), [name, field])
            if field == 'physical':
                self.equal('profile_exact_physical_balance', actual.get('origin_acquires'), actual.get('origin_releases'), name)
        text = self.raw[name + '/perf-samples.txt'].decode()
        periods, counts, commands, ips, ip_counts = Counter(), Counter(), Counter(), Counter(), Counter()
        cpus, pids, tids, timestamps = set(), set(), set(), []
        errors, losses, headers, blanks = [], [], 0, 0
        for lineno, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                blanks += 1
                continue
            if 'PERF_RECORD_LOST' in line:
                losses.append(dict(line=lineno, text=line))
                continue
            if line.lstrip().startswith('#'):
                headers += 1
                continue
            # Delimiter parsing is intentionally independent of the report's
            # single sample regex; unknown symbols remain denominator samples.
            try:
                before, separator, after = line.partition(' cycles:k:')
                if not separator:
                    raise ValueError('unexpected event or malformed sample')
                header, period_text = before.rsplit(':', 1)
                header = re.sub(r'\s*/\s*', '/', header)
                comm, identity, cpu_text, timestamp_text = header.rsplit(None, 3)
                pid_text, tid_text = identity.split('/')
                ip_text, tail = after.strip().split(None, 1)
                symbol, dso_text = tail.rsplit(' (', 1)
                period, pid, tid, cpu = int(period_text), int(pid_text), int(tid_text), int(cpu_text[1:-1])
                timestamp, ip = float(timestamp_text), int(ip_text, 16)
                if not (period > 0 and cpu_text.startswith('[') and cpu_text.endswith(']') and
                        dso_text.endswith(')') and symbol and len(dso_text) > 1 and comm.strip() and
                        pid >= 0 and tid >= 0 and cpu >= 0 and math.isfinite(timestamp)):
                    raise ValueError('invalid sample fields')
                comm, dso = comm.strip(), dso_text[:-1]
            except (ValueError, IndexError):
                errors.append(dict(line=lineno, text=line))
                continue
            worker = comm == 'sc_worker'
            key = worker, symbol, dso
            periods[key] += period
            counts[key] += 1
            commands[comm] += period
            pids.add(pid); tids.add(tid); timestamps.append(timestamp)
            if worker:
                cpus.add(cpu)
            if any(re.search(FOCUS[focus], symbol_base(symbol)) for focus in OFFSET_NAMES):
                ips[(*key, ip)] += period
                ip_counts[(*key, ip)] += 1
        all_period, all_count = sum(periods.values()), sum(counts.values())
        worker_period = sum(period for key, period in periods.items() if key[0])
        worker_count = sum(count for key, count in counts.items() if key[0])
        self.check('profile_positive_denominators', all_period > 0 and worker_period > 0 and worker_count > 0, name)
        self.equal('profile_raw_parsed_lines', profile['parsed_sample_lines'], all_count, name)
        self.equal('profile_raw_nonempty_lines', profile['nonempty_lines'], all_count + headers + len(errors) + len(losses), name)
        self.equal('profile_raw_header_blank_lines', [profile['header_lines'], profile['blank_lines']], [headers, blanks], name)
        self.equal('profile_raw_parse_error_count', profile['parse_error_count'], len(errors), name)
        self.equal('profile_raw_parse_errors', profile['parse_errors'], errors[:10], name)
        self.equal('profile_raw_loss_line_count', profile['lost_event_line_count'], len(losses), name)
        self.equal('profile_raw_loss_lines', profile['lost_event_lines'], losses[:10], name)
        self.check('profile_no_unparsed_or_loss', not errors and not losses, name)
        for label, period, count in (('all_kernel', all_period, all_count), ('sc_worker', worker_period, worker_count)):
            self.equal('profile_denominator', profile['denominator_' + label],
                       dict(observed_sum_period=period, samples=count), [name, label])
        self.equal('profile_worker_cpus', profile['worker_cpus'], sorted(cpus), name)
        self.equal('profile_worker_cpu_coverage', sorted(cpus), record['cpus'], name)
        self.equal('profile_process_ids', profile['observed_pids'], sorted(pids), name)
        self.equal('profile_client_pid', sorted(pids), [record['client_pid']], name)
        self.equal('profile_thread_count', profile['observed_tid_count'], len(tids), name)
        self.equal('profile_sample_times', [profile['first_sample_time'], profile['last_sample_time']],
                   [min(timestamps), max(timestamps)] if timestamps else [None, None], name)
        self.equal('profile_command_periods', profile['command_periods'], dict(commands), name)
        report = self.raw[name + '/perf-report.txt'].decode()
        report_lost, report_periods, report_events = [], [], []
        for line in report.splitlines():
            item = line.strip().removeprefix('#').strip()
            if item.startswith('Total Lost Samples:'):
                report_lost.append(int(item.split(':', 1)[1].strip().replace(',', '')))
            elif item.startswith('Event count (approx.):'):
                report_periods.append(int(item.split(':', 1)[1].strip().replace(',', '')))
            elif item.startswith('Samples:'):
                count_text, event = item.removeprefix('Samples:').strip().split(" of event '", 1)
                if not event.endswith("'"):
                    raise ValueError('malformed perf report event')
                report_events.append(dict(displayed_samples=count_text.strip(), event=event[:-1]))
        self.equal('profile_report_loss', profile['report_lost_samples'], report_lost, name)
        self.equal('profile_zero_report_loss', report_lost, [0], name)
        self.equal('profile_report_periods', profile['report_approx_event_counts'], report_periods, name)
        self.equal('profile_report_period_sum', report_periods, [all_period], name)
        self.equal('profile_report_events', profile['report_event_headers'], report_events, name)
        self.equal('profile_report_single_event', [row['event'] for row in report_events], ['cycles:k'], name)
        symbols = defaultdict(lambda: [0, 0, 0, 0])
        for (worker, symbol, dso), period in periods.items():
            value = symbols[symbol, dso]
            value[0] += period; value[1] += counts[worker, symbol, dso]
            if worker:
                value[2] += period; value[3] += counts[worker, symbol, dso]

        def weight(period, count, denominator):
            return dict(observed_sum_period=period, samples=count,
                        percent_of_denominator=100 * period / denominator if denominator else None)

        def symbol_row(key, value):
            return dict(symbol=key[0], dso=key[1], all_kernel=weight(*value[:2], all_period),
                        sc_worker=weight(*value[2:], worker_period))

        self.equal('profile_focus_names', sorted(profile['focus']), sorted(FOCUS), name)
        focus_totals = {}
        for focus, expression in FOCUS.items():
            selected = [(key, value) for key, value in symbols.items() if re.search(expression, symbol_base(key[0]))]
            totals = [sum(value[index] for _, value in selected) for index in range(4)]
            output = profile['focus'][focus]
            self.equal('profile_focus_expression', output['symbol_regex'], expression, [name, focus])
            self.equal('profile_focus_members', sorted((row['symbol'], row['dso']) for row in output['matched_symbols']),
                       sorted(key for key, _ in selected), [name, focus])
            self.equal('profile_focus_all_weight', output['all_kernel'], weight(*totals[:2], all_period), [name, focus])
            self.equal('profile_focus_worker_weight', output['sc_worker'], weight(*totals[2:], worker_period), [name, focus])
            focus_totals[focus] = dict(all_kernel=weight(*totals[:2], all_period), sc_worker=weight(*totals[2:], worker_period))
        for label, index in (('all_kernel', 0), ('sc_worker', 2)):
            expected = [symbol_row(key, value) for key, value in
                        sorted(symbols.items(), key=lambda item: -item[1][index]) if value[index]][:top]
            self.equal('profile_top_symbols', profile['top_' + label], expected, [name, label])
        addresses = {}
        for line in self.raw[name + '/kallsyms'].decode().splitlines():
            tokens = line.split()
            if len(tokens) >= 3:
                addresses[tokens[2], tokens[3] if len(tokens) > 3 else '[kernel.kallsyms]'] = int(tokens[0], 16)
        per_function = defaultdict(list)
        for key in ips:
            per_function[symbol_base(key[1])].append(key)
        selected_ips = [key for function in sorted(per_function) for key in
                        sorted(per_function[function], key=lambda value: -ips[value])[:top]]
        expected_offsets = []
        for key in selected_ips:
            worker, symbol, dso, ip = key
            start = addresses.get((symbol.partition('+0x')[0], dso))
            offset = ip - start if start and ip >= start else None
            expected_offsets.append(dict(comm_scope='sc_worker' if worker else 'other_client', symbol=symbol, dso=dso,
                ip=hex(ip), symbol_offset=hex(offset) if offset is not None else None,
                **weight(ips[key], ip_counts[key], worker_period if worker else all_period)))
        self.equal('profile_focus_offsets', profile['focus_sampled_offsets'], expected_offsets, name)
        self.equal('profile_measurement_counters',
                   [profile['measured_operations'], profile['measured_jit_bodies'], profile['measured_jit_completions']],
                   [audited['count'], audited['bodies'], audited['returned']], name)
        fraction = audited['returned'] / audited['count']
        self.equal('profile_returned_share', profile['measured_returned_jit_share'], fraction, name)
        self.equal('profile_whole_rate', profile['observed_profile_whole_mops'], audited['whole'], name)
        plain = [value for value in self.sessions.values() if value['summary']['arm'] == summary['arm'] and
                 value['summary']['collection'] == 'pipe' and value['summary']['threads'] == summary['threads']]
        context = profile['matching_plain_context']
        self.check('profile_plain_context_complete', context['available'] is True and context['complete'] is True and
                   context['issues'] == [] and context['excluded_sessions'] == [], name)
        self.equal('profile_plain_context_count', [context['n'], context['recorded_count'], len(plain)], [3, 3, 3], name)
        self.equal('profile_plain_source', context['source_commit'], summary['source_commit'], name)
        self.equal('profile_plain_source_identity', context['source_identity'], plain[0]['summary']['source_identity'], name)
        self.equal('profile_plain_class', context['execution_class'], plain[0]['execution'], name)
        count, returned = sum(value['count'] for value in plain), sum(value['returned'] for value in plain)
        plain_fraction = returned / count
        self.equal('profile_plain_totals', [context['measured_operations'], context['measured_returned_bodies']], [count, returned], name)
        self.equal('profile_plain_share', context['measured_returned_jit_share'], plain_fraction, name)
        self.equal('profile_plain_statistics', context['whole_mops'], stats([value['whole'] for value in plain]), name)
        self.equal('profile_plain_records_hash', context['records_sha256'], self.hashes[summary['arm'] + '/pipe/records.json'], name)
        self.equal('profile_plain_comparison_hash', context['comparison_sha256'], self.hashes['comparison.json'], name)
        self.equal('profile_plain_share_difference', profile['profile_minus_plain_jit_percentage_points'],
                   100 * (fraction - plain_fraction), name)
        self.check('profile_plain_mismatch_visible', bool(profile['attribution_warning']) if fraction != plain_fraction else
                   profile['attribution_warning'] is None, name)
        self.profiles.append(dict(arm=summary['arm'], threads=summary['threads'], profile_path=name,
            parsed_samples=all_count, all_kernel_period=all_period, sc_worker_samples=worker_count,
            sc_worker_period=worker_period, unparsed_records=len(errors), lost_records=len(losses), report_lost=report_lost,
            measured_returned_jit_share=fraction, plain_returned_jit_share=plain_fraction,
            profile_minus_plain_jit_percentage_points=100 * (fraction - plain_fraction), focus=focus_totals))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--arms', nargs='+', default=list(ARMS))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--profile-top', type=int, default=16)
    args = parser.parse_args()
    report, raw = args.report.resolve(), args.raw.resolve()
    if len(set(args.arms)) != len(args.arms) or set(args.arms) not in (set(ARMS), set(ARMS + TRIAL_ARMS)):
        raise ValueError('select the original three arms and optionally the separate prefetch trial')
    if not 1 <= args.profile_top <= 50:
        raise ValueError('--profile-top must be 1..50')
    output = (args.output or report / 'statistics-review.json').resolve()
    if output == Path(__file__).resolve() or output.is_relative_to(raw) or output in (
            report / 'comparison.json', report / 'profile-analysis.json', report / 'placement-analysis.json'):
        raise ValueError('output must not replace source or retained inputs')
    audit = Audit()
    comparison = json.loads((report / 'comparison.json').read_bytes())
    profiles = json.loads((report / 'profile-analysis.json').read_bytes())
    placement = json.loads((report / 'placement-analysis.json').read_bytes())
    audit.load(raw)
    for filename in ('comparison.json', 'profile-analysis.json', 'placement-analysis.json'):
        audit.equal('report_archive_binding', file_hash(report / filename), audit.hashes[filename], filename)
    audit.equal('ordered_source_arms', comparison['arms'], args.arms, 'requested source arms')
    audit.equal('original_comparison_arms', comparison['original_comparison_arms'],
                [arm for arm in args.arms if arm in ARMS], 'requested source roles')
    audit.equal('trial_arms', comparison['trial_arms'],
                [arm for arm in args.arms if arm in TRIAL_ARMS], 'requested source roles')
    for arm in args.arms:
        audit.equal('matrix_original_role', audit.json(arm + '/matrix.json')['comparison_arm'],
                    arm in ARMS, arm)
    audit.equal('comparison_complete', comparison['complete'], True, 'compact comparison')
    audit.equal('comparison_issues', comparison['issues'], [], 'compact comparison')
    audit.collections(comparison, args.arms)
    try:
        audit.groups(comparison, args.arms)
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        audit.check('group_data_exception', False, str(error))
    audit.equal('profile_report_complete', profiles['complete'], True, 'compact profiles')
    audit.equal('profile_report_issues', profiles['issues'], [], 'compact profiles')
    audit.profile_records(profiles, args.arms)
    audit.equal('profile_matrix_keys', sorted((row['arm'], row['threads']) for row in profiles['profiles']),
                sorted((arm, workers) for arm in args.arms for workers in (8, 60)), 'profile matrix')
    for profile in profiles['profiles']:
        try:
            audit.profile(profile, args.profile_top)
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
            audit.check('profile_data_exception', False, dict(profile_path=profile.get('profile_path'), error=str(error)))
    audit.equal('audited_profile_count', len(audit.profiles), 2 * len(args.arms), 'profile matrix')
    placement_review = audit.placement(placement)
    audit.equal('reconstructed_window_count', len(audit.windows), 8 * len(args.arms) + 12, 'all raw windows reconstructed')
    result = dict(schema=1, created_utc=datetime.now(timezone.utc).isoformat(), passed=not audit.issues,
        scope='Independent data-only offline archive arithmetic audit; no retained code or binaries executed.',
        arms=args.arms, checks=dict(audit.checks), issues=audit.issues,
        audited_sessions=len(audit.sessions), reconstructed_windows=len(audit.windows),
        audited_profiles=len(audit.profiles), parsed_profile_samples=sum(row['parsed_samples'] for row in audit.profiles),
        audited_placement_sessions=placement_review['sessions'], placement_review=placement_review,
        input_sha256={name: file_hash(report / name) for name in ('comparison.json', 'profile-analysis.json', 'placement-analysis.json')},
        script_sha256=file_hash(Path(__file__)), archives_manifest_sha256=file_hash(raw / 'archives.json'),
        archives=audit.archives, windows=audit.windows, pipe_phase_diagnostics=audit.pipe,
        profile_weight_receipts=audit.profiles,
        limits=['The separate archive/source audit validates the complete source, binary and snapshot inventory.',
                'Whole-session counters include warmup and checks. Measured returned JIT fractions use only measured API counters.',
                'Heat ratios are approximate admission diagnostics, never exact ownership/retirement authorities. Missing suppressed CPU rows remain unknown.',
                'Bodies per combiner is an aggregate ratio, not a batch-size distribution. The 2047-per-worker residual is diagnostic accounting, not a new invariant.',
                'Pipe records do not supply type geometry; the dedicated local live probe supplies sizeof/alignof evidence.',
                'Profiles remain separate from plain timings. Flat sampled IPs have skid and do not count atomic retries or establish causal cost.',
                'Peak windows use exact rational selection and observed endpoints; whole-run fractions do not describe peak-window delegation.'])
    output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    print(json.dumps(dict(passed=result['passed'], checks=sum(audit.checks.values()), issues=len(audit.issues),
                          sessions=len(audit.sessions), output=str(output))))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
