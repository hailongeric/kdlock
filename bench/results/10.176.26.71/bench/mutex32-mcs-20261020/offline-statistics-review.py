#!/usr/bin/env python3
"""Independent, read-only arithmetic audit of retained MCS-round archives.

Run on the source host after collection and archiving finish. Only this newly
authored script executes: retained Python, binaries and modules are data. The
separate archive/source audit checks the broader artifact inventory. This audit
reconstructs all timed windows, phase fractions, whole-session counters, group
statistics without importing the collection or summary helpers.
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


ARMS = ('baseline', 'candidate', 'old256')
DERIVED = {'whole_amortized_ns_op', 'throughput_ops_s', 'whole_throughput_ops_s',
           'score_eligible', 'amortized_ns_op'}
FAULT = re.compile(r'BUG:|\bWARNING:|kernel panic|double fault|soft lockup|hard LOCKUP|'
                   r'unable to handle|general protection fault|Oops:|\[ERROR\]|'
                   r'invariant_failures=[1-9]|runtime error:|KASAN:|UBSAN:', re.I)
WANTED = {'records.json', 'session.json', 'source-sha256.json', 'plan.json', 'matrix.json',
          'warmup.json', 'measure.json', 'check-before.json', 'check-after.json',
          'kernel.log', 'comparison.json'}


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
        self.equal('no_auxiliary_diagnostics', parsed['mutex_aux'], None, name)
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
                residual_after_2047_per_worker_and_busy=None if other is None else
                    other - 2047 * record['threads'] - (auxiliary['busy'] if auxiliary else 0),
                final_mutex_heat_rows=len(finals), all_reported_final_mutex_heat_hot=
                    all(item['cpu_hot'] and item['lock_hot'] for item in finals) if finals else None,
                auxiliary_counts=auxiliary,
                failure_counters={key: physical[key] for key in
                    ('handoff', 'jit_not_ready', 'jit_failure', 'context_busy', 'node_overflow', 'frame_failure')}))
        return batch

    def session(self, record, row, collection):
        group, name = row['collection'], row['session_path']
        workload = 'c%02d' % record['cachelines'] if group == 'synthetic' else '%s-%s-n%d' % (
            record['kind'], record['query'], record['entries'])
        self.equal('raw_summary_identity', [row['name'], row['arm'], row['collection'], row['threads'], row['repeat'], row['workload']],
                   [record['name'], collection['arm'], collection['collection'], record['threads'], record['repeat'], workload], name)
        saved = self.json(name + '/session.json')
        self.equal('saved_session_hash', row['session_sha256'], self.hashes[name + '/session.json'], name)
        self.check('saved_session_key_presence', set(saved) <= set(record), name)
        self.equal('saved_session_fields', {key: record.get(key) for key in saved}, saved, name)
        self.equal('aggregate_only_fields', sorted(set(record) - set(saved)), sorted(DERIVED) if group == 'synthetic' else [], name)
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
        count, bodies = record['measurement']['completed'], record['jit_bodies']
        returned = None if group == 'synthetic' else record['jit_completions']
        self.check('body_bounds', unsigned(bodies) and bodies <= count, name)
        self.equal('body_share', row['measured_body_entry_share'], bodies / count, name)
        self.equal('returned_count', row['jit_completions'], returned, name)
        self.equal('returned_share', row['measured_returned_jit_share'], returned / count if returned is not None else None, name)
        if group == 'synthetic':
            self.check('synthetic_oracle', record['measurement']['complete'] is True and
                       record['measurement']['data_ok'] is True, name)
            self.equal('synthetic_entry_delta', record['jit_after'] - record['jit_before'], bodies, name)
            self.check('synthetic_completion_unmeasured', record['parameters']['bench_complete_probe'] in ('N', '0'), name)
            compact = 'include/kd_mutex_state.h' in self.json(
                name.rsplit('/', 1)[0] + '/source-sha256.json')
            size, alignment = (32, 8) if compact else (256, 128)
            layout = record['layout']
            self.check('runtime_lock_geometry', layout['lock_bytes'] == size and unsigned(layout['lock_addr']) and
                       layout['lock_addr'] > 0 and layout['lock_addr'] % alignment == 0, name)
            self.check('reported_type_alignment', 'lock_align' not in layout or layout['lock_align'] == alignment, name)
            self.equal('summary_runtime_geometry', row['layout'],
                       dict(lock_bytes=layout['lock_bytes'], lock_addr=layout['lock_addr'],
                            reported_type_alignment=layout.get('lock_align'), required_address_alignment=alignment), name)
            execution = 'WITNESSED_JIT' if bodies else 'NO_JIT'
            self.equal('synthetic_derived_fields', {key: record[key] for key in DERIVED},
                dict(whole_throughput_ops_s=whole * 1e6,
                     whole_amortized_ns_op=record['measurement']['wall_ns'] / count,
                     throughput_ops_s=peak['throughput_ops_s'], amortized_ns_op=peak['amortized_ns_op'],
                     score_eligible=not any(record.get(key, False) for key in ('diagnostic', 'pmu', 'perf_record'))), name)
        else:
            self.check('api_oracle', record['measurement']['ok'] is True and record['measurement']['phase'] == 'measure' and
                       record['redirected_calls'] == count == record['jit_eligible_operations'], name)
            self.check('returned_bounds', unsigned(returned) and returned <= bodies, name)
            self.check('returned_probe_identity', record['jit_completion_probe'] is True and
                       record['jit_evidence_version'] == record['entry_abi'] == 2, name)
            execution = 'RETURNED_JIT' if returned else 'PARTIAL_JIT' if bodies else 'NO_JIT'
            self.equal('api_status', record['jit_status'], 'PASS' if returned else execution, name)
            self.equal('api_layout_unreported', row['layout'], None, name)
        self.equal('execution_class', row['jit_class'], execution, name)
        self.equal('summary_score_eligibility', row['score_eligible'], group != 'profile', name)
        self.check('instrumentation_class',
            all(record.get(key) is True for key in ('diagnostic', 'perf_record')) and
                record.get('pmu') is False and record.get('score_eligible') is False if group == 'profile' else
            not any(record.get(key, False) for key in ('diagnostic', 'perf_record', 'pmu')), name)
        batch = self.diagnostics(record, row, name)
        self.sessions[name] = dict(record=record, summary=row, whole=whole, peak=peak['throughput_ops_s'] / 1e6,
                                   count=count, bodies=bodies, returned=returned, execution=execution, batch=batch)

    def collections(self, comparison, arms):
        rows = comparison['sessions']
        self.equal('session_count', len(rows), 18 * len(arms), 'complete matrix')
        self.equal('unique_session_paths', len({row['session_path'] for row in rows}), len(rows), 'complete matrix')
        lookup = {row['session_path']: row for row in rows}
        collections = comparison['collections']
        self.equal('collection_keys', sorted((row['arm'], row['collection']) for row in collections),
                   sorted((arm, group) for arm in arms for group in ('synthetic', 'seek', 'pipe')), 'matrix')
        for collection in collections:
            arm, group = collection['arm'], collection['collection']
            prefix = arm + '/' + ('profile/pipe' if group == 'profile' else group)
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
            if row['collection'] != 'profile':
                grouped[row['arm'], row['workload'], row['threads']].append(value)
        expected = sorted((arm, workload, workers) for arm in arms
                          for workload in ('c01', 'seek-set-n16', 'pipebytes-query-n16') for workers in (8, 60))
        self.equal('group_keys', sorted(grouped), expected, 'plain cohort identities')
        exported = comparison['groups']
        self.equal('exported_group_keys', sorted((row['arm'], row['workload'], row['threads']) for row in exported), expected, 'plain groups')
        for group in exported:
            key = group['arm'], group['workload'], group['threads']
            values = grouped[key]
            if not self.check('group_has_raw_sessions', bool(values), list(key)):
                continue
            self.equal('group_repeat_set', sorted(value['summary']['repeat'] for value in values), [0, 1, 2], list(key))
            classes = {value['execution'] for value in values}
            identities = {json.dumps(value['summary']['identity'], sort_keys=True) for value in values}
            uniform = len(classes) == len(identities) == 1
            selected = values if uniform else []
            self.equal('group_repeat_order', [value['summary']['repeat'] for value in selected], group['repeats'], list(key))
            self.equal('group_complete', [group['planned'], group['valid'], group['status']],
                       [3, 3, 'COMPLETE' if uniform else 'MIXED_IDENTITY_OR_CLASSES'], list(key))
            self.equal('group_whole_statistics', group['whole_mops'], stats([value['whole'] for value in selected]), list(key))
            self.equal('group_batch_statistics', group['whole_session_bodies_per_combiner'],
                       stats([value['batch'] for value in selected if value['batch'] is not None]), list(key))
            operations = sum(value['count'] for value in selected)
            self.equal('group_body_share', group['measured_body_entry_share'],
                       sum(value['bodies'] for value in selected) / operations if operations else None, list(key))
            returns = None if group['collection'] == 'synthetic' or not selected else sum(value['returned'] for value in selected)
            self.equal('group_return_share', group['measured_returned_jit_share'],
                       returns / operations if returns is not None else None, list(key))
            self.equal('group_execution_class', group['jit_class'], next(iter(classes)) if len(classes) == 1 else 'MIXED', list(key))
            self.check('group_source_cohort', all(value['summary']['source_commit'] == group['source_commit'] and
                       value['summary']['source_identity'] == group['source_identity'] for value in values), list(key))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--arms', nargs='+', default=list(ARMS))
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    report, raw = a.report.resolve(), a.raw.resolve()
    if len(a.arms) != 3 or set(a.arms) != set(ARMS):
        raise ValueError('select the three distinct MCS comparison arms')
    output = (a.output or report / 'statistics-review.json').resolve()
    if output == Path(__file__).resolve() or output.is_relative_to(raw) or output == report / 'comparison.json':
        raise ValueError('output must not replace source or retained inputs')
    audit = Audit()
    comparison = json.loads((report / 'comparison.json').read_bytes())
    audit.load(raw)
    audit.equal('report_archive_binding', file_hash(report / 'comparison.json'), audit.hashes['comparison.json'], 'comparison.json')
    audit.equal('ordered_source_arms', comparison['arms'], a.arms, 'requested source arms')
    audit.equal('comparison_complete', comparison['complete'], True, 'compact comparison')
    audit.equal('comparison_issues', comparison['issues'], [], 'compact comparison')
    audit.collections(comparison, a.arms)
    try:
        audit.groups(comparison, a.arms)
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        audit.check('group_data_exception', False, str(error))
    cross_arm = []
    for workload in ('c01', 'seek-set-n16', 'pipebytes-query-n16'):
        for workers in (8, 60):
            values = [v for v in audit.sessions.values() if v['summary']['workload'] == workload
                      and v['summary']['threads'] == workers]
            identities = {json.dumps({k: v for k, v in item['summary']['identity'].items()
                                     if k != 'mutex_implementation'}, sort_keys=True) for item in values}
            classes = {item['execution'] for item in values}
            compatible = len(identities) == 1 and {v['summary']['arm'] for v in values} == set(a.arms)
            cross_arm.append(dict(workload=workload, threads=workers, identity_compatible=compatible,
                execution_classes=sorted(classes), comparable=compatible and len(classes) == 1,
                allowed_identity_differences=['mutex_implementation']))
            audit.check('cross_arm_identity_compatible', compatible, [workload, workers])
    audit.equal('cross_arm_identity_receipt', comparison['cross_arm_identity'], cross_arm, 'cohort comparability')
    audit.equal('reconstructed_window_count', len(audit.windows), 18 * len(a.arms), 'all raw ordinary windows')
    result = dict(schema=1, created_utc=datetime.now(timezone.utc).isoformat(), passed=not audit.issues,
        scope='Independent data-only offline archive arithmetic audit; no retained code or binaries executed.',
        arms=a.arms, checks=dict(audit.checks), issues=audit.issues,
        audited_sessions=len(audit.sessions), reconstructed_windows=len(audit.windows), audited_profiles=0,
        input_sha256={'comparison.json': file_hash(report / 'comparison.json')},
        script_sha256=file_hash(Path(__file__)), archives_manifest_sha256=file_hash(raw / 'archives.json'),
        archives=audit.archives, windows=audit.windows, pipe_phase_diagnostics=audit.pipe,
        limits=['Source/archive checks independently bind full source, binary and snapshot inventories.',
                'Synthetic counters witness entry, not return; API completions are explicit measured-phase counters.',
                'Whole-session counters include warmup and checks; batch ratios are not batch-size distributions.',
                'Heat ratios are approximate admission diagnostics, never ownership or retirement authorities.',
                'No execution-class, source, workload or instrumentation cohorts are pooled.',
                'Peak windows use exact rational selection; whole-run JIT fractions do not describe the peak window.'])
    output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    print(json.dumps(dict(passed=result['passed'], checks=sum(audit.checks.values()), issues=len(audit.issues),
                          sessions=len(audit.sessions), reconstructed_windows=len(audit.windows), output=str(output))))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

