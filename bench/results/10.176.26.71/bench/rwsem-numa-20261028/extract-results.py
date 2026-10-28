"""Read completed rwsem NUMA receipts; write JSON only to standard output."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/rwsem-numa-20261028')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_identity(directory):
    path = directory / 'source-sha256.json'
    manifest = read(path)
    differences = [name for name, value in manifest.items()
                   if sha(directory / 'source' / name) != value]
    assert not differences, differences
    return dict(manifest_sha256=sha(path), files=manifest,
                frozen_source_files_checked=len(manifest), mismatches=differences)


def point(row, diagnostic=False):
    m = row.get('measurement', {})
    complete = (row.get('execution_status') == 'OK' and row.get('drained') is True
                and m.get('complete') is True and m.get('data_ok') is True)
    entries, returns = row.get('jit_bodies'), row.get('jit_completions')
    execution = ('NATIVE' if row['arm'] != 'kdlock' else
                 'RETURNED_JIT' if returns else 'PARTIAL_JIT' if entries else 'NO_JIT')
    return dict(name=row['name'], backend=row['arm'], lock_kind=row['lock_kind'],
                workload=row['workload'], cachelines=row['cachelines'],
                write_percent=row['write_percent'], threads=row['threads'],
                cpus=row['cpus'], cpu_nodes=row['cpu_nodes'], collector_cpu=row['collector_cpu'],
                repeat=row['repeat'], post_work_rounds=row['post_work_rounds'],
                duration_ms=row['duration_ms'], diagnostic=diagnostic,
                score_eligible=row.get('score_eligible', not diagnostic),
                mops_s=m.get('completed', 0) * 1e3 / m['wall_ns'] if complete else None,
                completed=m.get('completed'), writes=m.get('writes'), reads=m.get('reads'),
                execution_status=row.get('execution_status'), drained=row.get('drained'),
                data_ok=m.get('data_ok'), complete=m.get('complete'), valid=complete,
                execution_class=execution, jit_entries=entries, jit_completions=returns,
                returned_body_share_of_writes=(returns / m['writes']
                    if returns is not None and m.get('writes') else 0),
                provider_mutex_policy=row.get('provider_mutex_policy'),
                delegate=row['delegate'], call_shell=row.get('call_shell'))


def sample_summary(path, row):
    pattern = re.compile(r'^\s*(?P<comm>.+?)\s+(?P<pid>\d+)/(?P<tid>\d+)\s+'
        r'\[(?P<cpu>\d+)\]\s+(?P<time>\d+\.\d+):\s+(?P<period>\d+)\s+'
        r'(?P<event>[^:]+):\s+(?P<ip>[0-9a-fA-F]+)\s+(?P<symbol>.+?)\s+\((?P<dso>.*)\)\s*$')
    m = row['measurement']
    start = max(m['started_ns'] + m['peak_settle_ns'],
                max(w['active_started_ns'] for w in m['workers']))
    finish = min(m['deadline_ns'], min(w['kernel_finished_ns'] for w in m['workers']))
    assert start < finish
    all_samples = defaultdict(lambda: [0, 0])
    settled_samples = defaultdict(lambda: [0, 0])
    nonworkers = Counter()
    events = Counter()
    unparsed = []
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        match = pattern.match(line)
        if not match:
            unparsed.append(line)
            continue
        g = match.groupdict()
        events[g['event']] += 1
        if g['comm'] != 'rb_worker':
            nonworkers[g['comm']] += 1
            continue
        assert int(g['cpu']) in row['cpus']
        seconds, fraction = g['time'].split('.')
        timestamp = int(seconds) * 1_000_000_000 + int(fraction.ljust(9, '0'))
        key = (g['symbol'], g['dso'])
        all_samples[key][0] += 1
        all_samples[key][1] += int(g['period'])
        if start <= timestamp < finish:
            settled_samples[key][0] += 1
            settled_samples[key][1] += int(g['period'])
    assert not unparsed, unparsed[:5]

    def aggregate(values):
        count = sum(v[0] for v in values.values())
        period = sum(v[1] for v in values.values())
        assert count and period
        return dict(samples=count, total_period=period,
                    functions=[dict(symbol=k[0], dso=k[1], samples=v[0], period=v[1],
                                    sample_share=v[0] / count, period_share=v[1] / period,
                                    period_percent=100 * v[1] / period)
                               for k, v in sorted(values.items(), key=lambda kv: -kv[1][1])])

    report = path.with_name('perf-report.txt').read_text()
    lost_match = re.search(r'Total Lost Samples:\s*(\d+)', report)
    return dict(sample_file_sha256=sha(path), report_file_sha256=sha(path.with_name('perf-report.txt')),
                lost_samples_in_perf_report=int(lost_match[1]) if lost_match else None,
                event_counts=dict(events), excluded_nonworker_samples=dict(nonworkers),
                unparsed_samples=len(unparsed),
                settled_interval_ns=dict(start=start, end=finish),
                clock='CLOCK_MONOTONIC, matching perf --clockid mono',
                settled_selection='rb_worker only, after 300 ms settle, all workers active, before any worker kernel finish/deadline',
                all_rb_worker=aggregate(all_samples), settled_rb_worker=aggregate(settled_samples),
                scope='Flat cpu-clock period-weighted instruction-pointer samples. Not callchains, PMU cycles, memory stalls, or uninstrumented throughput.')


result = dict(schema=1, guest_base=str(BASE),
              scope='Read-only extraction of completed frozen receipts and profile samples; no oracle, test, build or timing execution.',
              phases=[], profile_baseline={}, caveats=[
                  'One two-second repetition per uninstrumented point; no repeat variability estimate.',
                  'Do not pool changed sources, compact/split CPU placements, or instrumented profile rates.',
                  'Flat cpu-clock samples identify where worker CPU time was sampled; they do not isolate NUMA traffic or stall causes.',
                  'NO_JIT points cannot establish benefits from writer delegation; all read bodies remain local.',
                  'kd_mutex_osq_lock is shared by reader admission and the embedded mutex gate. No callgraph was captured; flat samples cannot directly separate reader versus writer queue waits.',
              ])
baseline_manifest = None
for phase in ('baseline', 'colocated', 'striped', 'cohort'):
    base = BASE / phase
    status = read(base / 'status.json')
    assert status['passed'] and all(x['returncode'] == 0 for x in status['commands'])
    item = dict(phase=phase, status=status, status_sha256=sha(base / 'status.json'), variants=[])
    for variant in ('compact', 'split32'):
        directory = base / variant
        manifest = source_identity(directory)
        if baseline_manifest is None:
            baseline_manifest = manifest['files']
        records = read(directory / 'records.json')
        rows = [point(row) for row in records]
        assert all(row['valid'] for row in rows)
        assert all(row['repeat'] == 0 for row in rows)
        assert len({row['name'] for row in rows}) == len(rows)
        item['variants'].append(dict(name=variant, source_identity=manifest,
            changed_sources_from_baseline={name: dict(baseline=baseline_manifest.get(name), current=value)
                for name, value in manifest['files'].items() if baseline_manifest.get(name) != value},
            removed_sources_from_baseline=sorted(set(baseline_manifest) - set(manifest['files'])),
            records_sha256=sha(directory / 'records.json'), plan_sha256=sha(directory / 'plan.json'),
            points=rows))
    result['phases'].append(item)

for profile_name, phase_name in [('profile-baseline', 'baseline'), ('profile-cohort', 'cohort')]:
    base = BASE / profile_name
    directory = base / 'rwsem-c01-w020'
    profile_result = read(base / 'result.json')
    manifest = source_identity(directory)
    outer_manifest = read(base / 'source-sha256.json')
    phase = next(p for p in result['phases'] if p['phase'] == phase_name)
    matching = next(v for v in phase['variants'] if v['name'] == 'compact')['source_identity']['files']
    assert manifest['files'] == outer_manifest == matching
    assert profile_result['completed'] and profile_result['final_idle'] and not profile_result['score_eligible']
    profile = dict(result=profile_result, result_sha256=sha(base / 'result.json'),
        frozen_sources_equal_phase=phase_name + '/compact', source_identity=manifest,
        outer_source_manifest_sha256=sha(base / 'source-sha256.json'), points=[])
    if profile_name == 'profile-baseline':
        correction = read(base / 'source-identity-correction.json')
        assert sha(base / 'source-sha256.json') == correction['profile_manifest_sha256']
        assert profile_result['source_commit'] == correction['recorded_commit']
        profile.update(source_identity_correction=correction,
            source_identity_correction_sha256=sha(base / 'source-identity-correction.json'),
            verified_actual_commit=correction['actual_source_host_commit'],
            source_label_note='The original diagnostic CLI commit was transcribed incorrectly; it is retained unchanged. Exact frozen manifests establish baseline identity and the separate correction records the actual source-host commit.')
    else:
        assert profile_result['source_commit'] is None
        profile.update(source_label_note='The diagnostic CLI source-commit argument was intentionally omitted. The original result retains source_commit:null; exact inner/outer frozen source hashes match the completed cohort/compact measurement. A separate source-host commit binding may be added after read-only Git inspection.')
    for row in read(directory / 'records.json'):
        item = point(row, diagnostic=True)
        assert item['valid'] and item['score_eligible'] is False
        item['perf_command'] = read(directory / row['name'] / 'perf-record-command.json')
        item['profile'] = sample_summary(directory / row['name'] / 'perf-samples.txt', row)
        profile['points'].append(item)
    result[profile_name.replace('-', '_')] = profile
result['totals'] = dict(uninstrumented_points=sum(len(v['points']) for phase in result['phases']
                          for v in phase['variants']), diagnostic_points=sum(
                              len(result[name]['points']) for name in ['profile_baseline', 'profile_cohort']))
comparisons = []
for phase in result['phases']:
    variants = {v['name']: v for v in phase['variants']}
    for backend in ('kdlock', 'tclock'):
        compact = next(x for x in variants['compact']['points'] if x['backend'] == backend
                       and x['cachelines'] == 1 and x['write_percent'] == 20 and x['threads'] == 32)
        split = next(x for x in variants['split32']['points'] if x['backend'] == backend)
        comparisons.append(dict(phase=phase['phase'], backend=backend,
            workload='rwsem c01, 20% writes, post256', workers=32,
            compact_mops_s=compact['mops_s'], split_mops_s=split['mops_s'],
            split_percent_change=100 * (split['mops_s'] / compact['mops_s'] - 1),
            compact_execution=compact['execution_class'], split_execution=split['execution_class'],
            compact_jit_completions=compact['jit_completions'], split_jit_completions=split['jit_completions']))
result['same_worker_topology_comparison'] = comparisons
result['causal_notes'] = [
    'The same32workers and payload run changes placement from CPUs0–31 to0–15+32–47. This isolates worker placement from worker count, but remains one observation per placement and preserves any JIT-class difference.',
    'Colocated and striped screens remain separate source generations, including regressions and neutral cases. The cohort screen is not pooled with them.',
    'Flat sampled queue-function names do not identify each caller, cacheline-transfer latency, or memory-stall causes. Profile rates remain separate from uninstrumented throughput.',
]
print(json.dumps(result, indent=2))
