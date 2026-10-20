#!/usr/bin/env python3
"""Analyze completed perf text as inert data; never execute recorded programs."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re

SAMPLE = re.compile(r'^\s*(?P<comm>.+?)\s+(?P<pid>\d+)\s*/\s*(?P<tid>\d+)\s+'
    r'\[(?P<cpu>\d+)\]\s+(?P<time>\d+\.\d+):\s+(?P<period>\d+)\s+'
    r'cycles:k:\s+(?P<ip>(?:0x)?[0-9a-fA-F]+)\s+(?P<symbol>.*?)\s+\((?P<dso>.*)\)\s*$')
GROUPS = {
    'direct_lock_entry': r'^(?:kd_mutex_lock_entry|kd_mutex_direct_lock_clobber_v1)$',
    'direct_unlock_route': r'^(?:__kd_mutex_unlock|kd_mutex_direct_unlock_clobber_v1)$',
    'exact_task_identity': r'^kd_mutex_task_(?:active|reroute|get|put)$',
    'rcu_read_helpers_all_uses': r'^__rcu_read_(?:lock|unlock)$',
    'physical_mutex': r'^(?:kd_mutex_local_(?:lock|unlock)|kd_local_lock_slow|kd_local_unlock_slow)$',
    'admission': r'^(?:kd_mutex_contended_acquire|kd_hotlock_record_mutex)$',
    'queue': r'^(?:_kd_mutex_lock_abi|kd_mutex_lock_slowpath|__kd_mutex_lock_slowpath|kd_mutex_wait_and_lock|kd_mutex_wait_for_result)$',
    'combine_release': r'^(?:kd_mutex_run_combiner|kd_mutex_execute_cs|_kd_mutex_unlock_checked|_kd_mutex_unlock)$',
    'return_thunk_all_uses': r'^__x86_return_thunk$',
}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base = args.raw/'extracted/run-2'
    records = read(base/'matrix/records.json')
    sizes = read(args.raw/'original-elf/module-symbol-sizes.json')
    helper_path = args.repo/'bench/spin_cacheline/profile_summary.py'
    spec = importlib.util.spec_from_file_location('range_reader', helper_path)
    ranges_helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ranges_helper)
    guest = Path('/root/kdlock-evidence/10.176.26.71/bench/pipecap-causal-20261021/run-2')
    summaries = []
    for record in records:
        if record['causal_mode'] != 'profile':
            continue
        assert record['perf_clock_id'] == 'mono'
        assert '--clockid' in record['perf_command'] and record['perf_command'][record['perf_command'].index('--clockid')+1] == 'mono'
        folder = base/Path(record['evidence_path']).relative_to(guest)
        assert record == read(folder/'session.json')
        assert record['diagnostic'] and record['perf_record'] and not record['score_eligible']
        assert record['execution_status'] == 'OK' and record['drained']
        m = record['measurement']
        version = 'baseline' if record['comparison_arm'] == 'baseline-kd' else 'current'
        key = version+'/'+record['comparison_workload']
        provider_ranges = ranges_helper.symbol_ranges((folder/'kallsyms').read_text(),
            sizes[key]['sizes'], 'kdlock_km') if record['arm'] == 'kdlock' else []
        ranges = [(a, b, name.split(':', 1)[1]) for a, b, name in provider_ranges]
        # Generated images have an exact allocation range. Never assign an
        # arbitrary anonymous executable address to its nearest kernel symbol.
        jit_range = None
        if record['arm'] == 'kdlock':
            published = record['published_before']
            images = list((folder/'workspace/daemon').glob('**/jit.bin'))
            matching = [p for p in images if sha(p) == published['images']['jit.bin']]
            assert len(matching) == 1
            start = published['entry']['code']
            jit_range = start, start+matching[0].stat().st_size
        counts, periods, commands, categories, offsets = (Counter() for _ in range(5))
        all_period, workers = 0, 0
        excluded_samples, excluded_period = 0, 0
        worker_by_cpu = {w['cpu']:w for w in m['workers']}
        tid_cpus = {}
        cpus, pids, tids, timestamps, errors, losses = set(), set(), set(), [], [], []
        for number, line in enumerate((folder/'perf-samples.txt').read_text().splitlines(), 1):
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            if 'PERF_RECORD_LOST' in line:
                losses.append(dict(line=number, text=line))
                continue
            match = SAMPLE.fullmatch(line)
            if not match or int(match['period']) <= 0:
                errors.append(dict(line=number, text=line))
                continue
            row = match.groupdict()
            period, ip = int(row['period']), int(row['ip'], 16)
            all_period += period
            commands[row['comm'].strip()] += period
            if row['comm'].strip() != 'sc_worker':
                continue
            whole, fraction = row['time'].split('.')
            stamp = int(whole)*1_000_000_000+int(fraction.ljust(9,'0'))
            precision = 10**(9-len(fraction))
            worker = worker_by_cpu.get(int(row['cpu']))
            if worker is None or not (worker['active_started_ns'] <= stamp and stamp+precision-1 <= worker['kernel_finished_ns']):
                excluded_samples += 1; excluded_period += period
                continue
            tid = int(row['tid']); cpu = int(row['cpu'])
            assert tid not in tid_cpus or tid_cpus[tid] == cpu
            tid_cpus[tid] = cpu
            workers += 1
            cpus.add(int(row['cpu']))
            pids.add(int(row['pid']))
            tids.add(int(row['tid']))
            timestamps.append(float(row['time']))
            symbol, dso = row['symbol'], row['dso']
            if jit_range and jit_range[0] <= ip < jit_range[1]:
                symbol, dso = 'generated_image', 'exact_published_image'
            elif dso == '[kdlock_km]':
                matches = [(a, b, name) for a, b, name in ranges if a <= ip < b]
                if len(matches) == 1:
                    a, b, symbol = matches[0]
                    offsets[symbol, ip-a] += period
                else:
                    symbol = 'ambiguous_provider' if matches else 'unresolved_provider'
            bare = re.sub(r'\.(?:constprop|isra|part)\.\d+$', '', symbol.split('+0x', 1)[0])
            counts[bare, dso] += 1
            periods[bare, dso] += period
            for name, pattern in GROUPS.items():
                if re.fullmatch(pattern, bare):
                    categories[name] += period
        text = (folder/'perf-report.txt').read_text()
        lost = [int(x.replace(',', '')) for x in re.findall(r'Total Lost Samples:\s*([\d,]+)', text)]
        total = [int(x.replace(',', '')) for x in re.findall(r'Event count \(approx\.\):\s*([\d,]+)', text)]
        issues = []
        if errors or losses or lost != [0]:
            issues.append('invalid/unparsed samples, lost samples or missing loss count')
        if total != [all_period]:
            issues.append('period total differs from perf report')
        if cpus != set(record['cpus']) or len(tids) != record['threads'] or len(pids) != 1:
            issues.append('worker PID/TID/CPU cohort differs')
        if record['comparison_workload'] not in ('c08', 'rcuht') and pids != {record['client_pid']}:
            issues.append('API worker process differs from persistent client')
        denominator = sum(periods.values())
        if not workers or not denominator:
            issues.append('no worker denominator')
        detail = dict(name=record['name'], workload=record['comparison_workload'],
            arm=record['comparison_arm'], threads=record['threads'], repeat=record['repeat'],
            usable=not issues, issues=issues, parse_errors=errors[:10], lost_records=losses,
            lost_count=lost, worker_samples=workers, worker_sampled_period=denominator,
            all_sampled_period=all_period, command_periods=dict(commands),
            worker_cpus=sorted(cpus), worker_pids=sorted(pids), worker_tids=sorted(tids),
            perf_timestamp_span=[min(timestamps), max(timestamps)],
            guest_measurement_seconds=[m['started_ns']/1e9, m['finished_ns']/1e9],
            clock_alignment='Explicit perf --clockid mono and client CLOCK_MONOTONIC; retain only samples wholly inside the worker CPU active interval, including printed timestamp precision.',
            excluded_worker_samples=excluded_samples, excluded_worker_period=excluded_period, tid_to_cpu=tid_cpus,
            completed=m['completed'], whole_ops_s=m['completed']*1e9/m['wall_ns'],
            jit_bodies=record.get('jit_bodies'), jit_completions=record.get('jit_completions'),
            sampled_period_per_operation=denominator/m['completed'],
            categories={name: dict(sampled_period=categories[name],
                worker_weight_pct=100*categories[name]/denominator) for name in GROUPS},
            top_symbols=[dict(symbol=s, dso=d, samples=counts[s, d], sampled_period=v,
                worker_weight_pct=100*v/denominator) for (s, d), v in periods.most_common(25)],
            provider_hot_offsets=[dict(symbol=s, offset=hex(o), sampled_period=v,
                worker_weight_pct=100*v/denominator) for (s, o), v in offsets.most_common(30)],
            hashes={name: sha(folder/name) for name in
                ('perf.data', 'perf-report.txt', 'perf-samples.txt', 'kallsyms', 'session.json')},
            provider_elf_sha256=sizes[key]['sha256'] if record['arm'] == 'kdlock' else None)
        summaries.append(detail)
    assert len(summaries) == 12
    result = dict(run='pipecap-causal-20261021/run-2', sessions=summaries,
        usable=sum(r['usable'] for r in summaries), count=len(summaries),
        script_sha256=sha(Path(__file__)), ranges_helper_sha256=sha(helper_path),
        records_sha256=sha(base/'matrix/records.json'),
        symbol_sizes_sha256=sha(args.raw/'original-elf/module-symbol-sizes.json'),
        scope='Flat event-period weights, not isolated function timings or p95 latency. '
              'Three separate instrumented repeats. Interrupts inside each active worker interval can contribute. '
              'Host interference remains uncertain. RCU and return-thunk costs cannot be assigned '
              'exclusively to task routing. Profile and plain execution shares can differ.',
        overall_acceptance='OPEN')
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(dict(count=result['count'], usable=result['usable'])))
    for r in summaries:
        if r['arm'] == 'public-kd':
            print(r['name'], 'entry%', round(r['categories']['direct_lock_entry']['worker_weight_pct'], 2),
                  'tasks%', round(r['categories']['exact_task_identity']['worker_weight_pct'], 2),
                  'unlocks%', round(r['categories']['direct_unlock_route']['worker_weight_pct'], 2),
                  'issues', r['issues'])


if __name__ == '__main__':
    main()
