#!/usr/bin/env python3
"""Guest-only, unscored diagnostics for the active mutex nano profiles.

Only the measured client is wrapped. Preparation, translation and warmup retain
their ordinary boundaries. The inherited client includes startup/collection;
flat summaries separately select rb_worker samples within the settled full cohort.
No call-chain unwinding is attempted across generated or borrowed stacks.
Batch and pin modes enable optional provider observations without launching perf.
"""
import argparse
from collections import defaultdict
import csv
from decimal import Decimal
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import kernel_identity

PERF = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-admission-20261013/tools/perf')
EVENTS = ('cycles:k', 'instructions:k', 'cache-references:k', 'cache-misses:k',
          'branches:k', 'branch-misses:k', 'task-clock', 'context-switches',
          'cpu-migrations', 'page-faults')
PROFILES = {'mutex-throughput': ('cacheline', 1, 256),
            'mutex-locality': ('cacheline', 16, 256)}
OBSERVATION_PARAMS = ('bench_jit_bodies', 'bench_jit_completions', 'address_guard_count')
UNEXPORTED_MUTEX_COUNTERS = ('kd_mutex_combiner_count', 'kd_mutex_jit_success_count',
                            'kd_mutex_handoff_count')
BATCH_METADATA = dict(schema=3, compiled=1, total_cap=1024, numa_boundary=1024,
                      deferred_handoff=8, scan_budget=64, numa_aware=1,
                      completed_hist_bins=16, deferred_peak_hist_bins=8)
BATCH_COUNTERS = ('batches', 'attempts', 'jit_completed', 'native_completed', 'owner_transfers',
    'execution_refusals', 'jit_local', 'jit_remote', 'deferred_total', 'scan_steps',
    'scan_exhausted_batches', 'small_fifo_batches')
BATCH_REASONS = ('unclassified', 'initial_unexecutable', 'source_refusal',
    'numa_boundary', 'numa_tail', 'execution_refusal', 'early_outer_release',
    'native_done', 'owner_transfer', 'total_cap', 'empty_tail', 'unsupported_tail')
BATCH_HISTOGRAMS = ('completed_hist', 'deferred_peak_hist')
BATCH_LEGACY = ('combiner', 'jit_success', 'handoff')
PIN_METADATA = dict(schema=1, compiled=2, window=4, total_cap=1024,
                    numa_boundary=1024, tsc_sample_shift=0)
PIN_COUNTERS = ('batches', 'selections', 'requested', 'consumed', 'cancelled',
    'drain_calls', 'drain_nonempty', 'drain_keep_current',
    'current_ack_immediate', 'current_ack_stalled', 'current_ack_loops',
    'cancel_ack_immediate', 'cancel_ack_stalled', 'cancel_ack_loops',
    'full_resumes', 'tsc_samples', 'tsc_cycles')
PIN_HISTOGRAMS = ('occupancy_before', 'occupancy_after')
PIN_REASONS = ('self_current', 'single', 'budget', 'window', 'no_link', 'entry',
               'numa', 'deferred_tail', 'duplicate_cpu', 'self_future')
COMPILED_MODES = ('batch', 'pin')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def observations(folder):
    """Read only existing exports; unavailable static counters are not zeros."""
    available = sorted(p.name for p in folder.iterdir() if p.is_file())
    values = {}
    for name in OBSERVATION_PARAMS:
        require(name in available, 'required observation parameter unavailable: ' + name)
        values[name] = int((folder / name).read_text())
        require(values[name] >= 0, 'invalid observation parameter: ' + name)
    return dict(monotonic_ns=time.monotonic_ns(), values=values,
                available_parameters=available, unavailable_static_counters=list(UNEXPORTED_MUTEX_COUNTERS))


def observation_delta(before, after):
    require(before['values'].keys() == after['values'].keys(), 'observation parameters changed')
    result = {key: value - before['values'][key] for key, value in after['values'].items()}
    require(all(value >= 0 for value in result.values()), 'observation counter reset or moved backward')
    return result


def batch_fields(schema):
    require(type(schema) is int and schema in (2, 3), 'unsupported batch diagnostic schema')
    if schema == 2:
        # Preserve historical records exactly; absence is not a measured zero.
        return (tuple(key for key in BATCH_COUNTERS if key != 'owner_transfers'),
                tuple(key for key in BATCH_REASONS if key != 'owner_transfer'))
    return BATCH_COUNTERS, BATCH_REASONS


def batch_metadata(policy=None, *, schema=3):
    batch_fields(schema)
    result = dict(BATCH_METADATA, schema=schema)
    if policy is not None:
        require(isinstance(policy, dict) and set(policy) ==
                {'total_cap', 'numa_boundary', 'deferred_handoff', 'scan_budget'},
                'unexpected mutex policy schema')
        require(all(type(value) is int for value in policy.values()) and
                1 <= policy['total_cap'] <= 32767 and 1 <= policy['numa_boundary'] <= 32767 and
                policy['deferred_handoff'] == 8 and policy['scan_budget'] == 64,
                'invalid mutex policy')
        result.update(policy)
    return result


def selected_mutex_policy(args):
    policy = dict(total_cap=args.mutex_batch_limit, numa_boundary=args.mutex_numa_boundary,
                  deferred_handoff=8, scan_budget=64)
    batch_metadata(policy)
    require((args.mutex_batch_limit, args.mutex_numa_boundary) == (1024, 1024) or
            'kdlock' in selected_backends(args), 'nondefault mutex policy requires KD')
    return policy


def validate_batch(snapshot, policy=None):
    """Quiescent diagnostic identities only; these never replace exact drain."""
    require(isinstance(snapshot, dict), 'unexpected batch diagnostic schema')
    counters, reasons = batch_fields(snapshot.get('schema'))
    metadata = batch_metadata(policy, schema=snapshot['schema'])
    require(set(snapshot) ==
            set(BATCH_METADATA) | set(counters) | set(BATCH_HISTOGRAMS) | {'stop_reason', 'legacy'},
            'unexpected batch diagnostic schema')
    def counter(value):
        return type(value) is int and 0 <= value <= 2**64 - 1
    require(all(type(snapshot[key]) is int and snapshot[key] == value
                for key, value in metadata.items()), 'batch diagnostic metadata differs')
    require(all(counter(snapshot[key]) for key in counters), 'invalid batch counter')
    for key in BATCH_HISTOGRAMS:
        require(isinstance(snapshot[key], list) and len(snapshot[key]) == snapshot[key + '_bins'] and
                all(counter(value) for value in snapshot[key]), 'invalid batch histogram: ' + key)
    for key, fields in (('stop_reason', reasons), ('legacy', BATCH_LEGACY)):
        require(isinstance(snapshot[key], dict) and set(snapshot[key]) == set(fields) and
                all(counter(value) for value in snapshot[key].values()), 'invalid batch mapping: ' + key)
    batches = snapshot['batches']
    require(batches == sum(snapshot['completed_hist']) == sum(snapshot['deferred_peak_hist']) ==
            sum(snapshot['stop_reason'].values()) == snapshot['legacy']['combiner'],
            'batch counts/histograms/stop reasons/legacy combiner differ')
    require(snapshot['stop_reason']['unclassified'] == 0, 'unclassified batch exit')
    transfers = snapshot['owner_transfers'] if snapshot['schema'] == 3 else 0
    require(snapshot['attempts'] == snapshot['jit_completed'] + snapshot['native_completed'] +
            snapshot['execution_refusals'] + transfers, 'batch attempt accounting differs')
    if snapshot['schema'] == 3:
        require(transfers == snapshot['stop_reason']['owner_transfer'],
                'batch ownership transfer accounting differs')
    require(snapshot['jit_completed'] == snapshot['jit_local'] + snapshot['jit_remote'] ==
            snapshot['legacy']['jit_success'], 'batch completion/locality accounting differs')
    require(snapshot['deferred_total'] == snapshot['scan_steps'], 'batch deferral/scan accounting differs')
    require(snapshot['scan_exhausted_batches'] <= batches and snapshot['small_fifo_batches'] <= batches,
            'batch subset counter exceeds batches')
    require(snapshot['legacy']['handoff'] == sum(snapshot['stop_reason'][key] for key in
            ('initial_unexecutable', 'source_refusal', 'execution_refusal')),
            'legacy refusal handoff accounting differs')
    histogram = snapshot['completed_hist']
    lower = sum(count * (1 << (index - 1)) for index, count in enumerate(histogram) if index)
    upper = sum(count * ((1 << index) - 1) for index, count in enumerate(histogram) if index)
    require(lower <= snapshot['jit_completed'] + snapshot['native_completed'] <= upper,
            'completed-body count outside histogram bounds')
    deferred_lower = sum(count * (1 << (index - 1))
        for index, count in enumerate(snapshot['deferred_peak_hist']) if index)
    require(deferred_lower <= snapshot['deferred_total'], 'deferred peaks exceed total deferrals')
    return snapshot


def batch_delta(before, after, expected_completions=None, policy=None):
    validate_batch(before, policy)
    validate_batch(after, policy)
    require(before['schema'] == after['schema'], 'batch diagnostic schema changed')
    counters, _ = batch_fields(before['schema'])
    result = batch_metadata(policy, schema=before['schema'])
    result.update({key: after[key] - before[key] for key in counters})
    for key in BATCH_HISTOGRAMS:
        result[key] = [b - a for a, b in zip(before[key], after[key])]
    for key in ('stop_reason', 'legacy'):
        result[key] = {field: after[key][field] - before[key][field] for field in before[key]}
    validate_batch(result, policy)
    if expected_completions is not None:
        require(type(expected_completions) is int and expected_completions >= 0 and
                result['jit_completed'] == expected_completions,
                'batch JIT completions differ from exact returned-body counter delta')
    return result


def pin_metadata(policy=None, tsc_sample_shift=0):
    require(type(tsc_sample_shift) is int and tsc_sample_shift in (0, 6),
            'invalid pin TSC sample shift')
    selected = batch_metadata(policy)
    return dict(PIN_METADATA, total_cap=selected['total_cap'],
                numa_boundary=selected['numa_boundary'], tsc_sample_shift=tsc_sample_shift)


def validate_pin(snapshot, policy=None, tsc_sample_shift=0):
    """Check quiescent pin observations, independently of body completion/drain."""
    metadata = pin_metadata(policy, tsc_sample_shift)
    require(isinstance(snapshot, dict) and set(snapshot) ==
            set(PIN_METADATA) | set(PIN_COUNTERS) | set(PIN_HISTOGRAMS) | {'refill_stop'},
            'unexpected pin diagnostic schema')
    require(all(type(snapshot[key]) is int and snapshot[key] == value
                for key, value in metadata.items()), 'pin diagnostic metadata differs')
    def counter(value):
        return type(value) is int and 0 <= value <= 2**64 - 1
    require(all(counter(snapshot[key]) for key in PIN_COUNTERS), 'invalid pin counter')
    for key in PIN_HISTOGRAMS:
        require(isinstance(snapshot[key], list) and len(snapshot[key]) == metadata['window'] + 1 and
                all(counter(value) for value in snapshot[key]), 'invalid pin histogram: ' + key)
    require(isinstance(snapshot['refill_stop'], dict) and
            set(snapshot['refill_stop']) == set(PIN_REASONS) and
            all(counter(value) for value in snapshot['refill_stop'].values()),
            'invalid pin refill stop mapping')
    require(snapshot['selections'] == sum(snapshot['occupancy_before']) ==
            sum(snapshot['occupancy_after']) == sum(snapshot['refill_stop'].values()),
            'pin selections/occupancy/refill stops differ')
    require(snapshot['requested'] == snapshot['consumed'] + snapshot['cancelled'],
            'pin request retirement accounting differs')
    require(snapshot['cancelled'] == snapshot['cancel_ack_immediate'] + snapshot['cancel_ack_stalled'],
            'pin cancellation ACK accounting differs')
    for prefix in ('current', 'cancel'):
        stalled, loops = snapshot[prefix + '_ack_stalled'], snapshot[prefix + '_ack_loops']
        require(loops >= stalled and (stalled != 0 or loops == 0),
                'pin ACK loop accounting differs: ' + prefix)
    require(snapshot['drain_keep_current'] <= snapshot['drain_nonempty'] <= snapshot['drain_calls'],
            'pin drain subset accounting differs')
    require(snapshot['tsc_samples'] <= snapshot['current_ack_immediate'] + snapshot['current_ack_stalled'],
            'pin TSC samples exceed current ACKs')
    require(tsc_sample_shift != 0 or snapshot['tsc_samples'] == snapshot['tsc_cycles'] == 0,
            'pin TSC observations present with sampling disabled')
    return snapshot


def pin_delta(before, after, policy=None, tsc_sample_shift=0):
    validate_pin(before, policy, tsc_sample_shift)
    validate_pin(after, policy, tsc_sample_shift)
    result = pin_metadata(policy, tsc_sample_shift)
    result.update({key: after[key] - before[key] for key in PIN_COUNTERS})
    for key in PIN_HISTOGRAMS:
        result[key] = [b - a for a, b in zip(before[key], after[key])]
    result['refill_stop'] = {key: after['refill_stop'][key] - before['refill_stop'][key]
                           for key in PIN_REASONS}
    validate_pin(result, policy, tsc_sample_shift)
    return result


def parse_stat(text, events, allow_multiplex=False):
    """Preserve reported units/scaling; missing or unsupported counters fail."""
    rows = {}
    for fields in csv.reader(text.splitlines(), delimiter=';'):
        if not fields or not fields[0].strip() or fields[0].lstrip().startswith('#'):
            continue
        require(len(fields) >= 5, 'malformed perf stat row: ' + repr(fields))
        count, unit, event, runtime, percent = [s.strip() for s in fields[:5]]
        require(event in events and event not in rows, 'unexpected/duplicate perf event: ' + event)
        require(not count.startswith('<'), 'unavailable perf event ' + event + ': ' + count)
        try:
            values = [float(count), float(runtime), float(percent.rstrip('%'))]
        except ValueError as error:
            raise ValueError('nonnumeric perf counter/scaling: ' + event) from error
        require(all(math.isfinite(x) for x in values) and values[0] >= 0 and
                values[1] > 0 and 0 < values[2] <= 100, 'invalid perf counter/scaling: ' + event)
        multiplexed = values[2] < 100
        require(allow_multiplex or not multiplexed,
                'multiplexed perf event requires --allow-multiplex: ' + event)
        rows[event] = dict(value=values[0], value_text=count, unit=unit,
            runtime_ns=values[1], runtime_percent=values[2], multiplexed=multiplexed,
            scaling_status='MULTIPLEXED' if multiplexed else 'FULL_RUNTIME', raw_fields=fields)
    require(set(rows) == set(events), 'missing perf events: ' + ','.join(sorted(set(events) - set(rows))))
    return dict(status='MULTIPLEXED' if any(r['multiplexed'] for r in rows.values()) else 'FULL_RUNTIME',
                events=rows, scope='Measured client and inherited threads, including client startup/collection; preparation and warmup excluded')


SAMPLE = re.compile(r'^\s*(\S+)\s+(\d+)/(\d+)\s+\[(\d+)\]\s+'
                    r'(\d+(?:\.\d+)?):\s+(\d+)\s+(\S+):\s+'
                    r'([0-9a-fA-F]+)\s+(.*?)\s+\(([^)]*)\)\s*$')


def summarize_samples(text, measurement, cpus, event, generated_ranges):
    """Use sampled periods, not sample counts, and retain unattributed buckets."""
    active_begin = max(w['active_started_ns'] for w in measurement['workers'])
    settle = measurement['peak_settle_ns']
    require(isinstance(settle, int) and settle >= 0, 'invalid settling interval')
    begin = active_begin + settle
    end = min(measurement['deadline_ns'],
              *(w['kernel_finished_ns'] for w in measurement['workers']))
    require(begin < end, 'no settled full-cohort sampling interval')
    totals = defaultdict(int)
    buckets = defaultdict(lambda: dict(samples=0, period=0))
    lost = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if re.search(r'LOST|lost events', line, re.I):
            lost.append(line)
            continue
        match = SAMPLE.match(line)
        require(match is not None, 'unrecognized perf sample: ' + line[:240])
        comm, pid, tid, cpu, stamp, period, sample_event, ip, symbol, dso = match.groups()
        require(sample_event == event, 'unexpected sampled event: ' + sample_event)
        stamp_ns, period, cpu, ip = int(Decimal(stamp) * 1_000_000_000), int(period), int(cpu), int(ip, 16)
        require(period > 0, 'zero sampled period')
        totals['client_tree_samples'] += 1
        totals['client_tree_period'] += period
        if comm != 'rb_worker':
            totals['other_client_thread_samples'] += 1
            totals['other_client_thread_period'] += period
            continue
        require(cpu in cpus, 'worker sample outside selected CPU cohort')
        if not begin <= stamp_ns <= end:
            totals['worker_outside_settled_cohort_samples'] += 1
            totals['worker_outside_settled_cohort_period'] += period
            continue
        totals['worker_settled_cohort_samples'] += 1
        totals['worker_settled_cohort_period'] += period
        generated = next((r for r in generated_ranges if r['start'] <= ip < r['end']), None)
        category = ('GENERATED_IMAGE' if generated else 'UNKNOWN' if
                    symbol in ('[unknown]', 'unknown', '0x0') or dso in ('[unknown]', 'unknown')
                    else 'SYMBOL')
        key = (category, symbol, dso)
        buckets[key]['samples'] += 1
        buckets[key]['period'] += period
    require(totals['worker_settled_cohort_samples'] > 0, 'no rb_worker samples inside the settled full cohort')
    denominator = totals['worker_settled_cohort_period']
    return dict(status='LOST_SAMPLES' if lost else 'OBSERVED', event=event,
        clock='CLOCK_MONOTONIC', timestamp_precision_ns=1,
        full_cohort_begin_ns=active_begin, full_cohort_end_ns=end, settle_ns=settle,
        sampled_begin_ns=begin, sampled_end_ns=end,
        totals=dict(totals), lost_event_lines=lost, generated_ranges=generated_ranges,
        interpretation='Flat sampled-period attribution, not elapsed latency or per-function inclusive time; startup/other threads and unknown/JIT ranges remain explicit.',
        hot_paths=[dict(category=key[0], symbol=key[1], dso=key[2],
                        worker_period_share=value['period'] / denominator, **value)
                   for key, value in sorted(buckets.items(), key=lambda item: -item[1]['period'])])


def perf_command(perf, mode, directory, client, *, cpu, events, record_event, frequency):
    prefix = ['taskset', '-c', str(cpu), str(perf)]
    if mode == 'stat':
        return prefix + ['stat', '--no-big-num', '-x', ';', '-o', str(directory / 'perf-stat.csv'),
                         '-e', ','.join(events), '--', *map(str, client)]
    require(mode == 'record', 'unknown profiling mode')
    return prefix + ['record', '--quiet', '--clockid', 'mono', '--sample-cpu',
                     '--strict-freq', '--no-buildid-cache', '--inherit',
                     '-e', record_event, '-F', str(frequency),
                     '-o', str(directory / 'perf.data'), '--', *map(str, client)]


def launch_profiled_client(session, argv, timeout, failure):
    """Separate perf stderr from client JSON; timeout never kills either process."""
    receipt = dict(argv=argv, started_ns=time.monotonic_ns(), timeout_seconds=timeout,
                   state='STARTING', scope='Measured client process and inherited threads only')
    path = session.path / 'perf-command.json'
    with (session.path / 'measure.json').open('w') as output, \
            (session.path / 'perf-command.log').open('w') as errors:
        child = subprocess.Popen(argv, cwd=session.path.parent / 'source',
            stdout=output, stderr=errors, start_new_session=True,
            env=dict(os.environ, LC_ALL='C', PYTHONDONTWRITEBYTECODE='1'))
        receipt.update(pid=child.pid, state='RUNNING')
        save(path, receipt)
        try:
            code = child.wait(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            receipt.update(state='UNKNOWN_DRAIN', error=repr(error))
            save(path, receipt)
            raise failure('TIMEOUT', 'Profiler/client timeout; retain processes, source and provider', unsafe=True) from error
    receipt.update(returncode=code, finished_ns=time.monotonic_ns(), state='EXITED')
    save(path, receipt)
    # A nonzero recorder exit alone cannot establish that its inherited child
    # returned. Preserve objects until the normal client/drain evidence exists.
    if code:
        raise failure('PERF_CLIENT_FAILED', 'Nonzero perf/client exit; drain unproven', unsafe=True)
    return (session.path / 'measure.json').read_text()


def capture_symbols(session):
    for name in ('kallsyms', 'modules'):
        (session.path / name).write_bytes(Path('/proc', name).read_bytes())
    modules = [session.workload_module.stem]
    if session.loaded_kd:
        modules.append('kdlock_km')
    sections = {}
    for module in modules:
        folder = Path('/sys/module') / module / 'sections'
        require(folder.is_dir(), 'module section map unavailable: ' + module)
        sections[module] = {p.name: p.read_text().strip() for p in sorted(folder.iterdir()) if p.is_file()}
        require('.text' in sections[module], 'module text address unavailable: ' + module)
    save(session.path / 'module-sections.json', sections)
    ranges = []
    if session.loaded_kd and session.has_entry():
        publication = session.publication()
        entry = publication['entry']
        image = session.path / 'workspace/daemon' / hex(entry['entry']) / str(entry['tgid']) / 'asm/jit.bin'
        require(digest(image) == publication['images']['jit.bin'], 'published generated image changed')
        ranges.append(dict(start=entry['code'], end=entry['code'] + image.stat().st_size,
                           image_bytes=image.stat().st_size, image_sha256=digest(image),
                           generation=entry['generation'], entry=entry['entry']))
    save(session.path / 'generated-ranges.json', ranges)
    return ranges


def diagnostic_report(runner, out):
    """Do not call ordinary report(): it recalculates eligibility as True."""
    records = []
    for spec in json.loads((out / 'plan.json').read_text()):
        path = out / spec['name'] / 'session.json'
        row = json.loads(path.read_text()) if path.exists() else dict(spec, execution_status='NOT_RUN', drained=False)
        row.update(diagnostic=True, score_eligible=False)
        if runner.valid(row) and not row['functional']:
            m = row['measurement']
            row.update(whole_ops_s=m['completed'] * 1e9 / m['wall_ns'],
                       read_ops_s=m['reads'] * 1e9 / m['wall_ns'],
                       write_ops_s=m['writes'] * 1e9 / m['wall_ns'],
                       peak_ops_s=m['peak']['throughput_ops_s'],
                       execution_class=runner.execution_class(row))
        records.append(row)
    save(out / 'records.json', records)
    save(out / 'summary.json', [])
    parity = dict(status='DIAGNOSTIC', criterion='Diagnostic instrumentation; no performance score or parity acceptance', points=[])
    save(out / 'parity.json', parity)
    return parity


def profiled_session(runner, args, perf, perf_sha):
    class ProfiledSession(runner.RWSession):
        def measure(self):
            if self.loaded_kd:
                before = observations(Path('/sys/module/kdlock_km/parameters'))
                save(self.path / 'observations-before.json', before)
                self.record['profile_observations'] = dict(status='BEFORE_ONLY', before=before)
            else:
                self.record['profile_observations'] = dict(status='NOT_APPLICABLE')
            if args.mode == 'batch':
                require(self.loaded_kd, 'batch diagnostics require KD provider')
                batch_path = Path('/sys/module/kdlock_km/parameters/mutex_batch_stats')
                policy = self.record['provider_mutex_policy']
                batch_before = validate_batch(json.loads(batch_path.read_text()), policy)
                save(self.path / 'batch-before.json', batch_before)
                self.record['batch_diagnostics'] = dict(status='BEFORE_ONLY', before=batch_before)
            elif args.mode == 'pin':
                require(self.loaded_kd, 'pin diagnostics require KD provider')
                pin_path = Path('/sys/module/kdlock_km/parameters/mutex_pin_stats')
                policy = self.record['provider_mutex_policy']
                shift = 6 if args.pin_tsc else 0
                pin_before = validate_pin(json.loads(pin_path.read_text()), policy, shift)
                save(self.path / 'pin-before.json', pin_before)
                self.record['pin_diagnostics'] = dict(status='BEFORE_ONLY', before=pin_before)
            self.save()
            super().measure()
            if self.loaded_kd:
                after = observations(Path('/sys/module/kdlock_km/parameters'))
                delta = observation_delta(before, after)
                save(self.path / 'observations-after.json', after)
                self.record['profile_observations'].update(status='OBSERVED', after=after, delta=delta,
                    scope='Quiescent reads outside perf; after warmup through measured client completion; observational counters do not establish drain')
                self.save()
            if args.mode == 'batch':
                batch_after = validate_batch(json.loads(batch_path.read_text()), policy)
                delta = batch_delta(batch_before, batch_after, self.record['jit_completions'], policy)
                save(self.path / 'batch-after.json', batch_after)
                save(self.path / 'batch-delta.json', delta)
                self.record['batch_diagnostics'].update(status='OBSERVED', after=batch_after, delta=delta,
                    scope='Quiescent pre/post reads after warmup and joined measurement; optional compiled batch observations, no perf process',
                    histogram_bins='0: zero; i>0: [2^(i-1), 2^i-1]',
                    locality='Requester node versus executor node immediately before JIT entry, not whole-body residency',
                    owner_transfer_accounting=('Accepted queued ownership transfer before body completion; this counter does not count completed bodies'
                        if batch_after['schema'] == 3 else 'Unavailable in historical schema 2'),
                    legacy_handoff='Existing refusal-path counter, not total physical-owner handoffs')
                self.record.update(profile_status='OBSERVED', diagnostic=True, score_eligible=False)
                self.save()
            elif args.mode == 'pin':
                pin_after = validate_pin(json.loads(pin_path.read_text()), policy, shift)
                delta = pin_delta(pin_before, pin_after, policy, shift)
                save(self.path / 'pin-after.json', pin_after)
                save(self.path / 'pin-delta.json', delta)
                self.record['pin_diagnostics'].update(status='OBSERVED', after=pin_after, delta=delta,
                    scope='Quiescent pre/post reads after warmup and joined measurement; optional compiled pin observations, no perf process',
                    occupancy_bins='Exact requested-pin occupancy 0..4 before and after selection',
                    consumption='Consumed pins are not returned JIT bodies; native exits and FULL resumes remain separate',
                    tsc_scope='Ordered-TSC current-ACK samples include timestamp overhead and the first ACK load; zero loops do not imply zero latency')
                self.record.update(profile_status='OBSERVED', diagnostic=True, score_eligible=False)
                self.save()

        def run(self, command, log, **kwargs):
            if log != 'measure.json' or args.mode in COMPILED_MODES:
                return super().run(command, log, **kwargs)
            expected = self.path.parent / 'source/bench/rwlock_compare/client.py'
            require(len(command) >= 2 and Path(command[1]) == expected,
                    'profiling wrapper reached an unexpected measured command')
            require(digest(perf) == perf_sha, 'frozen perf tool changed')
            generated_ranges = capture_symbols(self)
            argv = perf_command(perf, args.mode, self.path, command,
                cpu=self.record['collector_cpu'], events=args.events,
                record_event=args.record_event, frequency=args.frequency)
            raw = launch_profiled_client(self, argv, kwargs.get('timeout', 120), runner.Failure)
            try:
                measurement = json.loads(raw)
                require(measurement.get('complete') is True and measurement.get('data_ok') is True,
                        'measured client did not establish complete valid output')
                require(isinstance(measurement.get('completed'), int) and measurement['completed'] > 0,
                        'measured client did not complete any operations')
            except (ValueError, TypeError) as error:
                raise runner.Failure('PROFILE_CLIENT_OUTPUT_INVALID', str(error), unsafe=True) from error
            # RWSession.phase still runs the unchanged full oracle and snapshot.
            # Resolve samples while the matching source/provider stay loaded.
            if args.mode == 'stat':
                result = parse_stat((self.path / 'perf-stat.csv').read_text(), args.events, args.allow_multiplex)
                result['completed_operations'] = measurement['completed']
                for value in result['events'].values():
                    value['reported_unit_per_completed_op'] = value['value'] / measurement['completed']
                save(self.path / 'perf-stat.json', result)
            else:
                for options, name in (
                    (['report', '--stdio', '--no-children', '--sort', 'comm,dso,symbol', '--percent-limit', '0.2'], 'perf-report-all-client.txt'),
                    (['script', '--ns', '--show-lost-events', '-F', 'comm,pid,tid,cpu,time,event,ip,sym,dso,period'], 'perf-samples.txt')):
                    super().run(['taskset', '-c', str(self.record['collector_cpu']), str(perf), *options,
                        '--kallsyms', self.path / 'kallsyms', '-i', self.path / 'perf.data'], name, timeout=60)
                result = summarize_samples((self.path / 'perf-samples.txt').read_text(), measurement,
                    self.record['cpus'], args.record_event, generated_ranges)
                save(self.path / 'perf-worker-summary.json', result)
            self.record.update(profile_status=result['status'], diagnostic=True, score_eligible=False)
            self.save()
            return raw
    return ProfiledSession


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=('stat', 'record', 'batch', 'pin'), required=True)
    p.add_argument('--pin-tsc', action='store_true',
                   help='pin mode only: sample ordered-TSC current ACK latency once per 64 observations')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--source-root', type=Path, default=ROOT)
    p.add_argument('--source-commit', required=True)
    p.add_argument('--perf', type=Path, default=PERF)
    p.add_argument('--profiles', nargs='+', choices=PROFILES,
                   default=['mutex-throughput', 'mutex-locality'])
    p.add_argument('--threads', nargs='+', type=int, choices=(16, 20, 32, 36, 60), default=[16, 36, 60])
    p.add_argument('--backends', nargs='+', choices=('native', 'kdlock'))
    p.add_argument('--frequency', type=int, choices=(199, 499, 997), default=499)
    p.add_argument('--mutex-batch-limit', type=int, default=1024)
    p.add_argument('--mutex-numa-boundary', type=int, default=1024)
    p.add_argument('--record-event', default='cycles:k')
    p.add_argument('--events', nargs='+', default=list(EVENTS))
    p.add_argument('--allow-multiplex', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    kernel_identity.arguments(p)
    return p


def selected_backends(args):
    return args.backends or (['kdlock'] if args.mode in COMPILED_MODES else ['native', 'kdlock'])


def diagnostic_settings(args):
    require(args.mode not in COMPILED_MODES or selected_backends(args) == ['kdlock'],
            args.mode + ' diagnostics support the KD provider only')
    require(not args.pin_tsc or args.mode == 'pin', '--pin-tsc requires --mode pin')
    return dict(mutex_diag={'batch': 1, 'pin': 2}.get(args.mode, 0),
                mutex_pin_tsc_shift=6 if args.pin_tsc else 0)


def runner_arguments(args, profile):
    selected_mutex_policy(args)
    diagnostic_settings(args)
    workload, lines, post = PROFILES[profile]
    return ['--output', str(args.output.resolve() / profile), '--lock-kind', 'mutex',
        '--workloads', workload, '--cachelines', str(lines), '--write-percent', '100',
        '--threads', *map(str, args.threads), '--cpus', *map(str, range(max(args.threads))),
        '--collector-cpu', '63', '--backends', *selected_backends(args), '--repeats', '1',
        '--duration-ms', '2000', '--post-work-rounds', str(post),
        '--mutex-batch-limit', str(args.mutex_batch_limit),
        '--mutex-numa-boundary', str(args.mutex_numa_boundary),
        '--kernel-source', str(args.kernel_source),
        '--kernel-baseline', str(args.kernel_baseline), '--kernel-variant', args.kernel_variant]


def main():
    args = parser().parse_args()
    args.backends = selected_backends(args)
    policy = selected_mutex_policy(args)
    diagnostics = diagnostic_settings(args)
    for values in (args.profiles, args.threads, args.backends, args.events):
        require(values and len(values) == len(set(values)), 'empty or duplicate profile selection')
    require(re.fullmatch(r'[0-9a-f]{40}', args.source_commit), 'record a full source commit')
    require(all(re.fullmatch(r'[A-Za-z0-9_:./=-]+', event) for event in [*args.events, args.record_event]),
            'unsupported event syntax')
    if args.dry_run:
        print(json.dumps({profile: runner_arguments(args, profile) for profile in args.profiles}, indent=2))
        return 0
    require(os.geteuid() == 0 and os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
            os.environ.get('KDLOCK_SNAPSHOT_TAG'),
            'confirmed recovery guest and recorded snapshot tag required')
    root, out = args.source_root.resolve(), args.output.resolve()
    require(str(root).startswith('/root/') and not out.exists() and not out.is_relative_to(root),
            'use the guest checkout and a new external evidence directory')
    path = root / 'bench/rwlock_compare/run.py'
    sys.path.insert(0, str(path.parent))
    module = importlib.util.spec_from_file_location('nano_profile_runner', path)
    runner = importlib.util.module_from_spec(module)
    module.loader.exec_module(runner)
    with open('/run/lock/kdlock-nano.lock', 'w') as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        runner.idle()
        out.mkdir(parents=True)
        perf, tool_sha, events = None, None, []
        if args.mode not in COMPILED_MODES:
            perf = out / 'tools/perf'
            perf.parent.mkdir()
            tool_sha = digest(args.perf)
            shutil.copyfile(args.perf, perf)
            perf.chmod(0o755)
            require(digest(perf) == digest(args.perf) == tool_sha, 'perf changed during retention')
            save(out / 'perf-tool.json', dict(original=str(args.perf), retained=str(perf), sha256=tool_sha,
                version=runner.command([perf, '--version'], out / 'perf-version.txt').strip(),
                sysctls={name: (Path('/proc/sys/kernel') / name).read_text().strip() for name in
                         ('perf_event_paranoid', 'perf_event_max_sample_rate', 'perf_event_mlock_kb', 'perf_event_max_stack')}))
            events = args.events if args.mode == 'stat' else [args.record_event]
            runner.command(['taskset', '-c', '63', perf, 'stat', '--no-big-num', '-x', ';',
                            '-e', ','.join(events), '-o', out / 'perf-capability.csv', '--', '/bin/true'],
                           out / 'perf-capability.log', timeout=30)
            save(out / 'perf-capability.json', parse_stat((out / 'perf-capability.csv').read_text(), events, args.allow_multiplex))
        else:
            save(out / 'perf-tool.json', dict(status='NOT_USED',
                reason='Compiled ' + args.mode + ' observations only; no perf process or PMU counters'))
        frozen = runner.sources()
        save(out / 'source-sha256.json', frozen)
        self_sha = digest(Path(__file__))
        require(frozen['bench/nano/profile.py'] == self_sha, 'driver differs from selected source checkout')
        original_plan, original_build = runner.make_plan, runner.build
        def plan(parsed):
            rows = original_plan(parsed)
            for row in rows:
                row.update(diagnostic=True, score_eligible=False, source_commit=args.source_commit,
                    diagnostic_kind='nano-' + args.mode, diagnostic_mode=args.mode,
                    mutex_batch_diagnostics=args.mode == 'batch',
                    mutex_pin_diagnostics=args.mode == 'pin',
                    mutex_diagnostics_mode=diagnostics['mutex_diag'],
                    mutex_pin_tsc_shift=diagnostics['mutex_pin_tsc_shift'],
                    perf_mode=args.mode if args.mode not in COMPILED_MODES else None,
                    perf_events=events, perf_frequency=args.frequency if args.mode == 'record' else None,
                    perf_binary_sha256=tool_sha, profile_driver_sha256=self_sha,
                    profile_scope=('Compiled ' + args.mode + ' observations around joined measurement; warmup excluded'
                        if args.mode in COMPILED_MODES else 'Measured client including startup/collection; warmup excluded'))
            return rows
        def build(parsed, directory, rows):
            binaries, hashes = original_build(parsed, directory, rows, **diagnostics)
            if perf is not None:
                hashes[str(perf)] = tool_sha
            save(directory / 'binary-sha256.json', hashes)
            return binaries, hashes
        runner.make_plan, runner.build = plan, build
        runner.RWSession = profiled_session(runner, args, perf, tool_sha)
        runner.report = lambda directory: diagnostic_report(runner, directory)
        receipt = dict(diagnostic=True, score_eligible=False, source_commit=args.source_commit,
            driver_sha256=self_sha, mode=args.mode, provider_mutex_policy=policy,
            provider_diagnostics=diagnostics, stages=[], complete=False)
        save(out / 'result.json', receipt)
        for profile in args.profiles:
            require(runner.sources() == frozen and (perf is None or digest(perf) == tool_sha),
                    'frozen inputs changed between profiles')
            require(not (out / 'STOP').exists(), 'STOP requested at drained profile boundary')
            require(shutil.disk_usage(out).free >= 512 * 1024**2, 'storage reserve exhausted')
            argv = runner_arguments(args, profile)
            row = dict(profile=profile, argv=argv, started_ns=time.monotonic_ns(), complete=False)
            receipt['stages'].append(row)
            save(out / 'result.json', receipt)
            code = runner.main(argv)
            row.update(returncode=code, finished_ns=time.monotonic_ns(), complete=code == 0)
            save(out / 'result.json', receipt)
            if code:
                return code
            require(runner.sources() == frozen, 'frozen source changed during profile')
        runner.idle()
        receipt.update(complete=True, final_idle=True)
        save(out / 'result.json', receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
