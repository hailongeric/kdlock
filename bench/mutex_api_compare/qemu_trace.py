#!/usr/bin/env python3
"""Short read-only QEMU lifetime/accounting trace; no performance acceptance.

Run on the existing benchmark host. stdin accepts clock/phase markers and an
optional hash-bound full host capture, with an independent whole-call deadline.
Samples cannot see lifetimes wholly between scans or departed accounting tails.
The observer records its own CPU cost and read brackets; it is intrusive evidence.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import resource
import select
import signal
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


class AccountingWindow:
    """One bounded observation window; never a workload or gate permit."""
    def __init__(self, interval_ns):
        self.base_interval_ns = interval_ns
        self.expires_ns = None

    def arm(self, now):
        if self.expires_ns is not None:
            raise ValueError('accounting window cannot be renewed')
        self.expires_ns = now+60_000_000_000

    def active(self, now):
        return self.expires_ns is not None and now < self.expires_ns

    def next_read(self, finished):
        return finished+(250_000_000 if self.active(finished) else self.base_interval_ns)


def accounting_scan(proc):
    """Bracket each task identity and retain partial or vanished worker reads."""
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
    return dict(scan_began=scan_began, scan_finished=stamp(),
                observer_scan_cpu_ns=time.process_time_ns()-cpu_before, tasks=rows, process_io=process_io)


def capture_with_accounting(capture, sample, enabled):
    """The full gate read precedes accounting; its original cost stays separate."""
    result = capture()
    if enabled:
        observed = sample_status(sample)
        result.update(following_sample=observed['sequence'], following_sample_error=observed['error'])
    return result


def sample_status(sample):
    try:
        return dict(sequence=sample(), error=None)
    except Exception as error:
        # Keep the preceding capture/marker receipt even when accounting fails.
        # The coordinator refuses this ACK; it cannot infer observation/drain.
        return dict(sequence=None, error=repr(error))


def periodic_due(now, next_sample, active, control_ready):
    return now >= next_sample and not (active and control_ready)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid', type=int, required=True)
    p.add_argument('--cmdline-sha256', required=True)
    p.add_argument('--duration', type=float, default=45)
    p.add_argument('--interval', type=float, default=.5)
    p.add_argument('--full-capture', action='store_true', help='Allow the established read-only full host capture on request')
    p.add_argument('--phase-accounting', action='store_true', help='Permit one 60-second 250ms accounting window on request')
    a = p.parse_args()
    assert 1 <= a.duration <= 600 and .25 <= a.interval <= 5
    capture_source = None
    if a.full_capture:
        capture_path = Path('/home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/capture-host.py')
        capture_source = capture_path.read_bytes()
        assert hashlib.sha256(capture_source).hexdigest() == 'b0ad0d1854a0f0d60487fa9afea4d044aacf7b9fa86ec3c700d66a150cd4be1b'
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
         interval_s=a.interval, duration_s=a.duration, phase_accounting=a.phase_accounting,
         observer_rusage=list(resource.getrusage(resource.RUSAGE_SELF)))
    deadline, next_sample = began+int(a.duration*1e9), began
    phase, sequence, stop, end_reason = 'unmarked', 0, False, 'deadline'
    window = AccountingWindow(int(a.interval*1e9))
    expiration_reported = False
    def sample(reason, correlation=None):
        nonlocal sequence, next_sample
        number = sequence
        emit('sample', sequence=number, phase=phase, reason=reason, correlation=correlation,
             accounting_window_active=window.active(time.monotonic_ns()), **accounting_scan(proc))
        sequence += 1
        # Completion spacing forbids catch-up bursts, including forced reads.
        next_sample = window.next_read(time.monotonic_ns())
        return number
    while time.monotonic_ns() < deadline and not stop:
        now = time.monotonic_ns()
        active = window.active(now)
        if window.expires_ns is not None and not active and not expiration_reported:
            emit('accounting_expired', expires_ns=window.expires_ns)
            expiration_reported = True
        # While armed, pending control traffic takes priority over periodic
        # accounting. Never deliberately put a scan before an immediate gate.
        pending = active and bool(select.select([sys.stdin], [], [], 0)[0])
        if periodic_due(now, next_sample, active, pending):
            sample('periodic')
        wait = max(0, min(next_sample, deadline)-time.monotonic_ns())/1e9
        if select.select([sys.stdin], [], [], wait)[0]:
            line = sys.stdin.readline()
            if not line:
                end_reason = 'stdin_eof'
                break
            message = json.loads(line)
            if set(message) == {'accounting'}:
                assert a.phase_accounting and isinstance(message['accounting'], str) and len(message['accounting']) <= 100
                window.arm(time.monotonic_ns())
                phase = 'accounting-window-armed'
                observed = sample_status(lambda: sample('arm', message['accounting']))
                emit('accounting', accounting=message['accounting'], baseline_sample=observed['sequence'],
                     accounting_error=observed['error'],
                     armed_ns=window.expires_ns-60_000_000_000,
                     expires_ns=window.expires_ns, interval_ns=250_000_000)
                continue
            if set(message) == {'capture'}:
                assert capture_source is not None and isinstance(message['capture'], str) and len(message['capture']) <= 100
                capture_began, capture_cpu = stamp(), time.process_time_ns()
                output = io.StringIO()
                scope = {}
                def capture_timeout(signum, frame):
                    raise TimeoutError('full host capture exceeded 15 seconds')
                old_alarm = signal.signal(signal.SIGALRM, capture_timeout)
                signal.setitimer(signal.ITIMER_REAL, 15)
                try:
                    with contextlib.redirect_stdout(output):
                        exec(compile(capture_source, str(capture_path), 'exec'), scope)
                    result = dict(host=json.loads(output.getvalue()), error=None)
                except Exception as error:
                    result = dict(host=None, error=repr(error), partial_stdout=output.getvalue())
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 0)
                    signal.signal(signal.SIGALRM, old_alarm)
                    if 's' in scope:
                        scope['s'].close()
                result.update(capture_began=capture_began, capture_finished=stamp(),
                              capture_cpu_ns=time.process_time_ns()-capture_cpu)
                result = capture_with_accounting(lambda: result,
                    lambda: sample('after-capture', message['capture']), window.active(time.monotonic_ns()))
                emit('capture', capture=message['capture'],
                     capture_source_sha256=hashlib.sha256(capture_source).hexdigest(), **result)
                continue
            assert set(message) == {'marker'} and isinstance(message['marker'], str) and len(message['marker']) <= 100
            # The guest still waits for this ACK. Keep the preceding phase on
            # the read, and link the pending marker separately; its new action
            # has not started merely because the request arrived.
            observed = (sample_status(lambda: sample('marker', message['marker']))
                        if window.active(time.monotonic_ns()) else dict(sequence=None, error=None))
            phase = message['marker']
            emit('marker', marker=phase, accounting_sample=observed['sequence'], accounting_error=observed['error'])
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
