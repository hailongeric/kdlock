#!/usr/bin/env python3
"""Read-only offline accounting review of phase-control JSON evidence.

Partial lifetimes and boundary-straddling counter intervals remain explicitly
unattributed. Never infer departed tails from later cumulative accounting.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def counters(task):
    result = {}
    for name, data in task.get('files', {}).items():
        if data['status'] != 'READ':
            continue
        if name == 'schedstat':
            for key, value in zip(('runtime_ns', 'runqueue_wait_ns', 'timeslices'), data['text'].split()):
                result[key] = int(value)
        elif name == 'io':
            result.update({key: int(value) for key, value in
                           (line.split(':') for line in data['text'].splitlines())})
    return result


def review(path):
    supervisor = json.loads((path/'supervisor.json').read_text())
    stream = records(path/'observer.jsonl')
    rows = [r['remote'] for r in stream]
    samples = [r for r in rows if r['event'] == 'sample']
    complete = [r for r in rows if r['event'] == 'complete']
    ready = [r for r in rows if r['event'] == 'ready']
    assert supervisor['complete'] and len(ready) == len(complete) == 1
    assert complete[0]['end_reason'] == 'requested_stop' and complete[0]['samples'] == len(samples)
    phases, identities, incomplete, changes = defaultdict(list), defaultdict(list), [], []
    anchor = supervisor.get('trigger_anchor')
    if anchor is not None:
        # A trigger run can start with extra workers and retain a refused
        # preflight. Its recorded anchor selects only the original identities;
        # it is not a passing full capture or a count-only gate waiver.
        gate = next(s for s in samples if s['sequence'] == anchor['sample_sequence'])
        assert hashlib.sha256(json.dumps(gate, sort_keys=True).encode()).hexdigest() == anchor['sample_sha256']
        old = json.loads((path/'original-host-state.json').read_text())['qemu'][0]['tasks']
        assert sorted(old, key=lambda t: t['tid']) == anchor['tasks']
        lifetime_ticks = {tid: ticks for tid, ticks in anchor['identities']}
        assert len(lifetime_ticks) == len(anchor['identities']) == len(anchor['tasks']) == 67
        original = {(t['tid'], lifetime_ticks[t['tid']]): (t['comm'], t['affinity']) for t in anchor['tasks']}
        available = {tuple(t['identity_before']): (t['comm'], t['affinity']) for t in gate['tasks'] if t['complete']}
        assert all(available.get(key) == value for key, value in original.items())
    else:
        gate = samples[supervisor.get('gate_sample_sequence', 0)]
        original = {tuple(t['identity_before']): (t['comm'], t['affinity']) for t in gate['tasks']}
        assert len(original) == 67 and all(t['complete'] for t in gate['tasks'])
    previous = None
    for sample in samples:
        phases[sample['phase']].append(sample)
        active = {}
        for task in sample['tasks']:
            if not task['complete']:
                incomplete.append(dict(sequence=sample['sequence'], task=task))
                continue
            identity = tuple(task['identity_before'])
            assert identity == tuple(task['identity_after'])
            active[identity] = (task['comm'], task['affinity'])
            if task['comm'] == 'worker':
                identities[identity].append(dict(sequence=sample['sequence'], phase=sample['phase'],
                    read_began=task['read_began'], read_finished=task['read_finished'],
                    counters=counters(task), affinity=task['affinity'],
                    wchan=task['files']['wchan'], syscall=task['files']['syscall']))
        assert all(active.get(key) == value for key, value in original.items()), 'original task changed or disappeared'
        if previous is not None and set(active) != set(previous[1]):
            changes.append(dict(sequence=sample['sequence'], phase=sample['phase'],
                previous_scan_began=previous[0]['scan_began'], this_scan_finished=sample['scan_finished'],
                appeared=sorted(set(active)-set(previous[1])), disappeared=sorted(set(previous[1])-set(active))))
        previous = sample, active
    workers = []
    deltas = defaultdict(lambda: defaultdict(int))
    for identity, history in sorted(identities.items()):
        first, last = history[0], history[-1]
        diff = {k: last['counters'][k]-v for k, v in first['counters'].items() if k in last['counters']}
        assert all(v >= 0 for v in diff.values()), 'counter regression within exact lifetime'
        workers.append(dict(identity=identity, observations=len(history), first=first, last=last,
                            birth_boot_interval_ns=[identity[1]*1_000_000_000//ready[0]['clk_tck'],
                                (identity[1]+1)*1_000_000_000//ready[0]['clk_tck']],
                            observed_counter_delta=diff, final_sample_present=last['sequence'] == samples[-1]['sequence'],
                            tail_missing=True))
        for before, after in zip(history, history[1:]):
            phase = after['phase'] if (before['phase'] == after['phase'] and
                after['sequence'] == before['sequence']+1) else 'UNATTRIBUTED_BOUNDARY_OR_GAP'
            for key, value in before['counters'].items():
                if key in after['counters']:
                    delta = after['counters'][key]-value
                    assert delta >= 0
                    deltas[phase][key] += delta
    clock_brackets = []
    for request in supervisor['requests']:
        if request['stream'] == 'observer' or request['value'] == 'clock':
            remote = request['ack']['remote']['real_ns']
            clock_brackets.append(dict(stream=request['stream'], value=request['value'],
                source_midpoint_ns=(request['sent']['real_ns']+request['ack']['received']['real_ns'])//2,
                offset_low_ns=remote-request['ack']['received']['real_ns'],
                offset_high_ns=remote-request['sent']['real_ns'],
                round_trip_ns=request['ack']['received']['mono_ns']-request['sent']['mono_ns']))
    scan_wall = [s['scan_finished']['mono_ns']-s['scan_began']['mono_ns'] for s in samples]
    gaps = [b['scan_began']['mono_ns']-a['scan_finished']['mono_ns'] for a, b in zip(samples, samples[1:])]
    return dict(run=path.name, complete=True, accepted=False, samples=len(samples),
        initial_tasks=len(samples[0]['tasks']), final_tasks=len(samples[-1]['tasks']),
        gate_sequence=gate['sequence'] if anchor is None else None,
        gate_tasks=len(gate['tasks']) if anchor is None else None,
        reference_sample_sequence=gate['sequence'], reference_sample_tasks=len(gate['tasks']),
        minimum_tasks=min(len(s['tasks']) for s in samples), maximum_tasks=max(len(s['tasks']) for s in samples),
        source_commit=supervisor['source_commit'], sources=supervisor['sources'],
        evidence_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir() if p.is_file()},
        original_67_unchanged=True, incomplete_rows=incomplete, changes=changes, workers=workers,
        phases={phase: dict(samples=len(values), minimum_tasks=min(len(s['tasks']) for s in values),
                           maximum_tasks=max(len(s['tasks']) for s in values),
                           observed_worker_deltas=dict(deltas[phase])) for phase, values in phases.items()},
        unattributed_deltas=dict(deltas['UNATTRIBUTED_BOUNDARY_OR_GAP']), clock_brackets=clock_brackets,
        observer=dict(elapsed_ns=complete[0]['elapsed_ns'], cpu_ns=complete[0]['observer_cpu_ns'],
            cpu_percent_one_core=complete[0]['observer_cpu_ns']/complete[0]['elapsed_ns']*100,
            maximum_scan_wall_ns=max(scan_wall), median_scan_wall_ns=statistics.median(scan_wall),
            maximum_unsampled_gap_ns=max(gaps), affinity=ready[0]['observer_affinity'],
            clk_tck=ready[0]['clk_tck'], host_boot_id=ready[0]['host_boot_id'],
            sched_schedstats=ready[0]['sched_schedstats']),
        limitations=['Sampling misses lifetimes wholly between scans and accounting after the last read.',
            'First/last cumulative values are not phase-local activity; only matched intervals are differenced.',
            'Task count includes partial rows; original identities must remain completely readable.',
            'Each read is bracketed; a scan is not an atomic QEMU snapshot.',
            'Clock offsets are per-request intervals, not a fixed synchronized-clock assumption.',
            'Recorded observer CPU excludes SSH/sudo startup and source supervisor overhead.',
            'Host observation has no unobserved counterfactual; guest background I/O is not disabled.',
            ('BOOTTIME brackets present; birth ticks are quantized, not exact instants.' if
             'boot_ns' in samples[0]['scan_began'] else
             'Start ticks lack a recorded BOOTTIME relationship in this control; no UTC birth inference.')])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('runs', nargs='+', type=Path)
    a = p.parse_args()
    print(json.dumps([review(path.resolve()) for path in a.runs], indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
