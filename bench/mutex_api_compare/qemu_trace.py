#!/usr/bin/env python3
"""Short read-only QEMU lifetime/accounting trace; no performance acceptance.

Run on the existing benchmark host. stdin accepts clock/phase markers only.
Samples cannot see lifetimes wholly between scans or departed accounting tails.
The observer records its own CPU cost and read brackets; it is intrusive evidence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import select
import sys
import time


def read(path):
    try:
        return dict(status='READ', text=path.read_text())
    except OSError as error:
        return dict(status='UNAVAILABLE', error=repr(error))


def stamp():
    return dict(real_ns=time.time_ns(), mono_ns=time.monotonic_ns(),
                boot_ns=time.clock_gettime_ns(time.CLOCK_BOOTTIME))


def identity(stat):
    return [int(stat.split(' ', 1)[0]), int(stat.rsplit(')', 1)[1].split()[19])]


def emit(event, **values):
    print(json.dumps(dict(event=event, **stamp(), **values), sort_keys=True), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid', type=int, required=True)
    p.add_argument('--cmdline-sha256', required=True)
    p.add_argument('--duration', type=float, default=45)
    p.add_argument('--interval', type=float, default=.5)
    a = p.parse_args()
    assert 1 <= a.duration <= 120 and .25 <= a.interval <= 5
    proc = Path('/proc')/str(a.pid)
    command = (proc/'cmdline').read_bytes()
    assert hashlib.sha256(command).hexdigest() == a.cmdline_sha256
    assert Path(os.fsdecode(command.split(b'\0')[0])).name == 'qemu-system-x86_64'
    start_ticks = (proc/'stat').read_text().rsplit(')', 1)[1].split()[19]
    began, cpu_began = time.monotonic_ns(), time.process_time_ns()
    emit('ready', pid=a.pid, start_ticks=start_ticks, cmdline_sha256=a.cmdline_sha256,
         observer_pid=os.getpid(), observer_affinity=sorted(os.sched_getaffinity(0)),
         clk_tck=os.sysconf('SC_CLK_TCK'), host_boot_id=read(Path('/proc/sys/kernel/random/boot_id')),
         sched_schedstats=read(Path('/proc/sys/kernel/sched_schedstats')),
         interval_s=a.interval, duration_s=a.duration, observer_rusage=list(resource.getrusage(resource.RUSAGE_SELF)))
    deadline, next_sample = began+int(a.duration*1e9), began
    phase, sequence, stop, end_reason = 'unmarked', 0, False, 'deadline'
    while time.monotonic_ns() < deadline and not stop:
        if time.monotonic_ns() >= next_sample:
            scan_began, cpu_before = stamp(), time.process_time_ns()
            rows = []
            for task in sorted((proc/'task').iterdir(), key=lambda p: int(p.name)):
                row = dict(tid=int(task.name), read_began=stamp(), complete=False)
                try:
                    first = (task/'stat').read_text()
                    row.update(stat_before=first, identity_before=identity(first))
                    comm = (task/'comm').read_text().strip()
                    row.update(comm=comm, affinity=sorted(os.sched_getaffinity(int(task.name))))
                    if comm == 'worker':
                        row['files'] = {name: read(task/name) for name in ('schedstat', 'io', 'wchan', 'syscall')}
                    row['stat_after'] = (task/'stat').read_text()
                    row['identity_after'] = identity(row['stat_after'])
                    row['identity_matches'] = row['identity_before'] == row['identity_after']
                    row['complete'] = row['identity_matches']
                except (FileNotFoundError, ProcessLookupError) as error:
                    row.update(disappeared=True, error=repr(error))
                row['read_finished'] = stamp()
                rows.append(row)
            process_io = read(proc/'io')
            emit('sample', sequence=sequence, phase=phase, scan_began=scan_began, scan_finished=stamp(),
                 observer_scan_cpu_ns=time.process_time_ns()-cpu_before,
                 tasks=rows, process_io=process_io)
            sequence += 1
            # Space scans from completion: slow reads cannot create catch-up load.
            next_sample = time.monotonic_ns()+int(a.interval*1e9)
        wait = max(0, min(next_sample, deadline)-time.monotonic_ns())/1e9
        if select.select([sys.stdin], [], [], wait)[0]:
            line = sys.stdin.readline()
            if not line:
                end_reason = 'stdin_eof'
                break
            message = json.loads(line)
            assert set(message) == {'marker'} and isinstance(message['marker'], str) and len(message['marker']) <= 100
            phase = message['marker']
            emit('marker', marker=phase)
            stop = phase == 'stop'
            if stop:
                end_reason = 'requested_stop'
    assert (proc/'cmdline').read_bytes() == command
    assert (proc/'stat').read_text().rsplit(')', 1)[1].split()[19] == start_ticks
    emit('complete', samples=sequence, end_reason=end_reason, elapsed_ns=time.monotonic_ns()-began,
         observer_cpu_ns=time.process_time_ns()-cpu_began,
         observer_rusage=list(resource.getrusage(resource.RUSAGE_SELF)),
         scope='Read-only diagnostic; observation overhead and missed lifetimes remain limitations.')


if __name__ == '__main__':
    main()
