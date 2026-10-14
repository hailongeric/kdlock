#!/usr/bin/env python3
"""Audit the unscored SELF PMU block and its physical-host observer.

No workload execution. Frequency samples are observational and not weighted by
operations; aggregate virtual PMU cycles/task-clock remain a separate quantity.
"""
import argparse
import json
from pathlib import Path
import statistics
import sys

sys.dont_write_bytecode = True
import references

report = references.report
audit, require = report.audit, report.require
RUN = 'bench/mutex-native-first-self-pmu64-20261014'
CLOCK = 'tests/mutex-native-first-self-clock-20261014'
ARCHIVE_SHA = 'd52d501663ea7fd7b031a54a5674d26708617c30697b55e7c877e76cb943023b'


def proc_stats(text):
    result = {}
    for line in text.splitlines():
        fields = line.split()
        if fields[0].startswith('cpu') and fields[0][3:].isdigit():
            values = list(map(int, fields[1:]))
            require(len(values) >= 8 and all(value >= 0 for value in values), 'invalid proc-stat CPU row')
            # guest/guest_nice are already included in user/nice: do not add
            # their later columns again. Idle and iowait are excluded as idle.
            result[int(fields[0][3:])] = (sum(values[:8]), values[3]+values[4])
    require(set(result) == set(range(64)), 'physical proc-stat CPU coverage differs')
    return result


def freq_summary(points, cpus):
    values = [point['khz'][str(cpu)]/1e6 for point in points for cpu in cpus]
    return dict(samples=len(points), minimum_ghz=min(values) if values else None,
                median_ghz=statistics.median(values) if values else None,
                maximum_ghz=max(values) if values else None)


def busy_summary(points, cpus, start, end):
    values = []
    for before, after in zip(points, points[1:]):
        if not start <= before['time_ns'] < after['time_ns'] <= end:
            continue
        busy = 0.0
        for cpu in cpus:
            total = after['_stat'][cpu][0] - before['_stat'][cpu][0]
            idle = after['_stat'][cpu][1] - before['_stat'][cpu][1]
            require(total > 0 and 0 <= idle <= total, 'physical CPU counters regressed')
            busy += (total-idle)/total
        values.append(busy)
    return dict(complete_intervals=len(values), cpu_equivalents_mean=statistics.mean(values) if values else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True, help='task raw root containing archives and extracted/')
    parser.add_argument('--out', type=Path, default=report.HERE)
    args = parser.parse_args()
    raw = args.raw.resolve()
    extracted = raw/'extracted'
    archive = references.archive_receipt(raw/'self-pmu.tar.gz', extracted, ARCHIVE_SHA)
    rows, receipt = audit.audit_group('self_pmu', extracted/RUN, True)
    report.require_owned(rows, True)
    require(len(rows) == 18 and {r['threads'] for r in rows} == {4, 16, 60} and
            {r['arm'] for r in rows} == {'native', 'kdlock'}, 'SELF diagnostic grid differs')
    require(len({(r['threads'], r['arm'], r['repeat']) for r in rows}) == 18 and
            {r['repeat'] for r in rows} == {0, 1, 2}, 'SELF diagnostic repeat coverage differs')
    for row in rows:
        require(row['pmu'] is True and not row['profile_lock'] and not row['perf_record'],
                'SELF diagnostic instrumentation differs')
        if row['arm'] == 'kdlock':
            require(row['mutex_routing'] == 'self' and row['entry_abi'] == 4 and
                    row['owned_mutex_cabi'] is True and row['owned_mutex_early_release'] is True and
                    row['owned_mutex_native_first'] is False and row['owned_mutex_refill'] is False and
                    row['execution_class'] == 'KD_SELF' and row['jit_bodies'] == 0,
                    'SELF diagnostic policy differs')
    report.study.require_fresh(rows, set())
    start = audit.read(extracted/CLOCK/'start.json')
    end = audit.read(extracted/CLOCK/'end.json')
    command_path = raw/'self-control-pmu-host-command.json'
    frequency_path = raw/'self-control-pmu-host-frequency.jsonl'
    command = audit.read(command_path)
    require(command['exit_status'] == 0 and command['diagnostic'] is True and command['observer_cpu'] == 63,
            'observer command did not complete as the declared diagnostic')
    require(start['monotonic_ns'] < end['monotonic_ns'] and start['time_ns'] < end['time_ns'],
            'guest clock anchors are reversed')
    observations = [json.loads(line) for line in frequency_path.read_text().splitlines()]
    identity, *points = observations
    require(identity['kind'] == 'identity' and identity['affinity'] == [63] and points,
            'observer identity/affinity differs')
    require(set(identity['policies']) == {str(cpu) for cpu in range(64)}, 'governor CPU coverage differs')
    for point in points:
        require(point['kind'] == 'sample' and set(point['khz']) == {str(cpu) for cpu in range(64)},
                'observer frequency coverage differs')
        point['khz'] = {key: int(value) for key, value in point['khz'].items()}
        require(all(value > 0 for value in point['khz'].values()), 'invalid sampled frequency')
        point['_stat'] = proc_stats(point['proc_stat'])
    require(all(a['time_ns'] < b['time_ns'] and a['monotonic_ns'] < b['monotonic_ns']
                for a, b in zip(observations, observations[1:])), 'observer clocks regressed')
    guest_offset_start = start['time_ns']-start['monotonic_ns']
    guest_offset_end = end['time_ns']-end['monotonic_ns']
    delta_min = command['host_start_time_ns']-start['time_ns']
    delta_max = command['host_end_time_ns']-end['time_ns']
    require(delta_min <= delta_max, 'host/guest causal clock bounds do not overlap')

    def epoch(monotonic_ns):
        require(start['monotonic_ns'] <= monotonic_ns <= end['monotonic_ns'], 'measurement outside guest clock anchors')
        drift = (guest_offset_end-guest_offset_start)*(monotonic_ns-start['monotonic_ns'])//(
            end['monotonic_ns']-start['monotonic_ns'])
        return monotonic_ns+guest_offset_start+drift

    summaries, selected_points = [], []
    for row in rows:
        m, events = row['measurement'], row['_pmu']
        begin, finish = epoch(m['started_ns']), epoch(m['finished_ns'])
        guaranteed_begin, guaranteed_finish = begin+delta_max, finish+delta_min
        nominal = [point for point in points if begin <= point['time_ns'] <= finish]
        guaranteed = [point for point in points if guaranteed_begin <= point['time_ns'] <= guaranteed_finish]
        require(nominal, 'no nominal frequency sample during a measured run')
        summary = dict(**audit.identity('self_pmu', row),
            whole_mops=m['completed']*1e3/m['wall_ns'], peak_mops=m['peak']['throughput_ops_s']/1e6,
            jit_bodies=row['jit_bodies'], whole_worker_progress=all(w['completed'] > 0 for w in m['workers']),
            worker_cpu_equivalents=m['worker_cpu_ns']/m['wall_ns'],
            worker_cpu_ns_per_op=m['worker_cpu_ns']/m['completed'],
            pmu_cpu_equivalents=events['task-clock']['value']*1e6/m['wall_ns'],
            effective_ghz=events['cycles']['value']/events['task-clock']['value']/1e6,
            ipc=events['instructions']['value']/events['cycles']['value'],
            cycles_per_op=events['cycles']['value']/m['completed'],
            instructions_per_op=events['instructions']['value']/m['completed'],
            context_switches_per_op=events['context-switches']['value']/m['completed'],
            cache_misses_per_op=events['cache-misses']['value']/m['completed'],
            nominal_host_start_ns=begin, nominal_host_end_ns=finish,
            guaranteed_interior_start_ns=guaranteed_begin, guaranteed_interior_end_ns=guaranteed_finish)
        for scope, subset in (('nominal', nominal), ('guaranteed', guaranteed)):
            summary.update({scope+'_frequency_'+key: value for key, value in freq_summary(subset, row['cpus']).items()})
        for scope, bounds in (('nominal', (begin, finish)), ('guaranteed', (guaranteed_begin, guaranteed_finish))):
            summary.update({scope+'_host_busy_'+key: value for key, value in busy_summary(points, row['cpus'], *bounds).items()})
        summaries.append(summary)
        for point in points:
            if not begin+delta_min <= point['time_ns'] <= finish+delta_max:
                continue
            selected_points.append(dict(sample=row['name'], arm=row['arm'], threads=row['threads'], repeat=row['repeat'],
                time_ns=point['time_ns'], nominal_inside=begin <= point['time_ns'] <= finish,
                guaranteed_inside=guaranteed_begin <= point['time_ns'] <= guaranteed_finish,
                worker_khz_json=json.dumps({str(cpu): point['khz'][str(cpu)] for cpu in row['cpus']}, separators=(',', ':'))))
    args.out.mkdir(parents=True, exist_ok=True)
    audit.csv_write(args.out/'self-pmu-analysis.csv', summaries)
    audit.csv_write(args.out/'self-frequency-samples.csv', selected_points)
    audit.write_json(args.out/'self-observer.json', dict(
        passed=True, command=sys.argv, script_sha256=audit.digest(Path(__file__)), archive=archive, run=receipt,
        observer_input_sha256={str(path.relative_to(raw)): audit.digest(path) for path in (
            command_path, frequency_path, extracted/CLOCK/'start.json', extracted/CLOCK/'end.json')},
        identity=identity, guest_clock_anchors=[start, end], host_command=command,
        observer_samples=len(points), guest_realtime_offset_change_ns=guest_offset_end-guest_offset_start,
        host_realtime_offset_range_ns=max(p['time_ns']-p['monotonic_ns'] for p in observations)-
            min(p['time_ns']-p['monotonic_ns'] for p in observations),
        guest_to_host_realtime_offset_bounds_ns=[delta_min, delta_max],
        alignment='Nominal guest monotonic windows mapped through linearly interpolated guest realtime offsets. Causal SSH command bounds permit a guest-to-host wall-clock offset in the reported interval; guaranteed interior is common to every permitted offset, assuming no intervening clock jump.',
        limits=['1 Hz sysfs frequencies are point observations across worker CPUs, not operation-weighted execution frequencies.',
                'Frequency reads are sequential and have no per-CPU read timestamp; boundary samples remain uncertain.',
                'Host busy equivalents use only complete observer intervals inside each window; missing intervals remain blank. Host CPU time includes other physical-host work.',
                'PMU covers measured client and inherited workers; worker CPU accounting has a different scope.',
                'Zero JIT alone does not establish no delegate publication. This separate control explicitly selects SELF routing and records native-first=false.',
                'No observer or PMU result enters scored acceptance or proves a scheduling/cache mechanism.']))
    print(json.dumps(dict(passed=True, sessions=len(rows), observer_samples=len(points),
                          offset_bounds_ns=[delta_min, delta_max], output=str(args.out))))


if __name__ == '__main__':
    main()
