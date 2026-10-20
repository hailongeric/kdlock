#!/usr/bin/env python3
"""Read QEMU placement and scheduler accounting; never alter the observed VM.

This observer is separate from the guest workload and retained collector. Its
own CPU placement, sample duration and scheduling gaps are evidence too. Polling
does not prove absence of threads that start and exit between samples.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import time


def stat_fields(text):
    """Parse /proc/PID/stat even when comm contains spaces or parentheses."""
    opening, closing = text.find('('), text.rfind(')')
    if opening < 1 or closing <= opening:
        raise ValueError('malformed proc stat comm')
    fields = text[closing+2:].split()
    if len(fields) < 37:
        raise ValueError('short proc stat')
    return dict(tid=int(text[:opening].strip()), comm=text[opening+1:closing],
                state=fields[0], user_ticks=int(fields[11]),
                system_ticks=int(fields[12]), start_ticks=int(fields[19]),
                last_cpu=int(fields[36]))


def thread_sample(task, affinity=os.sched_getaffinity):
    """Retain both identity reads so exit/reuse cannot masquerade as one task."""
    before = stat_fields((task/'stat').read_text())
    schedstat = [int(v) for v in (task/'schedstat').read_text().split()]
    if len(schedstat) != 3 or any(v < 0 for v in schedstat):
        raise ValueError('invalid scheduler accounting')
    allowed = sorted(affinity(before['tid']))
    after = stat_fields((task/'stat').read_text())
    if (before['tid'], before['start_ticks']) != (after['tid'], after['start_ticks']):
        raise ProcessLookupError('task identity changed during sample')
    return dict(**after, affinity=allowed, runtime_ns=schedstat[0],
                runqueue_wait_ns=schedstat[1], timeslices=schedstat[2])


def sample(proc, expected_start, affinity=os.sched_getaffinity):
    began = time.monotonic_ns()
    real = time.time_ns()
    identity = stat_fields((proc/'stat').read_text())
    if identity['start_ticks'] != expected_start:
        raise RuntimeError('QEMU process identity changed')
    tasks, disappeared = [], []
    for task in sorted((proc/'task').iterdir(), key=lambda p: int(p.name)):
        try:
            tasks.append(thread_sample(task, affinity))
        except (FileNotFoundError, ProcessLookupError):
            disappeared.append(int(task.name))
    return dict(monotonic_begin_ns=began, realtime_ns=real,
                monotonic_end_ns=time.monotonic_ns(), tasks=tasks,
                disappeared_during_sample=disappeared)


def placement_issues(tasks):
    issues = []
    cpus = {}
    for task in tasks:
        comm = task['comm']
        if comm.startswith('CPU ') and comm.endswith('/KVM'):
            cpu = int(comm[4:-4])
            if cpu in cpus:
                issues.append(dict(reason='duplicate_vcpu', task=task))
            cpus[cpu] = task['affinity']
        elif task['affinity'] != [63]:
            issues.append(dict(reason='service_affinity', task=task))
    if cpus != {i: [i] for i in range(64)}:
        issues.append(dict(reason='vcpu_set_or_affinity', actual=cpus))
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--cmdline-sha256', required=True)
    parser.add_argument('--seconds', type=int, default=1200)
    parser.add_argument('--interval-ms', type=int, default=50)
    parser.add_argument('--observer-cpu', type=int, default=62)
    args = parser.parse_args()
    if not (1 <= args.seconds <= 7200 and 10 <= args.interval_ms <= 1000
            and args.observer_cpu == 62):
        raise ValueError('bounded observer on unused host CPU 62 required')
    proc = Path('/proc')/str(args.pid)
    command = (proc/'cmdline').read_bytes()
    if (Path(os.fsdecode(command.split(b'\0')[0])).name != 'qemu-system-x86_64'
            or hashlib.sha256(command).hexdigest() != args.cmdline_sha256):
        raise ValueError('observed QEMU command identity differs')
    identity = stat_fields((proc/'stat').read_text())
    os.sched_setaffinity(0, {args.observer_cpu})
    stop = False

    def requested_stop(number, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, requested_stop)
    signal.signal(signal.SIGINT, requested_stop)

    def emit(value):
        print(json.dumps(value, sort_keys=True, separators=(',', ':')), flush=True)

    start, own_cpu = time.monotonic_ns(), time.process_time_ns()
    emit(dict(kind='header', schema=1, pid=args.pid, identity=identity,
              command_sha256=args.cmdline_sha256, interval_ms=args.interval_ms,
              observer_pid=os.getpid(), observer_affinity=sorted(os.sched_getaffinity(0)),
              boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              scheduler_stats=Path('/proc/sys/kernel/sched_schedstats').read_text().strip(),
              clock_tick_hz=os.sysconf('SC_CLK_TCK'), realtime_ns=time.time_ns(),
              monotonic_ns=start, source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              limits='Polling may miss short-lived tasks. Runtime is cumulative; runqueue '
                     'wait requires enabled scheduler stats. No QEMU affinity or kernel setting is changed.'))
    samples, failures = 0, 0
    deadline = start+args.seconds*1_000_000_000
    while not stop and time.monotonic_ns() < deadline:
        due = time.monotonic_ns()+args.interval_ms*1_000_000
        try:
            row = sample(proc, identity['start_ticks'])
            row.update(kind='sample', sequence=samples, placement_issues=placement_issues(row['tasks']))
            failures += bool(row['placement_issues'])
            emit(row)
            samples += 1
        except Exception as error:
            failures += 1
            emit(dict(kind='sample_error', sequence=samples, error=repr(error),
                      monotonic_ns=time.monotonic_ns(), realtime_ns=time.time_ns()))
            break
        remaining = (due-time.monotonic_ns())/1e9
        if remaining > 0:
            time.sleep(remaining)
    emit(dict(kind='final', samples=samples, failures=failures, stopped_by_signal=stop,
              observer_cpu_ns=time.process_time_ns()-own_cpu, elapsed_ns=time.monotonic_ns()-start,
              realtime_ns=time.time_ns(), monotonic_ns=time.monotonic_ns()))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
