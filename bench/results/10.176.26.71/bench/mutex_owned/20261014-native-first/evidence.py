#!/usr/bin/env python3
"""Local raw-evidence helpers for the native-first study; no live execution.

Derived from the 20261013 owned report, with ABI4 identity support. The public
entry point and acceptance decisions are in this directory's analyze.py.
"""
import argparse
from collections import defaultdict
import csv
import json
import math
from pathlib import Path
import re
import statistics
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
import study_audit as study
from bench_runtime import FAULT, digest, require, validate_measurement
from experiment_policy import check_jit_evidence, check_kd_parameters, tc_quiescent
from summarize import valid, write_json

POLICY = ('mutex_implementation', 'mutex_entry_ratio_limit',
          'owned_mutex_entry_ratio_limit', 'mutex_routing', 'mutex_acceptance',
          'owned_queue_policy', 'owned_mutex_refill', 'caller_shell', 'cookie_storage', 'cpu_heat_policy',
          'mutex_wait_counter_scope', 'mutex_spin_limit', 'numa_policy',
          'delegation_batch_limit', 'kd_provider_ubsan',
          *study.policy_config.OWNED_CALLER_FIELDS)
EVENTS = ('cycles', 'instructions', 'cache-misses', 'task-clock',
          'context-switches', 'cpu-migrations')
PROFILE_FIELDS = ('native_calls', 'native_slow', 'spin_slow', 'admitted',
                  'declined', 'batches', 'batch_packets', 'owner_samples',
                  'owner_zero', 'owner_changes', 'missed')
OWNED_STATS = ('bodies', 'batches', 'refusals', 'early_releases')


def read(path):
    return json.loads(path.read_text())


def csv_write(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def declared(raw, arguments):
    result = {}
    for argument in arguments:
        label, separator, relative = argument.partition('=')
        require(separator and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', label),
                'expected LABEL=relative-path: ' + argument)
        folder = (raw/relative).resolve()
        require(not Path(relative).is_absolute() and folder.is_relative_to(raw) and
                folder.is_dir() and label not in result, 'invalid/duplicate run: ' + argument)
        result[label] = folder
    return result


def environment(folder):
    env = read(folder/'environment.json')
    require(env['kernel_identity']['ok'] and
            env['kernel_identity']['running_build_id'] == '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960' and
            env['topology']['online_cpus'] == list(range(64)) and
            env['collector_topology']['role_cpus'] == [63] and
            {'nokaslr', 'nopvspin'} <= set(env['cmdline'].split()) and
            '(voluntary)' in env['preemption'], 'kernel/boot/topology differs: ' + str(folder))
    return env


def frozen(folder, verify=True):
    sources, binaries = read(folder/'source-sha256.json'), read(folder/'binary-sha256.json')
    require(study.policy_config.POST_WORK_SOURCE in sources and
            study.policy_config.source_post_work_rounds(folder/'source') == 64,
            'frozen workload is not post64: ' + str(folder))
    if verify:
        for name, sha in sources.items():
            require(digest(folder/'source'/name) == sha, 'source changed: ' + name)
        for name, sha in binaries.items():
            path = (folder/'variants'/name.split('/variants/', 1)[1]
                    if '/variants/' in name else folder/'binaries'/Path(name).name)
            require(digest(path) == sha, 'binary changed: ' + name)
    result = {key + '_sha256': digest(folder/name) for key, name in (
        ('source_manifest', 'source-sha256.json'), ('binary_manifest', 'binary-sha256.json'),
        ('environment', 'environment.json'), ('plan', 'plan.json'))}
    result.update(source_files=len(sources), binaries=len(binaries), post_work_rounds=64)
    if (folder/'pmu-tool.json').exists():
        perf = read(folder/'pmu-tool.json')
        require(binaries.get(perf['path']) == perf['sha256'] and
                perf['scope'] == 'measure client and inherited workers; setup/warmup excluded',
                'perf identity/scope differs')
        result['perf'] = perf
    return result


def log_counts(log, prefix):
    matches = re.findall(re.escape(prefix) + r' ([^\n]+)', log)
    require(len(matches) == 1, 'missing/duplicate receipt: ' + prefix)
    pairs = re.findall(r'(\w+)=(\d+)', matches[0])
    require(len(dict(pairs)) == len(pairs), 'duplicate receipt counter: ' + prefix)
    return {key: int(value) for key, value in pairs}


def parse_profile(log, record):
    counts = log_counts(log, 'kd_mutex_profile:')
    require(set(counts) == set(PROFILE_FIELDS) and counts['missed'] == 0,
            'incomplete lock profile')
    buckets = re.findall(r'kd_mutex_profile histogram: bucket=(\d+) batches=(\d+)', log)
    require(len(buckets) == 12 and {int(k) for k, _ in buckets} == set(range(12)),
            'missing/duplicate batch histogram bucket')
    histogram = {str(int(k)): int(value) for k, value in buckets}
    require(sum(histogram.values()) == counts['batches'], 'histogram batch count differs')
    low = sum(histogram[str(k)] * (1 << (k - 1)) for k in range(1, 12))
    high = sum(histogram[str(k)] * ((1 << k) - 1) for k in range(1, 11))
    require(counts['batch_packets'] >= low and
            (histogram['11'] or counts['batch_packets'] <= high), 'histogram packet bounds differ')
    require(counts['owner_samples'] > 0 and counts['owner_zero'] <= counts['owner_samples'] and
            counts['owner_changes'] <= counts['owner_samples'] - counts['owner_zero'],
            'invalid sampled owner counts')
    require(counts['spin_slow'] == 0, 'unexpected spin diagnostic')
    if record['arm'] == 'native':
        require(counts['native_calls'] >= counts['native_slow'] and
                counts['admitted'] == counts['declined'] == counts['batches'] == 0,
                'Native profile contains KD activity or impossible slow counts')
    if record.get('mutex_implementation') == 'owned-v1':
        owned = log_counts(log, 'kd_mutex_profile owned:')
        owned_fields = {'linux_target_unlocks', 'self_calls', 'self_slow', 'missed'}
        # The ABI4-capable runner stamps this flag on every plan, including
        # profiles with native-first disabled. Earlier frozen profiles retain
        # their original four-counter receipt and cannot count the new helper.
        if 'profile_owned_native_first' in record:
            owned_fields.add('self_wait')
        require(set(owned) == owned_fields and
                counts['native_calls'] == counts['native_slow'] ==
                owned['linux_target_unlocks'] == owned['missed'] == 0,
                'owned profile contains Linux target calls or missed probes')
        counts['owned'] = owned
    counts['batch_histogram'] = histogram
    require(record['lock_profile'] == counts, 'saved profile differs from kernel receipt')
    return counts


def parse_pmu(path):
    events = {}
    for fields in csv.reader(path.read_text().splitlines(), delimiter=';'):
        if not fields or not fields[0].strip() or fields[0].lstrip().startswith('#'):
            continue
        require(len(fields) >= 5 and fields[2] in EVENTS and fields[2] not in events,
                'short, duplicate or unexpected PMU row')
        value, runtime, running = map(float, (fields[0], fields[3], fields[4]))
        require(all(math.isfinite(n) for n in (value, runtime, running)) and
                value >= 0 and runtime > 0 and running == 100,
                'unsupported, invalid or multiplexed PMU event')
        require(fields[1] == ('msec' if fields[2] == 'task-clock' else ''), 'PMU unit differs')
        events[fields[2]] = dict(value=value, unit=fields[1], event_runtime_ns=runtime,
            running_pct=running, reported_metric=fields[5] if len(fields) > 5 else '',
            reported_metric_unit=fields[6] if len(fields) > 6 else '')
    require(set(events) == set(EVENTS) and events['task-clock']['value'] > 0,
            'missing PMU events or CPU time')
    return events


def audit_backend(folder, record, log, diagnostic):
    path, completed = folder/record['name'], record['measurement']['completed']
    arm, owned = record['arm'], record.get('mutex_implementation') == 'owned-v1'
    require(read(path/'drain.counts.json')['active'] == 0, 'active workers in final drain receipt')
    if arm == 'native':
        require(record['jit_bodies'] == record['delegated_bodies'] == 0 and
                record['execution_class'] == 'NATIVE', 'Native execution identity differs')
        return {}
    if arm == 'tclock':
        for key in ('tclock_before', 'tclock_after', 'tclock_drained'):
            params = record[key]
            tc_quiescent(params, 'mutex')
            require(params['target_lock'] == record['layout']['lock_addr'] and
                    params['komb_batch_size'] == 1024, 'TCLock parameters differ')
        before, after = record['tclock_before'], record['tclock_after']
        require(after == record['tclock_drained'] and
                all(after[k] >= before[k] for k in ('delegated', 'batches', 'parks')) and
                after['delegated'] - before['delegated'] == record['delegated_bodies'] and
                0 <= record['delegated_bodies'] <= completed and
                record['delegation_share'] == record['delegated_bodies']/completed and
                record['jit_bodies'] == 0, 'TCLock body/drain evidence differs')
        return {}
    require(arm == 'kdlock' and record['lock_kind'] == 'mutex', 'unsupported backend')
    require(record['published_before'] == record['published_after'] and
            record['retired'] == dict(state=2, modules=0, frames=0, writers=0),
            'changed publication or incomplete source retirement')
    pub, kind = record['published_before'], 3 if owned else 2
    entry = pub['entry']
    require(entry['lock_kind'] == kind and entry['entry_abi'] == record.get('entry_abi', 2) and
            entry['pid'] == entry['status'] == 0 and entry['code'] > 0,
            'mutex publication family/ABI differs')
    image_dir = path/'workspace/daemon'/hex(entry['entry'])/str(entry['tgid'])/'asm'
    for name, sha in pub['images'].items():
        require(digest(image_dir/name) == sha, 'JIT artifact changed: ' + name)
    require(record['jit_after'] - record['jit_before'] == record['jit_bodies'] and
            0 <= record['jit_bodies'] <= completed and
            record['jit_share'] == record['jit_bodies']/completed and
            record['delegated_bodies'] == record['jit_bodies'], 'KD returned-body evidence differs')
    classified = dict(record)
    check_jit_evidence(classified)
    require(all(record.get(k) == classified[k] for k in ('execution_class', 'jit_acceptance')),
            'KD execution classification differs')
    check_kd_parameters(record['parameters'], record, record['layout']['lock_addr'])
    for key in ('result_schedule_calls', 'result_wakes', 'gate_wait_calls'):
        require(record['mutex_wait_after'][key] - record['mutex_wait_before'][key] ==
                record['mutex_wait_delta'][key] >= 0, 'mutex wait delta differs')
    stats = log_counts(log, 'kd_mutex stats:')
    require(stats['active_waiters'] == stats['reserved_nodes'] == stats['frame_failure'] == 0 and
            stats['origin_acquires'] == stats['origin_releases'], 'legacy queue/frame/owner imbalance')
    tasks = log_counts(log, 'kd_mutex tasks:')
    require(tasks['active_tasks'] == 0, 'task routing references did not drain')
    acks = log_counts(log, 'kd_native stats:')
    require(acks['started'] == acks['completed'], 'native continuations did not drain')
    result = dict(legacy_lifetime=stats, task_lifetime=tasks, native_ack_lifetime=acks)
    if owned:
        study.require_owned_identity(record)
        if diagnostic and 'owned_queue_policy' not in record:
            require('owned_queue_policy' not in
                    (folder/'source/bench/tclock_compare/run.py').read_text(),
                    'queue identity omitted despite frozen runner support')
        else:
            require(record.get('owned_queue_policy') ==
                    ('bounded_fifo_refill' if record.get('owned_mutex_refill', False) else 'finite_fifo'),
                    'owned queue policy differs from refill control')
        layout = record['layout']
        require(layout['lock_bytes'] == 32 and layout['line_bytes'] == 64 and
                layout['lock_addr'] % 64 == layout['data_addr'] % 64 == 0,
                'owned object layout differs')
        observations = log_counts(log, 'kd_owned_mutex:')
        require(set(observations) == set(OWNED_STATS) and
                observations == record['owned_observations'] and
                observations['bodies'] >= record['jit_bodies'] and
                observations['early_releases'] == 0 and record['mutex_wait_delta']['gate_wait_calls'] == 0,
                'owned plain body/wait observations differ')
        result['owned_lifetime'] = observations
    return result


def audit_group(label, folder, diagnostic):
    plan = read(folder/'plan.json')
    require(plan and len({s['name'] for s in plan}) == len(plan), 'empty/duplicate plan: ' + label)
    kinds = {s['lock_kind'] for s in plan}
    require(len(kinds) == 1 and kinds <= {'mutex', 'spin'}, 'mixed/unknown lock families')
    kind = next(iter(kinds))
    if kind == 'spin':
        require(not diagnostic and {s['arm'] for s in plan} == {'native'},
                'spin evidence is restricted to the uninstrumented Native qspinlock control')
    maintained = not diagnostic and kind == 'mutex'
    loaded = {r['name']: r for r in study.load_run(folder, 64)} if maintained else None
    receipt = frozen(folder, verify=not maintained)
    environment(folder)
    aggregate = read(folder/'records.json')
    require(len(aggregate) == len(plan) and {r['name'] for r in aggregate} == {s['name'] for s in plan},
            'missing/duplicate aggregate samples')
    aggregate = {r['name']: r for r in aggregate}
    rows, raw_hashes = [], {}
    for spec in plan:
        path = folder/spec['name']
        record = loaded[spec['name']] if maintained else read(path/'session.json')
        require(all(record.get(k) == v for k, v in spec.items()), 'record differs from plan')
        require(all(aggregate[spec['name']].get(k) == v for k, v in record.items()),
                'aggregate differs from session')
        require(valid(record) and aggregate[spec['name']]['score_eligible'] is (not diagnostic),
                'invalid/drained/score identity: ' + str(path))
        study.require_post_work_metadata(record, 64)
        flags = any(record.get(k, False) for k in ('pmu', 'perf_record', 'profile_lock'))
        control = record.get('mutex_routing') in ('self', 'native')
        # A routing experiment also marks its paired Native control unscored.
        # Native has no KD routing field, so verify its explicit planned partner.
        paired_control = record['arm'] == 'native' and any(
            s['arm'] == 'kdlock' and s['threads'] == record['threads'] and
            s['repeat'] == record['repeat'] and s.get('diagnostic') is True and
            s.get('mutex_routing') in ('self', 'native') for s in plan)
        require(record.get('diagnostic', False) is diagnostic and
                (flags or control or paired_control) is diagnostic and
                not record.get('functional', False) and not record.get('owned_mutex_force_full', False),
                'diagnostic or functional identity differs')
        require(record['cachelines'] == 1 and record['workload'] == 'cacheline' and
                record['scenario'] == 'plain' and record['cpus'] == list(range(record['threads'])) and
                record['cpu_nodes'] == [int(cpu >= 32) for cpu in record['cpus']] and
                record['collector_cpu'] == 63 and record['duration_ms'] == 2000 and
                record['peak_window_ms'] == record['peak_settle_ms'] == 300 and
                record['sample_ms'] == 10 and record['warmup_iterations_per_worker'] == 48000,
                'c01 geometry/timing differs')
        raw = read(path/'measure.json')
        peak = validate_measurement(raw, record, record['iterations'])
        require(dict(raw, peak=peak) == record['measurement'], 'raw measurement/peak differs')
        log = (path/'kernel.log').read_text()
        require(not FAULT.search(log), 'kernel error: ' + str(path))
        record = dict(record, _backend=audit_backend(folder, record, log, diagnostic))
        if record.get('profile_lock'):
            record['_profile'] = parse_profile(log, record)
            require(read(path/'profile-drain.counts.json')['active'] == 0, 'profile workers active')
        if record.get('pmu'):
            require('perf' in receipt, 'missing PMU tool receipt')
            record['_pmu'] = parse_pmu(path/'pmu.csv')
        if record.get('perf_record'):
            require('perf' in receipt and (path/'perf.data').stat().st_size > 0 and
                    (path/'kallsyms').stat().st_size > 0 and (path/'modules').stat().st_size > 0,
                    'missing raw perf data/symbol maps')
            report, raw_samples = (path/'perf-report.txt').read_text(), (path/'perf-samples.txt').read_text()
            require('# Total Lost Samples: 0' in report and 'PERF_RECORD_LOST' not in raw_samples and
                    'cycles:k' in report, 'lost/incorrect perf samples')
            record['_flat'] = [dict(percent=float(m[1]), command=m[2], dso=m[3], symbol=m[4])
                for line in report.splitlines()
                if (m := re.match(r'\s*(\d+\.\d+)%\s+(\S+)\s+(\S+)\s+\[k\]\s+(\S+)', line))]
            require(record['_flat'], 'empty resolved kernel profile')
        artifacts = ['session.json', 'measure.json', 'kernel.log', 'drain.counts.json']
        if record.get('profile_lock'):
            artifacts.append('profile-drain.counts.json')
        if record.get('pmu'):
            artifacts.append('pmu.csv')
        if record.get('perf_record'):
            artifacts += ['perf.data', 'perf-report.txt', 'perf-samples.txt', 'kallsyms', 'modules']
        raw_hashes[record['name']] = {name: digest(path/name) for name in artifacts}
        rows.append(record)
    kd_policies = {tuple(r.get(k, 'unrecorded') for k in POLICY) for r in rows if r['arm'] == 'kdlock'}
    require(len(kd_policies) <= 1, 'mixed KD policies within one declared run')
    receipt.update(label=label, sessions=len(rows), diagnostic=diagnostic, score_eligible=not diagnostic,
        lock_kind=kind, arms=sorted({r['arm'] for r in rows}), worker_counts=sorted({r['threads'] for r in rows}),
        repeats=sorted({r['repeat'] for r in rows}), source_and_raw_verified=True,
        every_worker_progress=True, drained=True,
        kd_policy=dict(zip(POLICY, next(iter(kd_policies)))) if kd_policies else None,
        sample_artifact_sha256=raw_hashes,
        historical_owned_queue_policy_unrecorded=any(r.get('mutex_implementation') == 'owned-v1' and
            'owned_queue_policy' not in r for r in rows))
    return rows, receipt


def identity(label, record):
    return dict(group=label, sample=record['name'], arm=record['arm'], lock_kind=record['lock_kind'],
        implementation=(record.get('mutex_implementation', 'legacy') if record['arm'] == 'kdlock'
                        else 'native_qspinlock' if record['lock_kind'] == 'spin' else record['arm']),
        threads=record['threads'], repeat=record['repeat'], post_work_rounds=64,
        diagnostic=record['diagnostic'], score_eligible=not record['diagnostic'])


def summarize(label, records, tables):
    groups = defaultdict(list)
    for record in records:
        ident, m = identity(label, record), record['measurement']
        shares = [w['completed']/m['completed'] for w in m['workers']]
        row = dict(**ident, whole_mops=m['completed']*1e3/m['wall_ns'],
            peak_mops=m['peak']['throughput_ops_s']/1e6, completed=m['completed'],
            worker_cpu_ns_per_op=m['worker_cpu_ns']/m['completed'],
            worker_cpu_equivalents=m['worker_cpu_ns']/m['wall_ns'],
            worker_share_min=min(shares), worker_share_max=max(shares),
            jit_bodies=record['jit_bodies'], jit_share=record['jit_share'],
            delegated_bodies=record.get('delegated_bodies'), delegation_share=record.get('delegation_share'),
            execution_class=record.get('execution_class', 'TCLOCK_NATIVE_DELEGATION'),
            jit_acceptance=record.get('jit_acceptance', 'NOT_APPLICABLE'),
            **{k: record.get(k, 'unrecorded') for k in POLICY})
        for worker, share in zip(m['workers'], shares):
            tables['workers'].append(dict(**ident, **worker, share=share))
        if record['arm'] != 'native':
            b = dict(**ident, measured_returned_bodies=record['delegated_bodies'],
                     measured_delegation_share=record['delegation_share'])
            if record['arm'] == 'tclock':
                before, after = record['tclock_before'], record['tclock_after']
                batches, bodies = after['batches']-before['batches'], record['delegated_bodies']
                b.update(scope='measurement', parks=after['parks']-before['parks'])
            else:
                stats = record['_backend'].get('owned_lifetime', record['_backend']['legacy_lifetime'])
                batches = stats['batches'] if 'batches' in stats else stats['combiner']
                bodies = stats['bodies'] if 'bodies' in stats else stats['jit_success']
                b.update(scope='provider_lifetime_including_warmup', **record['mutex_wait_delta'],
                         wait_counter_scope=record.get('mutex_wait_counter_scope', 'legacy_mutex_waits'))
            b.update(batches=batches, bodies=bodies, bodies_per_batch=bodies/batches if batches else None)
            tables['batches'].append(b)
        if '_pmu' in record:
            events = record['_pmu']
            row.update(effective_ghz=events['cycles']['value']/events['task-clock']['value']/1e6,
                ipc=events['instructions']['value']/events['cycles']['value'] if events['cycles']['value'] else None,
                pmu_cpu_equivalents=events['task-clock']['value']*1e6/m['wall_ns'])
            for name, event in events.items():
                tables['pmu'].append(dict(**ident, event=name, **event,
                    value_per_completed_op=event['value']/m['completed']))
        if '_flat' in record:
            tables['flat-profiles'].extend(dict(**ident, **r, lost_samples=0) for r in record['_flat'])
        if '_profile' in record:
            p = record['_profile']
            admitted = p['admitted']+p['declined']
            profile = dict(**ident, **{k: p[k] for k in PROFILE_FIELDS},
                native_fast=p['native_calls']-p['native_slow'] if record['arm'] == 'native' else None,
                admission_fraction=p['admitted']/admitted if admitted else None,
                mean_batch=p['batch_packets']/p['batches'] if p['batches'] else None,
                owner_zero_fraction=p['owner_zero']/p['owner_samples'],
                owner_change_fraction=p['owner_changes']/p['owner_samples'])
            profile.update({'owned_' + k: v for k, v in p.get('owned', {}).items()})
            tables['lock-profiles'].append(profile)
            for bucket in range(12):
                tables['batch-histograms'].append(dict(**ident, bucket=bucket,
                    batches=p['batch_histogram'][str(bucket)], min_packets=1 << (bucket-1) if bucket else 0,
                    max_packets=None if bucket == 11 else (1 << bucket)-1))
        tables['samples'].append(row)
        groups[record['threads'], record['arm']].append((record, row))
    for (threads, arm), cohort in sorted(groups.items()):
        records, samples = zip(*cohort)
        if not records[0]['diagnostic']:
            study.metrics(records)  # Exactly three distinct complete rounds.
        whole, peak = [r['whole_mops'] for r in samples], [r['peak_mops'] for r in samples]
        tables['statistics'].append(dict(group=label, lock_kind=records[0]['lock_kind'], arm=arm,
            implementation=samples[0]['implementation'], threads=threads, sessions=len(samples),
            diagnostic=records[0]['diagnostic'], score_eligible=not records[0]['diagnostic'],
            whole_min_mops=min(whole), whole_median_mops=statistics.median(whole), whole_max_mops=max(whole),
            whole_spread_pct=100*(max(whole)-min(whole))/statistics.median(whole),
            peak_min_mops=min(peak), peak_median_mops=statistics.median(peak), peak_best_mops=max(peak),
            peak_spread_pct=100*(max(peak)-min(peak))/statistics.median(peak),
            worker_cpu_ns_per_op_median=statistics.median(r['worker_cpu_ns_per_op'] for r in samples),
            worker_share_min=min(r['worker_share_min'] for r in samples),
            worker_share_max=max(r['worker_share_max'] for r in samples),
            largest_worker_share_median=statistics.median(r['worker_share_max'] for r in samples),
            jit_bodies_min=min(r['jit_bodies'] for r in samples),
            jit_share_median=statistics.median(r['jit_share'] for r in samples),
            delegation_share_median=statistics.median(r['delegation_share'] for r in samples),
            execution_classes=';'.join(sorted({r['execution_class'] for r in samples})),
            **{k: records[0].get(k, 'unrecorded') for k in POLICY}))


def acceptance(runs, folders, baseline_label, confirmations):
    result = dict(target_reached=False, selected_default=None, baseline=baseline_label,
        acceptance='97% separately for median whole-run and best valid warmed peak; higher-thread returned JIT required',
        confirmations=list(confirmations), trials={}, missing_gates=[])
    baseline = runs.get(baseline_label)
    if not baseline:
        result['missing_gates'].append('No declared baseline run')
        return result
    require({r['lock_kind'] for r in baseline} == {'mutex'} and
            {r.get('mutex_implementation', 'legacy') for r in baseline if r['arm'] == 'kdlock'} == {'legacy'},
            'baseline must be freshly measured legacy KD and Native mutex')
    baseline_complete = all(len([r for r in baseline if r['threads'] == t and r['arm'] == arm]) == 3
                            for t in study.GRID for arm in ('native', 'kdlock'))
    if not baseline_complete:
        result['missing_gates'].append('Baseline does not cover three rounds of the full primary/regression grid')
    for label, rows in runs.items():
        if label == baseline_label or not any(r['arm'] == 'kdlock' for r in rows):
            continue
        counts = {r['threads'] for r in rows if r['arm'] == 'kdlock'}
        paired = all(len([r for r in rows if r['arm'] == 'native' and r['threads'] == t]) == 3
                     for t in counts & set(study.PRIMARY))
        if not baseline_complete or not paired:
            result['trials'][label] = dict(verdict='INCOMPLETE', reason='missing baseline grid or paired Native controls')
            continue
        result['trials'][label] = study.evaluate(baseline, rows)
    if not result['trials']:
        result['missing_gates'].append('No candidate screen has been declared')
    if len(confirmations) != 2:
        result['missing_gates'].append('Two independent fresh confirmation blocks have not been declared')
        return result
    require(len(set(confirmations)) == 2 and all(c in runs for c in confirmations),
            'confirmation labels must identify two distinct declared scored runs')
    screens = [(label, trial) for label, trial in result['trials'].items()
               if label not in confirmations and trial['verdict'] == 'PASS']
    if not screens:
        result['missing_gates'].append('No complete passing screen')
        return result
    def selection_identity(label):
        return {tuple(r.get(key, 'unrecorded') for key in POLICY if key not in
                      ('mutex_entry_ratio_limit', 'owned_mutex_entry_ratio_limit'))
                for r in runs[label] if r['arm'] == 'kdlock'}
    identities = [selection_identity(label) for label in confirmations]
    require(len(identities[0]) == 1 and identities[0] == identities[1],
            'confirmation implementation/queue/caller policies differ')
    screens = [(label, trial) for label, trial in screens
               if selection_identity(label) == identities[0]]
    if not screens:
        result['missing_gates'].append('No passing screen matches the confirmation implementation/queue policy')
        return result
    chosen, screen = min(screens, key=lambda pair: pair[1]['threshold'])
    seen = set()
    for label, rows in runs.items():
        if label not in confirmations:
            seen.update(study.sample_identities(rows))
    for label in confirmations:
        study.require_fresh(runs[label], seen)
        require(read(folders[label]/'source-sha256.json') == read(folders[chosen]/'source-sha256.json'),
                'confirmation source differs from selected screen')
    ok = all(result['trials'][label].get('verdict') == 'PASS' and
             result['trials'][label].get('implementation') == screen['implementation'] and
             result['trials'][label].get('threshold') == screen['threshold'] for label in confirmations)
    result.update(selected_screen=chosen, target_reached=ok,
                  selected_default=screen['threshold'] if ok else None)
    if not ok:
        result['missing_gates'].append('Both confirmation blocks must independently pass every gate at the selected threshold')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--runs', nargs='+', default=[], metavar='LABEL=PATH')
    parser.add_argument('--diagnostics', nargs='+', default=[], metavar='LABEL=PATH')
    parser.add_argument('--baseline-label', default='baseline')
    parser.add_argument('--confirmations', nargs=2, default=[], metavar='LABEL')
    args = parser.parse_args()
    raw = args.raw.resolve()
    scored, diagnostics = declared(raw, args.runs), declared(raw, args.diagnostics)
    require(not (set(scored) & set(diagnostics)) and (scored or diagnostics), 'duplicate/empty run labels')
    folders = {**scored, **diagnostics}
    require(len(set(folders.values())) == len(folders), 'same folder declared under multiple labels')
    tables = {name: [] for name in ('statistics', 'samples', 'workers', 'batches', 'pmu',
                                   'flat-profiles', 'lock-profiles', 'batch-histograms')}
    receipts, runs, seen = {}, {}, set()
    for label, folder in folders.items():
        rows, receipt = audit_group(label, folder, label in diagnostics)
        identities = {(r['lock_kind'], r['arm'], r['threads'], r['measurement']['started_ns'],
                       r['measurement']['finished_ns']) for r in rows}
        require(len(identities) == len(rows) and not seen.intersection(identities), 'reused sample identity')
        seen.update(identities)
        receipt['path'] = str(folder.relative_to(raw))
        receipts[label] = receipt
        if label in scored:
            runs[label] = rows
        summarize(label, rows, tables)
    decision = acceptance(runs, folders, args.baseline_label, args.confirmations)
    undeclared = []
    for plan in sorted((raw/'bench').glob('*/plan.json')):
        if plan.parent.resolve() not in folders.values():
            specs = read(plan)
            undeclared.append(dict(path=str(plan.parent.relative_to(raw)), planned=len(specs),
                existing_sessions=sum((plan.parent/s['name']/'session.json').exists() for s in specs),
                audited=False))
    coverage = dict(schema=1, passed=True, post_work_rounds=64, runs=receipts,
        performance_sessions=sum(receipts[k]['sessions'] for k in scored),
        diagnostic_sessions=sum(receipts[k]['sessions'] for k in diagnostics),
        undeclared_runs=undeclared, command=sys.argv,
        analyzer_sha256=digest(Path(__file__)),
        policy_auditor_sha256=digest(Path(__file__).with_name('experiment_policy.py')),
        study_auditor_sha256=digest(Path(__file__).with_name('study_audit.py')),
        generic_validator_sha256={name: digest(ROOT/'bench/spin_cacheline'/name)
                                  for name in ('bench_runtime.py', 'summarize.py')},
        limits=['Declared groups only; undeclared preflight failures and test evidence are retained separately.',
                'Source/ELF/artifact hashes establish internal consistency, not independent execution authentication.',
                'Different group/source identities are never pooled into a statistical cohort.',
                'Diagnostic rates are unscored; probes and perf can substantially change execution.',
                'Owner sampling is not exact acquisition streaks or cacheline-transfer measurement.',
                'PMU covers the measured client and inherited workers; effective GHz is aggregate cycles/task-clock.',
                'Generic cache misses do not isolate coherence; flat samples largely include waiting workers.',
                'Governor, physical-host thermals and frequency control require separate environment receipts.',
                'Protocol/unit/live correctness validation is recorded separately by the study owner.'])
    # Publish only after every declared sample and acceptance dependency passes.
    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        csv_write(args.out/(name+'.csv'), rows)
    write_json(args.out/'coverage.json', coverage)
    write_json(args.out/'acceptance.json', decision)
    print(json.dumps(dict(passed=True, performance_sessions=coverage['performance_sessions'],
        diagnostic_sessions=coverage['diagnostic_sessions'], target_reached=decision['target_reached'],
        output=str(args.out))))


if __name__ == '__main__':
    raise SystemExit('Use analyze.py; evidence.py contains shared offline audit helpers.')
