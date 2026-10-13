#!/usr/bin/env python3
"""Audit frozen post8 mutex diagnostics offline; never produce acceptance scores.

Default grids: profile Native/KD at 2,4,16,28,32,60 workers; PMU Native/TC/KD
at 1,2,4,16,28,32,60. --group replaces these with explicitly declared grids.
--candidate-pmu adds a KD-only six-count group. Every cohort has repeat zero.
All inputs are read-only; output filenames begin with diagnostics.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT / 'bench/tclock_compare'))
import mutex_study as study
from bench_runtime import FAULT, digest, require, validate_measurement
from session import check_kd_parameters, tc_quiescent
from summarize import valid, write_json

COUNTS = (2, 4, 16, 28, 32, 60)
EVENTS = ('cycles', 'instructions', 'cache-misses', 'task-clock',
          'context-switches', 'cpu-migrations')
PROFILE_FIELDS = ('native_calls', 'native_slow', 'spin_slow', 'admitted',
                  'declined', 'batches', 'batch_packets', 'owner_samples',
                  'owner_zero', 'owner_changes', 'missed')
CONTROL = dict(mutex_entry_ratio_limit=256, mutex_routing='adaptive',
               mutex_acceptance='adaptive-performance', mutex_frame_reuse=False,
               mutex_native_epoch_ms=0, mutex_native_probe_ms=1,
               mutex_lazy_save=False, mutex_node_locality=False,
               mutex_preflight=False, mutex_native_epoch_cache=False,
               mutex_native_epoch_cross_node=False)
DEFAULTS = [('stage2-profile-control', 'profile', ('native', 'kdlock'), COUNTS),
            ('stage2-pmu-control', 'pmu', ('native', 'tclock', 'kdlock'), (1, *COUNTS))]


def read(path):
    return json.loads(path.read_text())


def natural(value):
    return type(value) is int and value >= 0


def csv_write(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w') as output:
        writer = csv.DictWriter(output, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def frozen(folder, mode):
    sources = read(folder/'source-sha256.json')
    require(study.run.POST_WORK_SOURCE in sources, 'post-work header is not hashed')
    for name, sha in sources.items():
        require(digest(folder/'source'/name) == sha, 'changed source: ' + name)
    require(study.run.source_post_work_rounds(folder/'source') == 8,
            'diagnostics require the frozen eight-round workload')
    binaries = read(folder/'binary-sha256.json')
    for name, sha in binaries.items():
        path = (folder/'variants'/name.split('/variants/', 1)[1]
                if '/variants/' in name else folder/'binaries'/Path(name).name)
        require(digest(path) == sha, 'changed binary: ' + name)
    env = read(folder/'environment.json')
    require(env['kernel_identity']['ok'] and
            env['kernel_identity']['running_build_id'] == '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960' and
            env['topology']['online_cpus'] == list(range(64)) and
            env['collector_topology']['role_cpus'] == [63] and
            {'nokaslr', 'nopvspin'} <= set(env['cmdline'].split()) and
            '(voluntary)' in env['preemption'], 'kernel/boot/topology differs')
    result = dict(source_manifest_sha256=digest(folder/'source-sha256.json'),
                  binary_manifest_sha256=digest(folder/'binary-sha256.json'),
                  environment_sha256=digest(folder/'environment.json'),
                  plan_sha256=digest(folder/'plan.json'), source_files=len(sources),
                  binaries=len(binaries), post_work_rounds=8)
    if mode == 'pmu':
        perf = read(folder/'pmu-tool.json')
        require(binaries.get(perf['path']) == perf['sha256'] and
                perf['scope'] == 'measure client and inherited workers; setup/warmup excluded',
                'PMU tool identity/scope differs')
        result['perf'] = perf
    return result


def parse_profile(log, arm):
    lines = re.findall(r'kd_mutex_profile: ([^\n]+)', log)
    require(len(lines) == 1, 'missing or duplicate profiler receipt')
    pairs = re.findall(r'(\w+)=(\d+)', lines[0])
    require(len(pairs) == len(PROFILE_FIELDS) and {k for k, _ in pairs} == set(PROFILE_FIELDS),
            'profiler field identity differs')
    counts = {key: int(value) for key, value in pairs}
    buckets = re.findall(r'kd_mutex_profile histogram: bucket=(\d+) batches=(\d+)', log)
    require(len(buckets) == 12 and {int(k) for k, _ in buckets} == set(range(12)),
            'missing or duplicate histogram bucket')
    histogram = {str(int(k)): int(v) for k, v in buckets}
    require(counts['missed'] == 0 and counts['spin_slow'] == 0 and
            sum(histogram.values()) == counts['batches'], 'missed or inconsistent mutex profile')
    minimum = sum(histogram[str(k)] * (1 << (k - 1)) for k in range(1, 12))
    maximum = sum(histogram[str(k)] * ((1 << k) - 1) for k in range(1, 11))
    require(counts['batch_packets'] >= minimum and
            (histogram['11'] or counts['batch_packets'] <= maximum), 'batch histogram bounds differ')
    require(counts['owner_samples'] > 0 and counts['owner_zero'] <= counts['owner_samples'] and
            counts['owner_changes'] <= counts['owner_samples'] - counts['owner_zero'],
            'invalid owner samples')
    if arm == 'native':
        require(counts['native_calls'] >= counts['native_slow'] and
                counts['admitted'] == counts['declined'] == counts['batches'] == 0,
                'Native profile contains KD activity or impossible call counts')
    return dict(**counts, batch_histogram=histogram)


def parse_pmu(path):
    events = {}
    for fields in csv.reader(path.read_text().splitlines(), delimiter=';'):
        if not fields or not fields[0].strip() or fields[0].lstrip().startswith('#'):
            continue
        require(len(fields) >= 5, 'short PMU row')
        name = fields[2].strip()
        require(name in EVENTS and name not in events, 'unexpected or duplicate PMU event: ' + name)
        try:
            value, runtime, running = map(float, (fields[0], fields[3], fields[4]))
        except ValueError as error:
            raise ValueError('unsupported/unavailable PMU event: ' + name) from error
        require(all(math.isfinite(n) for n in (value, runtime, running)) and
                value >= 0 and runtime > 0 and running == 100,
                'invalid or multiplexed PMU event: ' + name)
        unit = fields[1].strip()
        require(unit == ('msec' if name == 'task-clock' else ''), 'unexpected PMU unit')
        events[name] = dict(value=value, unit=unit, event_runtime_ns=runtime,
                            running_pct=running,
                            reported_metric=fields[5].strip() if len(fields) > 5 else '',
                            reported_metric_unit=fields[6].strip() if len(fields) > 6 else '')
    require(set(events) == set(EVENTS) and events['task-clock']['value'] > 0 and
            events['cycles']['value'] > 0, 'incomplete PMU events or zero CPU time/cycles')
    return events


def verify_record(folder, spec, aggregate, mode):
    path = folder/spec['name']
    record = read(path/'session.json')
    require(all(record.get(k) == v for k, v in spec.items()), 'session differs from declared plan')
    require(all(aggregate.get(k) == v for k, v in record.items()), 'aggregate differs from session')
    for item in (spec, record, aggregate):
        require(type(item.get('post_work_rounds')) is int and item['post_work_rounds'] == 8,
                'explicit post8 metadata missing or different')
        require(item.get('diagnostic') is True and item.get('profile_lock') is (mode == 'profile') and
                item.get('pmu') is (mode == 'pmu') and item.get('perf_record') is False and
                not item.get('functional', False), 'diagnostic mode identity differs')
    require(aggregate.get('score_eligible') is False and
            record.get('score_eligible', False) is False and valid(record),
            'invalid, undrained, or score-eligible diagnostic')
    require(record['lock_kind'] == 'mutex' and record['workload'] == 'cacheline' and
            record['cachelines'] == 1 and record['scenario'] == 'plain' and
            record['api_mode'] == 'direct' and record['cpus'] == list(range(record['threads'])) and
            record['cpu_nodes'] == [int(cpu >= 32) for cpu in record['cpus']] and
            record['collector_cpu'] == 63 and record['duration_ms'] == 2000 and
            record['warmup_policy'] == 'all_workers' and
            record['warmup_iterations_per_worker'] == 48000 and record['warmup_pause_seconds'] == 0 and
            record['peak_settle_ms'] == record['peak_window_ms'] == 300 and record['sample_ms'] == 10 and
            record['measurement_mode'] == 'timed_peak' and record['iterations'] == 100000,
            'diagnostic workload/measurement geometry differs')
    raw = read(path/'measure.json')
    peak = validate_measurement(raw, record, record['iterations'])
    require(dict(raw, peak=peak) == record['measurement'], 'saved measurement differs from raw data')
    log = (path/'kernel.log').read_text()
    require(not FAULT.search(log), 'diagnostic kernel error')
    drain = read(path/'drain.counts.json')
    require(drain['active'] == 0 and drain['values'] == raw['after'], 'incomplete or changed drain')
    completed = raw['completed']
    if record['arm'] == 'kdlock':
        require(record['mutex_wait_mode'] == 'blocking' and record['mutex_spin_limit'] == 4096 and
                record['numa_policy'] == 'on' and record['delegation_batch_limit'] == 1024 and
                record['kd_provider_ubsan'] == 'off', 'KD build/wait policy differs')
        require(set(CONTROL) <= set(record), 'missing explicit KD policy fields')
        check_kd_parameters(record['parameters'], record, record['layout']['lock_addr'])
        # Keep experimental identities explicit even after the live runner and
        # its baseline parameter helper stop exposing these rejected policies.
        for key in ('mutex_frame_reuse', 'mutex_native_epoch_ms', 'mutex_native_probe_ms',
                    'mutex_native_epoch_cache', 'mutex_native_epoch_cross_node'):
            value = record[key]
            expected = ('Y' if value else 'N') if type(value) is bool else str(value)
            require(record['parameters'].get(key) == expected, 'frozen KD parameter differs: ' + key)
        require(record['published_before'] == record['published_after'] and
                record['retired'] == dict(state=2, modules=0, frames=0, writers=0),
                'publication changed or source retirement incomplete')
        pub = record['published_before']
        images = path/'workspace/daemon'/hex(pub['entry']['entry'])/str(pub['entry']['tgid'])/'asm'
        for name, sha in pub['images'].items():
            require(digest(images/name) == sha, 'changed JIT image: ' + name)
        require(natural(record['jit_bodies']) and
                record['jit_after'] - record['jit_before'] == record['jit_bodies'] <= completed and
                record['jit_share'] == record['jit_bodies']/completed and
                record['delegated_bodies'] == record['jit_bodies'] and
                record['delegation_share'] == record['jit_share'], 'returned JIT body evidence differs')
        execution = ('NATIVE_ROUTING_CONTROL' if record['mutex_routing'] == 'native' else
                     'JIT' if record['jit_bodies'] else 'ADAPTIVE_NATIVE')
        require(record['execution_class'] == execution and
                (record['mutex_routing'] != 'native' or record['jit_bodies'] == 0),
                'execution classification differs')
        stats_lines = re.findall(r'kd_mutex stats: ([^\n]+)', log)
        require(len(stats_lines) == 1, 'missing or duplicate KD retirement stats')
        stats = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', stats_lines[0])}
        require(stats['active_waiters'] == stats['reserved_nodes'] == stats['frame_failure'] == 0 and
                stats['origin_acquires'] == stats['origin_releases'], 'KD queue/frame/owner imbalance')
        record['audited_lifetime_stats'] = stats
        for key in ('mutex_epoch_before', 'mutex_epoch_after', 'mutex_epoch_delta'):
            require(len(record[key]) == 3 and all(natural(v) for v in record[key]), 'invalid epoch counters')
        require([b - a for a, b in zip(record['mutex_epoch_before'], record['mutex_epoch_after'])] ==
                record['mutex_epoch_delta'], 'epoch delta differs')
        require(record['mutex_native_epoch_ms'] or record['mutex_epoch_delta'] == [0, 0, 0],
                'disabled epoch policy changed epoch counters')
        for key in record['mutex_wait_delta']:
            require(record['mutex_wait_after'][key] - record['mutex_wait_before'][key] ==
                    record['mutex_wait_delta'][key] >= 0, 'wait counter delta differs')
    elif record['arm'] == 'tclock':
        for key in ('tclock_before', 'tclock_after', 'tclock_drained'):
            params = record[key]
            tc_quiescent(params, 'mutex')
            require(params['target_lock'] == record['layout']['lock_addr'] and
                    params['komb_batch_size'] == 1024, 'TCLock configuration differs')
        before, after = record['tclock_before'], record['tclock_after']
        require(after == record['tclock_drained'], 'TCLock counters changed after worker completion')
        require(all(after[k] >= before[k] for k in ('delegated', 'batches', 'parks')) and
                after['delegated'] - before['delegated'] == record['delegated_bodies'] and
                0 <= record['delegated_bodies'] <= completed and
                record['delegation_share'] == record['delegated_bodies']/completed and
                record['jit_bodies'] == 0, 'TCLock returned-body evidence differs')
    else:
        require(record['jit_bodies'] == record['delegated_bodies'] == 0 and
                record['execution_class'] == 'NATIVE', 'Native execution identity differs')
    if mode == 'profile':
        profile = parse_profile(log, record['arm'])
        require(profile == record['lock_profile'], 'saved profile differs from raw kernel receipt')
        require(read(path/'profile-drain.counts.json')['active'] == 0, 'profile did not drain')
    return record


def audit_group(raw, declared):
    name, mode, arms, counts = declared
    folder = raw/name
    receipt = frozen(folder, mode)
    plan, aggregate = read(folder/'plan.json'), read(folder/'records.json')
    expected = {(t, arm, 0) for t in counts for arm in arms}
    require(len(plan) == len(expected) and
            {(p['threads'], p['arm'], p['repeat']) for p in plan} == expected,
            'planned arm/count/repeat grid differs: ' + name)
    names = {p['name'] for p in plan}
    require(len(names) == len(plan) == len(aggregate) and
            {r['name'] for r in aggregate} == names, 'missing/duplicate aggregate sample')
    records_by_name = {r['name']: r for r in aggregate}
    rows = [verify_record(folder, p, records_by_name[p['name']], mode) for p in plan]
    policies = {tuple(r[k] for k in CONTROL) for r in rows if r['arm'] == 'kdlock'}
    require(len(policies) <= 1, 'multiple KD policies in one diagnostic group')
    policy = dict(zip(CONTROL, next(iter(policies)))) if policies else None
    if name in {g[0] for g in DEFAULTS}:
        require(policy == CONTROL, 'control group enabled an experimental policy')
    if policy:
        require(policy['mutex_routing'] in ('adaptive', 'native') and
                policy['mutex_acceptance'] == 'adaptive-performance', 'unsupported diagnostic policy')
        require(type(policy['mutex_entry_ratio_limit']) is int and
                policy['mutex_entry_ratio_limit'] in (2, 4, 8, 16, 32, 64, 128, 256) and
                natural(policy['mutex_native_epoch_ms']) and
                type(policy['mutex_native_probe_ms']) is int and policy['mutex_native_probe_ms'] > 0 and
                all(type(policy[key]) is bool for key, value in CONTROL.items() if type(value) is bool),
                'invalid KD policy value')
        require((folder/'kdlock-node-locality.txt').read_text().strip() ==
                str(int(policy['mutex_node_locality'])), 'compiled node layout differs')
    for arm in arms:
        for field, suffix in (('mutex_lazy_save', 'lazy-save'), ('mutex_preflight', 'preflight')):
            require((folder/f'{arm}-{suffix}.txt').read_text().strip() ==
                    str(int(policy[field] if arm == 'kdlock' else False)),
                    'compiled caller policy differs: ' + arm + ' ' + field)
    receipt.update(group=name, mode=mode, arms=list(arms), worker_counts=list(counts),
                   repeats=[0], sessions=len(rows), diagnostic=True, score_eligible=False,
                   source_and_raw_verified=True, every_worker_progress=True, drained=True,
                   kd_policy=policy)
    return rows, receipt


def summarize_group(raw, declared, rows):
    group, mode, _, _ = declared
    samples, profiles, histograms, pmus, workers = [], [], [], [], []
    for record in rows:
        m = record['measurement']
        identity = dict(group=group, mode=mode, sample=record['name'], arm=record['arm'],
                        threads=record['threads'], repeat=record['repeat'],
                        diagnostic=True, score_eligible=False, post_work_rounds=8)
        shares = [w['completed']/m['completed'] for w in m['workers']]
        row = dict(**identity, completed=m['completed'], diagnostic_whole_mops=m['completed']*1e3/m['wall_ns'],
                   diagnostic_peak_mops=m['peak']['throughput_ops_s']/1e6,
                   worker_cpu_ns=m['worker_cpu_ns'], worker_cpu_ns_per_op=m['worker_cpu_ns']/m['completed'],
                   worker_cpu_equivalents=m['worker_cpu_ns']/m['wall_ns'],
                   min_worker_share=min(shares), max_worker_share=max(shares),
                   delegated_bodies=record['delegated_bodies'], delegation_share=record['delegation_share'],
                   jit_bodies=record['jit_bodies'], jit_share=record['jit_share'],
                   execution_class=record.get('execution_class', 'TCLOCK'),
                   **{k: record.get(k) for k in CONTROL})
        epoch = record.get('mutex_epoch_delta', [None, None, None])
        row.update(native_epochs=epoch[0], native_probes=epoch[1], native_remote_vetoes=epoch[2],
                   **record.get('mutex_wait_delta', {}))
        if record['arm'] == 'tclock':
            row.update(tclock_batches=record['tclock_after']['batches']-record['tclock_before']['batches'],
                       tclock_parks=record['tclock_after']['parks']-record['tclock_before']['parks'])
        for worker, share in zip(m['workers'], shares):
            workers.append(dict(**identity, **worker, share=share))
        if mode == 'profile':
            p = record['lock_profile']
            admissions = p['admitted'] + p['declined']
            profiles.append(dict(**identity, **{k: p[k] for k in PROFILE_FIELDS},
                native_fast=p['native_calls']-p['native_slow'] if record['arm'] == 'native' else None,
                admission_fraction=p['admitted']/admissions if admissions else None,
                mean_batch=p['batch_packets']/p['batches'] if p['batches'] else None,
                owner_zero_fraction=p['owner_zero']/p['owner_samples'],
                owner_change_fraction=p['owner_changes']/p['owner_samples']))
            for bucket in range(12):
                histograms.append(dict(**identity, bucket=bucket, batches=p['batch_histogram'][str(bucket)],
                    minimum_packets=(1 << (bucket-1)) if bucket else 0,
                    maximum_packets=None if bucket == 11 else (1 << bucket)-1))
        else:
            events = parse_pmu(raw/group/record['name']/'pmu.csv')
            for event, values in events.items():
                pmus.append(dict(**identity, event=event, **values,
                                 value_per_completed_op=values['value']/m['completed']))
            row.update(pmu_effective_ghz=events['cycles']['value']/events['task-clock']['value']/1e6,
                       pmu_ipc=events['instructions']['value']/events['cycles']['value'],
                       pmu_cpu_equivalents_over_worker_wall=events['task-clock']['value']*1e6/m['wall_ns'])
            for event in EVENTS:
                row['pmu_' + event.replace('-', '_')] = events[event]['value']
                row['pmu_' + event.replace('-', '_') + '_running_pct'] = events[event]['running_pct']
        samples.append(row)
    return samples, profiles, histograms, pmus, workers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True, help='root containing extracted diagnostic groups')
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--group', nargs=4, action='append', metavar=('NAME', 'MODE', 'ARMS', 'COUNTS'),
                        help='replace default grids; comma-separated arms/counts, repeat zero')
    parser.add_argument('--candidate-pmu', action='append', default=[], metavar='NAME',
                        help='append KD-only PMU group at 2,4,16,28,32,60 workers')
    args = parser.parse_args()
    groups = ([(n, m, tuple(a.split(',')), tuple(map(int, c.split(',')))) for n, m, a, c in args.group]
              if args.group else list(DEFAULTS))
    groups += [(name, 'pmu', ('kdlock',), COUNTS) for name in args.candidate_pmu]
    require(len({g[0] for g in groups}) == len(groups), 'duplicate group name')
    for name, mode, arms, counts in groups:
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name) and mode in ('profile', 'pmu') and
                arms and len(set(arms)) == len(arms) and set(arms) <= {'native', 'kdlock', 'tclock'} and
                (mode != 'profile' or 'tclock' not in arms) and counts and len(set(counts)) == len(counts) and
                all(1 <= t <= 60 for t in counts), 'invalid explicitly declared group')
    outputs = [[] for _ in range(5)]
    receipts, seen = [], set()
    for group in groups:
        rows, receipt = audit_group(args.raw, group)
        identities = study.sample_identities(rows)
        require(len(identities) == len(rows) and not seen.intersection(identities), 'reused diagnostic sample')
        seen.update(identities)
        for target, values in zip(outputs, summarize_group(args.raw, group, rows)):
            target.extend(values)
        receipts.append(receipt)
    # No output is written until every declared session has passed its audit.
    args.out.mkdir(parents=True, exist_ok=True)
    labels = ('samples', 'profiles', 'histograms', 'pmu', 'workers')
    for label, values in zip(labels, outputs):
        csv_write(args.out/f'diagnostics-{label}.csv', values)
    write_json(args.out/'diagnostics.json', dict(schema=1, post_work_rounds=8,
        diagnostic=True, score_eligible=False, passed=True, sessions=len(outputs[0]),
        groups=receipts, tables={label: values for label, values in zip(labels, outputs)},
        limits=[
            'Instrumented single sessions are causal clues, never throughput acceptance scores or medians.',
            'Profile probes and the 100 us owner timer perturb execution; compare with separate uninstrumented samples.',
            'Owner changes compare successive nonzero samples; they do not measure exact ownership streaks or transfers.',
            'Native fast = calls minus slow calls only in Native; KD may call the native slow path directly.',
            'Admission is not delegation; profile batches cover profiler lifetime, not exactly the business measurement window.',
            'PMU scope includes the measured client and inherited workers, excluding setup/warmup; counts/op use business completions.',
            'PMU effective GHz is aggregate cycles/task-clock, not combiner frequency; CPU equivalents use worker measurement wall time.',
            'Only complete, nonmultiplexed six-event PMU records pass; running percentages and raw event runtimes are retained.',
            'Generic cache misses do not isolate coherence traffic or prove cacheline ownership transfers.',
            'Kernel, topology and source identity are audited; governor and thermal/frequency effects are not controlled here.'
        ]))
    print(json.dumps(dict(passed=True, diagnostic=True, score_eligible=False,
                          groups=len(groups), sessions=len(outputs[0]), output=str(args.out))))


if __name__ == '__main__':
    main()
